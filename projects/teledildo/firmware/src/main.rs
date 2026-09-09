//! TCode-over-USB firmware for the RP2040 reference board.
//!
//! Task layout:
//!
//! * `usb_task`      — runs the USB device stack.
//! * `rx_task`       — CDC-ACM bytes -> lines -> parsed commands -> `EVENTS`.
//! * `tx_task`       — sends replies (`D0`/`D1`/`D2`) back to the host.
//! * `button_task`   — e-stop press / long-press-to-clear -> `EVENTS`.
//! * `main`          — the 200 Hz control loop: drains `EVENTS`, reads the
//!   sensors, runs the governor, writes PWM, and feeds the hardware watchdog
//!   *only after* re-checking the outputs against the limits.
//!
//! Anything that stalls the control loop (a panic, a hung task, a stuck bus)
//! stops the watchdog from being fed; the RP2040 then resets, all GPIO return
//! to inputs, the driver's nSLEEP pull-down turns the motor off, and the
//! reset reason is reported as a latched `Hardware` fault on boot.

#![no_std]
#![no_main]

mod board;

use defmt::{info, warn};
use embassy_executor::{SpawnError, SpawnToken, Spawner};
use embassy_rp::adc::{self, Adc, Channel as AdcChannel};
use embassy_rp::bind_interrupts;
use embassy_rp::gpio::{Input, Level, Output, Pull};
use embassy_rp::peripherals::USB;
use embassy_rp::pwm::{self, Pwm};
use embassy_rp::usb::{Driver, InterruptHandler};
use embassy_rp::watchdog::Watchdog;
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_sync::channel::Channel;
use embassy_time::{with_timeout, Duration, Instant, Ticker};
use embassy_usb::class::cdc_acm::{CdcAcmClass, Receiver, Sender, State};
use embassy_usb::driver::EndpointError;
use embassy_usb::{Builder, UsbDevice};
use fixed::traits::ToFixed;
use static_cell::StaticCell;
use teledildo_core::governor::{
    Disposition, Fault, Governor, Limits, Sensors, State as GovState, AXIS_LIST,
};
use teledildo_core::line::LineBuffer;
use teledildo_core::tcode::{parse_line, Command, DeviceCommand};
use teledildo_core::value::Fraction;
use {defmt_rtt as _, panic_probe as _};

bind_interrupts!(struct Irqs {
    USBCTRL_IRQ => InterruptHandler<USB>;
});

/// Reported for `D1`.
const FIRMWARE_ID: &str = concat!("teledildo-rp2040 v", env!("CARGO_PKG_VERSION"));

/// Control loop period. 5 ms keeps ADC + PWM work far below 100 % load while
/// giving the slew limiter 1 ms-scale resolution (dt is passed explicitly).
const CONTROL_PERIOD: Duration = Duration::from_millis(5);
/// Watchdog timeout: 100 missed control periods.
const WATCHDOG_TIMEOUT: Duration = Duration::from_millis(500);
/// Holding the button this long while faulted clears the fault.
const CLEAR_HOLD: Duration = Duration::from_secs(3);
/// Longest TCode line accepted.
const LINE_CAPACITY: usize = 128;
/// USB CDC bulk packet size.
const USB_PACKET: u16 = 64;

/// Things that can happen to the control loop.
#[derive(Clone, Copy, Debug)]
enum Event {
    /// A parsed TCode command.
    Command(Command),
    /// Host opened the port.
    LinkUp,
    /// Host closed the port / USB disconnected.
    LinkDown,
    /// E-stop button pressed.
    ButtonPressed,
    /// E-stop button held for `CLEAR_HOLD`.
    ButtonHeld,
}

static EVENTS: Channel<CriticalSectionRawMutex, Event, 16> = Channel::new();
static REPLIES: Channel<CriticalSectionRawMutex, &'static str, 4> = Channel::new();

type UsbDriver = Driver<'static, USB>;

#[embassy_executor::main]
async fn main(spawner: Spawner) {
    let p = embassy_rp::init(embassy_rp::config::Config::default());

    // --- Watchdog first: from here on, a stall resets the chip. ---
    let mut watchdog = Watchdog::new(p.WATCHDOG);
    let boot_fault = watchdog.reset_reason().is_some();
    watchdog.start(WATCHDOG_TIMEOUT);

    // --- Actuators, all initialised OFF before anything else runs. ---
    let mut driver_enable = Output::new(p.PIN_20, Level::Low);
    let mut led = Output::new(p.PIN_25, Level::Low);

    let mut motor_cfg = pwm::Config::default();
    motor_cfg.top = board::MOTOR_PWM_TOP;
    motor_cfg.compare_a = 0;
    motor_cfg.compare_b = 0;
    let mut motor_pwm = Pwm::new_output_ab(p.PWM_SLICE0, p.PIN_16, p.PIN_17, motor_cfg.clone());

    let mut servo_cfg = pwm::Config::default();
    servo_cfg.divider = board::SERVO_PWM_DIVIDER.to_fixed();
    servo_cfg.top = board::SERVO_PWM_TOP;
    servo_cfg.compare_a = board::SERVO_PULSE_MIN;
    let mut servo_pwm = Pwm::new_output_a(p.PWM_SLICE1, p.PIN_18, servo_cfg.clone());

    // --- Sensors. ---
    let mut adc = Adc::new_blocking(p.ADC, adc::Config::default());
    let mut ntc = AdcChannel::new_pin(p.PIN_26, Pull::None);
    let mut current = AdcChannel::new_pin(p.PIN_27, Pull::None);
    let mut supply = AdcChannel::new_pin(p.PIN_29, Pull::None);

    // --- USB CDC-ACM. ---
    let (usb, tx, rx) = build_usb(Driver::new(p.USB, Irqs));
    spawn_or_halt(&spawner, usb_task(usb));
    spawn_or_halt(&spawner, rx_task(rx));
    spawn_or_halt(&spawner, tx_task(tx));
    spawn_or_halt(&spawner, button_task(Input::new(p.PIN_15, Pull::Up)));

    // --- Governor. ---
    let limits = match Limits::DEFAULT.validated() {
        Ok(l) => l,
        Err(e) => {
            // Cannot happen for DEFAULT (checked by tests), but never run
            // with unvalidated limits: stay silent and let the watchdog bite.
            defmt::error!("invalid limits: {:?}", defmt::Debug2Format(&e));
            halt()
        }
    };
    let mut governor = Governor::new(limits);
    if boot_fault {
        warn!("watchdog reset detected: latching Hardware fault");
        governor.report(Fault::Hardware);
    }
    info!("{} ready", FIRMWARE_ID);

    let mut ticker = Ticker::every(CONTROL_PERIOD);
    let mut blink: u32 = 0;
    loop {
        ticker.next().await;
        let now_ms = Instant::now().as_millis();

        // 1. Drain events.
        while let Ok(ev) = EVENTS.try_receive() {
            handle_event(&mut governor, ev, now_ms);
        }

        // 2. Read sensors. A probe that reads outside its table is a fault.
        let sensors = read_sensors(&mut adc, &mut ntc, &mut current, &mut supply);
        let sensors = match sensors {
            Ok(s) => s,
            Err(()) => {
                governor.report(Fault::Hardware);
                Sensors::default()
            }
        };

        // 3. Run the governor.
        let out = governor.tick(now_ms, &sensors);

        // 4. Independent re-check of the invariants before touching hardware.
        let within_limits = out.vibe.iter().all(|v| *v <= limits.max_vibe)
            && (out.driver_enable || out.is_silent());
        if !within_limits {
            // Governor bug: hard-off and stop feeding the watchdog.
            defmt::error!(
                "governor invariant violated: {:?}",
                defmt::Debug2Format(&out)
            );
            driver_enable.set_low();
            motor_cfg.compare_a = 0;
            motor_cfg.compare_b = 0;
            motor_pwm.set_config(&motor_cfg);
            halt()
        }

        // 5. Apply outputs. Enable is asserted after PWM is set, and dropped
        //    before PWM would otherwise still be non-zero, so glitches are
        //    always toward "off".
        let a = out.vibe.first().copied().unwrap_or(Fraction::ZERO);
        let b = out.vibe.get(1).copied().unwrap_or(Fraction::ZERO);
        motor_cfg.compare_a = a.scale_to(board::MOTOR_PWM_TOP);
        motor_cfg.compare_b = b.scale_to(board::MOTOR_PWM_TOP);
        if !out.driver_enable {
            driver_enable.set_low();
        }
        motor_pwm.set_config(&motor_cfg);
        let stroke = out.linear.first().copied().unwrap_or(Fraction::ZERO);
        servo_cfg.compare_a =
            board::SERVO_PULSE_MIN.saturating_add(stroke.scale_to(board::SERVO_PULSE_SPAN));
        servo_pwm.set_config(&servo_cfg);
        if out.driver_enable {
            driver_enable.set_high();
        }

        // 6. Status LED: solid when active, off when idle, fast blink on fault,
        //    slow blink while coasting.
        blink = blink.wrapping_add(1);
        match governor.state() {
            GovState::Active => led.set_high(),
            GovState::Idle => led.set_low(),
            GovState::Coasting(_) => {
                if blink % 200 < 100 {
                    led.set_high();
                } else {
                    led.set_low();
                }
            }
            GovState::Faulted(_) => {
                if blink % 40 < 20 {
                    led.set_high();
                } else {
                    led.set_low();
                }
            }
        }

        // 7. Only a loop that got this far may feed the watchdog.
        watchdog.feed(WATCHDOG_TIMEOUT);
    }
}

/// Stop feeding the watchdog and wait for the reset it will deliver. Outputs
/// are left wherever the caller put them (always "off" at every call site).
fn halt() -> ! {
    loop {
        cortex_m::asm::wfe();
    }
}

/// Spawn a task, or halt if the task pool is exhausted (impossible for the
/// fixed set of tasks here, but never continue with a task missing).
fn spawn_or_halt<S>(spawner: &Spawner, token: Result<SpawnToken<S>, SpawnError>) {
    match token {
        Ok(t) => spawner.spawn(t),
        Err(_) => halt(),
    }
}

fn handle_event(governor: &mut Governor, ev: Event, now_ms: u64) {
    match ev {
        Event::Command(cmd) => match governor.handle(&cmd, now_ms) {
            Disposition::Applied => {}
            Disposition::Reply(q) => {
                let reply = match q {
                    DeviceCommand::ListAxes => Some(AXIS_LIST),
                    other => other.reply(FIRMWARE_ID),
                };
                if let Some(text) = reply {
                    // Drop the reply rather than stall the control loop.
                    let _ = REPLIES.try_send(text);
                }
            }
            Disposition::IgnoredFaulted => {
                warn!("ignored (faulted): {:?}", defmt::Debug2Format(&cmd));
            }
            Disposition::IgnoredUnsupportedAxis => {
                warn!("unsupported axis: {:?}", defmt::Debug2Format(&cmd));
            }
        },
        Event::LinkUp => info!("host connected"),
        Event::LinkDown => {
            info!("host disconnected");
            governor.link_down();
        }
        Event::ButtonPressed => {
            if !matches!(governor.state(), GovState::Faulted(_)) {
                warn!("emergency stop");
                governor.report(Fault::EmergencyStop);
            }
        }
        Event::ButtonHeld => {
            // Clearing requires healthy sensors; the next tick's readings are
            // what count, so pass the last known state as a pre-check only.
            let state = governor.clear_fault(&Sensors::default());
            info!("fault clear requested -> {:?}", defmt::Debug2Format(&state));
        }
    }
}

fn read_sensors(
    adc: &mut Adc<'_, adc::Blocking>,
    ntc: &mut AdcChannel<'_>,
    current: &mut AdcChannel<'_>,
    supply: &mut AdcChannel<'_>,
) -> Result<Sensors, ()> {
    let t = adc.blocking_read(ntc).map_err(|_| ())?;
    let i = adc.blocking_read(current).map_err(|_| ())?;
    let v = adc.blocking_read(supply).map_err(|_| ())?;
    Ok(Sensors {
        temperature_dc: Some(board::ntc_to_dc(t).ok_or(())?),
        motor_current_ma: Some(board::current_to_ma(i).ok_or(())?),
        supply_mv: Some(board::supply_to_mv(v).ok_or(())?),
    })
}

fn build_usb(
    driver: UsbDriver,
) -> (
    UsbDevice<'static, UsbDriver>,
    Sender<'static, UsbDriver>,
    Receiver<'static, UsbDriver>,
) {
    // pid.codes test VID/PID: replace before distributing hardware.
    let mut config = embassy_usb::Config::new(0x1209, 0x0001);
    config.manufacturer = Some("teledildo");
    config.product = Some("TCode v0.3 device");
    config.serial_number = Some("0001");
    config.max_power = 500;
    config.max_packet_size_0 = 64;

    static CONFIG_DESC: StaticCell<[u8; 256]> = StaticCell::new();
    static BOS_DESC: StaticCell<[u8; 256]> = StaticCell::new();
    static CONTROL_BUF: StaticCell<[u8; 64]> = StaticCell::new();
    static STATE: StaticCell<State<'static>> = StaticCell::new();

    let mut builder = Builder::new(
        driver,
        config,
        CONFIG_DESC.init([0; 256]),
        BOS_DESC.init([0; 256]),
        &mut [],
        CONTROL_BUF.init([0; 64]),
    );
    let class = CdcAcmClass::new(&mut builder, STATE.init(State::new()), USB_PACKET);
    let (tx, rx) = class.split();
    (builder.build(), tx, rx)
}

#[embassy_executor::task]
async fn usb_task(mut usb: UsbDevice<'static, UsbDriver>) -> ! {
    usb.run().await
}

#[embassy_executor::task]
async fn rx_task(mut rx: Receiver<'static, UsbDriver>) -> ! {
    let mut lines = LineBuffer::<LINE_CAPACITY>::new();
    let mut buf = [0u8; 64];
    loop {
        rx.wait_connection().await;
        EVENTS.send(Event::LinkUp).await;
        lines.clear();
        loop {
            match rx.read_packet(&mut buf).await {
                Ok(n) => {
                    let chunk = buf.get(..n).unwrap_or(&[]);
                    for &byte in chunk {
                        if lines.push(byte) == teledildo_core::line::Push::Complete {
                            for item in parse_line(lines.line()) {
                                match item {
                                    Ok(cmd) => EVENTS.send(Event::Command(cmd)).await,
                                    Err(e) => warn!("parse error: {:?}", defmt::Debug2Format(&e)),
                                }
                            }
                        }
                    }
                }
                Err(EndpointError::Disabled) => break,
                Err(EndpointError::BufferOverflow) => warn!("usb rx overflow"),
            }
        }
        EVENTS.send(Event::LinkDown).await;
    }
}

#[embassy_executor::task]
async fn tx_task(mut tx: Sender<'static, UsbDriver>) -> ! {
    loop {
        let text = REPLIES.receive().await;
        // Chunk below the packet size so no zero-length packet is needed.
        for chunk in text
            .as_bytes()
            .chunks(usize::from(USB_PACKET).saturating_sub(1))
        {
            if tx.write_packet(chunk).await.is_err() {
                break;
            }
        }
        let _ = tx.write_packet(b"\n").await;
    }
}

/// Active-low momentary switch. A press latches an e-stop; holding it for
/// `CLEAR_HOLD` requests a fault clear (which only succeeds if the sensors
/// are healthy).
#[embassy_executor::task]
async fn button_task(mut button: Input<'static>) -> ! {
    loop {
        button.wait_for_falling_edge().await;
        // Debounce.
        embassy_time::Timer::after_millis(30).await;
        if button.is_high() {
            continue;
        }
        EVENTS.send(Event::ButtonPressed).await;
        if with_timeout(CLEAR_HOLD, button.wait_for_rising_edge())
            .await
            .is_err()
        {
            EVENTS.send(Event::ButtonHeld).await;
            button.wait_for_rising_edge().await;
        }
    }
}
