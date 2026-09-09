//! Property tests mirroring the Kani harnesses in `src/proofs.rs`, runnable
//! with plain `cargo test` on any host.

#![allow(
    clippy::unwrap_used,
    clippy::indexing_slicing,
    clippy::arithmetic_side_effects,
    clippy::format_push_string,
    clippy::single_match_else
)]

use proptest::prelude::*;
use teledildo_core::governor::{Fault, Governor, Limits, Outputs, Sensors, State, VIBE_CHANNELS};
use teledildo_core::line::LineBuffer;
use teledildo_core::tcode::{parse_line, Axis, AxisKind, Command, DeviceCommand, Modifier};
use teledildo_core::value::Fraction;

fn fraction() -> impl Strategy<Value = Fraction> {
    (0u16..Fraction::SCALE).prop_map(|r| Fraction::new(r).unwrap())
}

fn modifier() -> impl Strategy<Value = Modifier> {
    prop_oneof![
        Just(Modifier::Immediate),
        any::<u32>().prop_map(|millis| Modifier::Interval { millis }),
        any::<u32>().prop_map(|per_second| Modifier::Speed { per_second }),
    ]
}

fn command() -> impl Strategy<Value = Command> {
    prop_oneof![
        Just(Command::Device(DeviceCommand::Stop)),
        Just(Command::Device(DeviceCommand::Identify)),
        (0u8..=9, fraction(), modifier()).prop_map(|(index, target, modifier)| Command::Move {
            axis: Axis {
                kind: AxisKind::Vibrate,
                index
            },
            target,
            modifier,
        }),
        (0u8..=9, fraction(), modifier()).prop_map(|(index, target, modifier)| Command::Move {
            axis: Axis {
                kind: AxisKind::Linear,
                index
            },
            target,
            modifier,
        }),
    ]
}

/// One step of an interleaving: maybe a command, then a tick after `dt`.
type Step = (Option<Command>, u16);

fn steps() -> impl Strategy<Value = Vec<Step>> {
    prop::collection::vec((prop::option::of(command()), 0u16..=2000), 0..200)
}

proptest! {
    #[test]
    fn parser_never_panics(bytes in prop::collection::vec(any::<u8>(), 0..64)) {
        for item in parse_line(&bytes) {
            if let Ok(Command::Move { target, axis, .. }) = item {
                prop_assert!(target.raw() < Fraction::SCALE);
                prop_assert!(axis.index <= 9);
            }
        }
    }

    #[test]
    fn parser_round_trips_well_formed_moves(
        kind in prop_oneof![Just(b'L'), Just(b'R'), Just(b'V'), Just(b'A')],
        index in 0u8..=9,
        raw in 0u16..Fraction::SCALE,
        modifier in modifier(),
    ) {
        let mut text = format!("{}{}{:04}", char::from(kind), index, raw);
        match modifier {
            Modifier::Immediate => {}
            Modifier::Interval { millis } => text.push_str(&format!("I{millis}")),
            Modifier::Speed { per_second } => text.push_str(&format!("S{per_second}")),
        }
        let parsed: Vec<_> = parse_line(text.as_bytes()).collect();
        prop_assert_eq!(parsed.len(), 1);
        match parsed[0] {
            Ok(Command::Move { axis, target, modifier: m }) => {
                prop_assert_eq!(axis.kind.letter(), kind);
                prop_assert_eq!(axis.index, index);
                prop_assert_eq!(target.raw(), raw);
                prop_assert_eq!(m, modifier);
            }
            other => prop_assert!(false, "unexpected {other:?}"),
        }
    }

    #[test]
    fn line_buffer_never_exceeds_capacity(bytes in prop::collection::vec(any::<u8>(), 0..300)) {
        let mut lb = LineBuffer::<32>::new();
        for &b in &bytes {
            lb.push(b);
            prop_assert!(lb.line().len() <= 32);
        }
    }

    #[test]
    fn ceiling_and_slew_hold(steps in steps()) {
        let limits = Limits::DEFAULT;
        let mut g = Governor::new(limits);
        let mut now = 0u64;
        let mut prev = g.outputs();
        for (cmd, dt) in steps {
            if let Some(c) = cmd {
                g.handle(&c, now);
            }
            now += u64::from(dt);
            let out = g.tick(now, &Sensors::default());
            for v in &out.vibe {
                prop_assert!(*v <= limits.max_vibe);
            }
            let dt_clamped = u32::from(dt).min(limits.max_tick_ms);
            let max_rise = u32::from(limits.vibe_slew_per_ms) * dt_clamped;
            for (p, o) in prev.vibe.iter().zip(out.vibe.iter()) {
                prop_assert!(u32::from(o.raw()) <= u32::from(p.raw()) + max_rise);
            }
            prop_assert_eq!(out.driver_enable, !out.is_silent());
            prev = out;
        }
    }

    #[test]
    fn faults_latch_until_cleared(prefix in steps(), suffix in steps()) {
        let mut g = Governor::new(Limits::DEFAULT);
        let mut now = 0u64;
        for (cmd, dt) in prefix {
            if let Some(c) = cmd {
                g.handle(&c, now);
            }
            now += u64::from(dt);
            g.tick(now, &Sensors::default());
        }
        g.report(Fault::EmergencyStop);
        prop_assert_eq!(g.outputs(), Outputs::OFF);
        for (cmd, dt) in suffix {
            if let Some(c) = cmd {
                g.handle(&c, now);
            }
            now += u64::from(dt);
            prop_assert_eq!(g.tick(now, &Sensors::default()), Outputs::OFF);
            prop_assert_eq!(g.state(), State::Faulted(Fault::EmergencyStop));
        }
        prop_assert_eq!(g.clear_fault(&Sensors::default()), State::Idle);
        prop_assert_eq!(g.outputs(), Outputs::OFF);
    }

    #[test]
    fn sensor_violation_faults_immediately(
        temperature_dc in prop::option::of(any::<i16>()),
        motor_current_ma in prop::option::of(any::<u16>()),
        supply_mv in prop::option::of(any::<u16>()),
    ) {
        let sensors = Sensors { temperature_dc, motor_current_ma, supply_mv };
        let mut g = Governor::new(Limits::DEFAULT);
        let out = g.tick(0, &sensors);
        match sensors.violation(&Limits::DEFAULT) {
            Some(f) => {
                prop_assert_eq!(g.state(), State::Faulted(f));
                prop_assert_eq!(out, Outputs::OFF);
            }
            None => prop_assert_eq!(g.state(), State::Idle),
        }
    }

    #[test]
    fn link_timeout_silences_vibration(cmds in prop::collection::vec(command(), 0..8)) {
        let limits = Limits::DEFAULT;
        let mut g = Governor::new(limits);
        for c in &cmds {
            g.handle(c, 0);
        }
        g.tick(0, &Sensors::default());
        let deadline = u64::from(limits.link_timeout_ms)
            + u64::from(Fraction::SCALE) / u64::from(limits.vibe_slew_per_ms)
            + 2 * u64::from(limits.max_tick_ms);
        let mut now = 0u64;
        let mut out = g.outputs();
        while now <= deadline {
            now += u64::from(limits.max_tick_ms);
            out = g.tick(now, &Sensors::default());
        }
        for i in 0..VIBE_CHANNELS {
            prop_assert_eq!(out.vibe[i], Fraction::ZERO);
        }
    }
}
