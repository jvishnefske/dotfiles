//! Pin map, PWM geometry and sensor scaling for the reference board.
//!
//! ```text
//! Pico pin   Function                     Connects to
//! GP16       PWM0A  vibe motor 0          DRV8833 AIN1 (AIN2 -> GND)
//! GP17       PWM0B  vibe motor 1          DRV8833 BIN1 (BIN2 -> GND)
//! GP18       PWM1A  stroke servo, 50 Hz   servo signal (optional)
//! GP20       GPIO   driver enable         DRV8833 nSLEEP (10k pull-down)
//! GP15       GPIO   e-stop / clear        momentary switch to GND
//! GP25       GPIO   status LED            on-board LED
//! GP26/ADC0  NTC thermistor               10k NTC 3V3->pin, 10k pin->GND
//! GP27/ADC1  motor current                INA180A1 (20 V/V) over 0.1 ohm
//! GP29/ADC3  VSYS / 3                     Pico on-board divider
//! ```
//!
//! Every constant that changes when the hardware changes lives here.

use teledildo_core::lookup::{interpolate, scale};

/// System clock the PWM dividers below assume.
pub const SYS_CLK_HZ: u32 = 125_000_000;

/// Motor PWM: 125 MHz / (4999 + 1) = 25 kHz, above the audible range.
pub const MOTOR_PWM_TOP: u16 = 4_999;
const _: () = assert!(
    SYS_CLK_HZ / 5_000 == 25_000,
    "MOTOR_PWM_TOP assumes 125 MHz"
);

/// Servo PWM: divider 100 -> 1.25 MHz tick; top 24_999 -> 20 ms period.
pub const SERVO_PWM_DIVIDER: u16 = 100;
/// Servo PWM counter top for a 50 Hz frame.
pub const SERVO_PWM_TOP: u16 = 24_999;
const _: () = assert!(SYS_CLK_HZ / 100 / 25_000 == 50, "servo PWM assumes 125 MHz");
/// Servo pulse for one end of travel: 1.0 ms = 1250 ticks.
pub const SERVO_PULSE_MIN: u16 = 1_250;
/// Servo pulse span: 1.0 ms .. 2.0 ms = 1250 ticks.
pub const SERVO_PULSE_SPAN: u16 = 1_250;

/// RP2040 ADC is 12-bit.
pub const ADC_MAX: u16 = 4_095;
/// ADC reference in millivolts.
pub const ADC_REF_MV: u32 = 3_300;

/// 10k NTC (beta 3950) on top of a 10k divider, sampled at 12 bits.
/// Columns: ADC count, temperature in tenths of a degree Celsius.
/// Generated for 0..=95 C in 5 C steps; anything outside is a sensor fault.
pub const NTC_TABLE: &[(u16, i16)] = &[
    (939, 0),
    (1140, 50),
    (1357, 100),
    (1585, 150),
    (1817, 200),
    (2048, 250),
    (2270, 300),
    (2481, 350),
    (2676, 400),
    (2854, 450),
    (3014, 500),
    (3155, 550),
    (3280, 600),
    (3388, 650),
    (3482, 700),
    (3563, 750),
    (3633, 800),
    (3694, 850),
    (3745, 900),
    (3790, 950),
];

/// INA180A1 (gain 20) across 0.1 ohm: 2 mV per mA, so full scale is
/// 3300 mV / 2 = 1650 mA.
pub const CURRENT_FULL_SCALE_MA: u32 = 1_650;

/// Pico VSYS is divided by 3 before ADC3.
pub const SUPPLY_FULL_SCALE_MV: u32 = ADC_REF_MV * 3;

/// Thermistor count to tenths of a degree, `None` for open/short/out of table.
#[must_use]
pub fn ntc_to_dc(count: u16) -> Option<i16> {
    interpolate(NTC_TABLE, count)
}

/// Current-sense count to milliamps.
#[must_use]
pub fn current_to_ma(count: u16) -> Option<u16> {
    scale(count, CURRENT_FULL_SCALE_MA, ADC_MAX).and_then(|v| u16::try_from(v).ok())
}

/// Supply-sense count to millivolts.
#[must_use]
pub fn supply_to_mv(count: u16) -> Option<u16> {
    scale(count, SUPPLY_FULL_SCALE_MV, ADC_MAX).and_then(|v| u16::try_from(v).ok())
}
