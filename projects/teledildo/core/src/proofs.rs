//! Kani model-checking harnesses. Compiled only under `cargo kani`.
//!
//! Run with:
//!
//! ```text
//! cargo kani --tests   # or: cargo kani --harness <name>
//! ```
//!
//! Each harness exhaustively explores every input of the given size; a
//! passing harness is a proof, not a sample, for that bound. The bounds are
//! small because the code is bounded: the parser touches at most one token
//! and the governor has no unbounded loops.

use crate::governor::{Fault, Governor, Limits, Outputs, Sensors, State, VIBE_CHANNELS};
use crate::line::LineBuffer;
use crate::lookup::interpolate;
use crate::tcode::{parse_line, Axis, AxisKind, Command, DeviceCommand, Modifier};
use crate::value::Fraction;

/// Parsing an arbitrary byte string never panics and each produced command
/// carries an in-range magnitude (guaranteed by `Fraction`'s invariant).
#[kani::proof]
#[kani::unwind(12)]
fn parse_never_panics() {
    let bytes: [u8; 10] = kani::any();
    let len: usize = kani::any();
    kani::assume(len <= bytes.len());
    for item in parse_line(&bytes[..len]) {
        if let Ok(Command::Move { target, axis, .. }) = item {
            assert!(target.raw() < Fraction::SCALE);
            assert!(axis.index <= 9);
        }
    }
}

/// Magnitude parsing agrees with its specification on every digit string.
#[kani::proof]
#[kani::unwind(6)]
fn magnitude_parse_is_left_aligned() {
    let digits: [u8; 4] = kani::any();
    let len: usize = kani::any();
    kani::assume(len >= 1 && len <= 4);
    let slice = &digits[..len];
    let all_digits = slice.iter().all(u8::is_ascii_digit);
    let parsed = Fraction::from_tcode_digits(slice);
    assert_eq!(parsed.is_some(), all_digits);
    if let Some(f) = parsed {
        let mut expect: u32 = 0;
        for &d in slice {
            expect = expect * 10 + u32::from(d - b'0');
        }
        for _ in len..4 {
            expect *= 10;
        }
        assert_eq!(u32::from(f.raw()), expect);
    }
}

/// The line assembler never panics and never yields a line longer than its
/// capacity.
#[kani::proof]
#[kani::unwind(10)]
fn line_buffer_bounded() {
    let mut lb = LineBuffer::<4>::new();
    let bytes: [u8; 8] = kani::any();
    for &b in &bytes {
        lb.push(b);
        assert!(lb.line().len() <= 4);
    }
}

fn any_fraction() -> Fraction {
    let raw: u16 = kani::any();
    kani::assume(raw < Fraction::SCALE);
    Fraction::saturating(raw)
}

fn any_modifier() -> Modifier {
    match kani::any::<u8>() % 3 {
        0 => Modifier::Immediate,
        1 => Modifier::Interval {
            millis: kani::any(),
        },
        _ => Modifier::Speed {
            per_second: kani::any(),
        },
    }
}

fn any_command() -> Command {
    match kani::any::<u8>() % 6 {
        0 => Command::Device(DeviceCommand::Stop),
        1 => Command::Device(DeviceCommand::Identify),
        2 => Command::Move {
            axis: Axis {
                kind: AxisKind::Linear,
                index: 0,
            },
            target: any_fraction(),
            modifier: any_modifier(),
        },
        _ => Command::Move {
            axis: Axis {
                kind: AxisKind::Vibrate,
                index: kani::any::<u8>() % 3, // includes an unsupported index
            },
            target: any_fraction(),
            modifier: any_modifier(),
        },
    }
}

fn assert_within_ceiling(out: &Outputs, limits: &Limits) {
    for v in &out.vibe {
        assert!(*v <= limits.max_vibe);
    }
}

/// For any short command/tick interleaving: outputs respect the ceiling and
/// the per-tick rise bound.
#[kani::proof]
#[kani::unwind(5)]
fn ceiling_and_slew_hold() {
    let limits = Limits::DEFAULT;
    let mut g = Governor::new(limits);
    let mut now: u64 = 0;
    let mut prev = g.outputs();
    for _ in 0..3 {
        if kani::any() {
            g.handle(&any_command(), now);
        }
        let dt: u8 = kani::any();
        now += u64::from(dt);
        let out = g.tick(now, &Sensors::default());
        assert_within_ceiling(&out, &limits);
        let dt_clamped = u32::from(dt).min(limits.max_tick_ms);
        let max_rise = u32::from(limits.vibe_slew_per_ms) * dt_clamped;
        for (p, o) in prev.vibe.iter().zip(out.vibe.iter()) {
            assert!(u32::from(o.raw()) <= u32::from(p.raw()) + max_rise);
        }
        assert_eq!(out.driver_enable, !out.is_silent());
        prev = out;
    }
}

/// Once faulted, every output is off and stays off through arbitrary
/// commands and ticks until `clear_fault` succeeds.
#[kani::proof]
#[kani::unwind(5)]
fn faults_latch() {
    let mut g = Governor::new(Limits::DEFAULT);
    g.handle(&any_command(), 0);
    g.tick(1, &Sensors::default());
    g.report(Fault::EmergencyStop);
    assert_eq!(g.outputs(), Outputs::OFF);
    let mut now: u64 = 1;
    for _ in 0..3 {
        g.handle(&any_command(), now);
        now += u64::from(kani::any::<u8>());
        let out = g.tick(now, &Sensors::default());
        assert_eq!(out, Outputs::OFF);
        assert!(matches!(g.state(), State::Faulted(Fault::EmergencyStop)));
    }
    // An unhealthy sensor keeps the latch.
    let hot = Sensors {
        temperature_dc: Some(Limits::DEFAULT.max_temperature_dc + 1),
        ..Sensors::default()
    };
    assert!(matches!(g.clear_fault(&hot), State::Faulted(_)));
    assert_eq!(g.clear_fault(&Sensors::default()), State::Idle);
    assert_eq!(g.outputs(), Outputs::OFF);
}

/// Any sensor reading outside limits faults the governor on that tick.
#[kani::proof]
fn sensor_violation_faults_immediately() {
    let mut g = Governor::new(Limits::DEFAULT);
    let sensors = Sensors {
        temperature_dc: kani::any(),
        motor_current_ma: kani::any(),
        supply_mv: kani::any(),
    };
    let out = g.tick(0, &sensors);
    match sensors.violation(&Limits::DEFAULT) {
        Some(f) => {
            assert_eq!(g.state(), State::Faulted(f));
            assert_eq!(out, Outputs::OFF);
        }
        None => assert_eq!(g.state(), State::Idle),
    }
}

/// With the link silent, vibration is fully off within
/// `link_timeout + full-scale / slew` milliseconds.
#[kani::proof]
#[kani::unwind(4)]
fn link_timeout_silences_vibration() {
    let limits = Limits::DEFAULT;
    let mut g = Governor::new(limits);
    for _ in 0..VIBE_CHANNELS {
        g.handle(&any_command(), 0);
    }
    g.tick(0, &Sensors::default());
    // One tick past the timeout flips to Coasting; the ramp then needs at
    // most SCALE / slew ms, taken in max_tick_ms-sized steps.
    let timeout = u64::from(limits.link_timeout_ms) + 1;
    let ramp_ms = u64::from(Fraction::SCALE) / u64::from(limits.vibe_slew_per_ms) + 1;
    let step = u64::from(limits.max_tick_ms);
    let mut now = timeout;
    let mut out = g.tick(now, &Sensors::default());
    let mut elapsed = 0;
    while elapsed < ramp_ms {
        now += step;
        elapsed += step;
        out = g.tick(now, &Sensors::default());
    }
    for v in &out.vibe {
        assert_eq!(*v, Fraction::ZERO);
    }
}

/// Table interpolation never panics and stays within the table's y-range.
#[kani::proof]
#[kani::unwind(6)]
fn interpolate_bounded() {
    let table: [(u16, i16); 4] = kani::any();
    kani::assume(table.windows(2).all(|w| w[0].0 < w[1].0));
    let x: u16 = kani::any();
    if let Some(y) = interpolate(&table, x) {
        let lo = table.iter().map(|p| p.1).min().unwrap();
        let hi = table.iter().map(|p| p.1).max().unwrap();
        assert!(lo <= y && y <= hi);
    }
}
