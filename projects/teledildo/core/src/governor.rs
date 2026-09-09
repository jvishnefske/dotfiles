//! The safety envelope between the host and the actuators.
//!
//! The firmware feeds every parsed [`Command`] into [`Governor::handle`] and
//! calls [`Governor::tick`] at a fixed rate with the current time and sensor
//! readings. The [`Outputs`] returned by `tick` are the *only* values the
//! firmware is allowed to write to the motor driver.
//!
//! Guarantees (each has a proptest in `tests/` and a Kani harness in
//! `src/proofs.rs`):
//!
//! 1. **Ceiling** — every vibration output is `<= limits.max_vibe`, whatever
//!    the host asks for.
//! 2. **Slew** — a vibration output never rises by more than
//!    `limits.vibe_slew_per_ms * dt` between consecutive ticks. (It may fall
//!    faster: stopping is always allowed.)
//! 3. **Link watchdog** — if no command arrives for `limits.link_timeout_ms`,
//!    or the transport reports the link down, vibration ramps to zero and the
//!    driver is disabled until the host speaks again.
//! 4. **Faults latch** — a sensor limit, e-stop, or reported hardware fault
//!    forces all outputs to zero and the driver off *immediately*, ignores
//!    every command, and stays that way until [`Governor::clear_fault`] is
//!    called with healthy sensor readings.
//! 5. **Thermal budget** — a leaky-bucket duty integrator derates sustained
//!    high intensity to `limits.heat_derate` so the motor and the surface in
//!    contact with skin cannot heat indefinitely.

use crate::motion::AxisPlanner;
use crate::tcode::{AxisKind, Command, DeviceCommand, Modifier};
use crate::value::Fraction;

/// Number of vibration channels this device drives.
pub const VIBE_CHANNELS: usize = 2;
/// Number of linear (stroke) channels this device drives.
pub const LINEAR_CHANNELS: usize = 1;

/// TCode axis list returned for `D2`, matching the channel constants above.
pub const AXIS_LIST: &str = "V0 Vibe0\nV1 Vibe1\nL0 Stroke";

/// Thermal duty budget. Heat accumulates as `intensity_raw * dt_ms` and
/// drains at `cool_per_ms` per millisecond; the equilibrium intensity is
/// therefore `cool_per_ms` raw units.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HeatBudget {
    /// Accumulated heat at which derating starts.
    pub limit: u64,
    /// Heat drained per millisecond regardless of intensity.
    pub cool_per_ms: u64,
    /// Ceiling applied while derated. Derating ends at `limit / 2`.
    pub derate: Fraction,
}

/// All tunable ceilings. Construct with [`Limits::validated`] so invalid
/// combinations are rejected at boot rather than discovered under load.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    /// Hard ceiling on any vibration channel.
    pub max_vibe: Fraction,
    /// Max rise per millisecond for vibration, in raw units (10000 = full).
    pub vibe_slew_per_ms: u16,
    /// Max change per millisecond for linear axes, in raw units.
    pub linear_slew_per_ms: u16,
    /// Silence from the host after which outputs coast to safe.
    pub link_timeout_ms: u32,
    /// Thermal duty budget.
    pub heat: HeatBudget,
    /// Fault above this temperature, in tenths of a degree Celsius.
    pub max_temperature_dc: i16,
    /// Fault above this motor current, in milliamps.
    pub max_current_ma: u16,
    /// Fault below this supply voltage, in millivolts.
    pub min_supply_mv: u16,
    /// Largest `dt` a single tick may integrate; longer gaps are clamped so a
    /// stalled scheduler cannot produce a huge jump.
    pub max_tick_ms: u32,
}

/// Why a [`Limits`] value was rejected.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LimitsError {
    /// A slew rate of zero would freeze the axis forever.
    ZeroSlew,
    /// A zero link timeout would coast on every tick.
    ZeroLinkTimeout,
    /// `heat.derate` must not exceed `max_vibe`.
    DerateAboveCeiling,
    /// `max_tick_ms` must be at least 1.
    ZeroMaxTick,
}

impl Limits {
    /// Conservative defaults for a small ERM/LRA vibration motor in a
    /// body-contact enclosure powered from 5 V USB.
    pub const DEFAULT: Self = Self {
        max_vibe: Fraction::saturating(8_000),
        vibe_slew_per_ms: 20,   // 0 -> 100 % in 500 ms
        linear_slew_per_ms: 50, // full stroke in >= 200 ms
        link_timeout_ms: 2_000,
        heat: HeatBudget {
            // Roughly ten minutes at full intensity above the 30 % baseline.
            limit: 7_000 * 600_000,
            cool_per_ms: 3_000,
            derate: Fraction::saturating(4_000),
        },
        max_temperature_dc: 420, // 42.0 C at the skin-contact surface
        max_current_ma: 1_500,
        min_supply_mv: 4_000,
        max_tick_ms: 250,
    };

    /// Check the invariants the governor relies on.
    ///
    /// # Errors
    /// Returns the first violated invariant.
    pub const fn validated(self) -> Result<Self, LimitsError> {
        if self.vibe_slew_per_ms == 0 || self.linear_slew_per_ms == 0 {
            return Err(LimitsError::ZeroSlew);
        }
        if self.link_timeout_ms == 0 {
            return Err(LimitsError::ZeroLinkTimeout);
        }
        if self.heat.derate.raw() > self.max_vibe.raw() {
            return Err(LimitsError::DerateAboveCeiling);
        }
        if self.max_tick_ms == 0 {
            return Err(LimitsError::ZeroMaxTick);
        }
        Ok(self)
    }
}

/// Latched fault causes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fault {
    /// Temperature sensor above `max_temperature_dc`.
    OverTemperature,
    /// Motor current above `max_current_ma`.
    OverCurrent,
    /// Supply below `min_supply_mv` (brown-out makes driver behaviour undefined).
    UnderVoltage,
    /// Local emergency-stop input.
    EmergencyStop,
    /// The firmware reported a hardware fault (driver nFAULT, watchdog reset, ...).
    Hardware,
}

/// Why outputs are coasting toward safe.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CoastReason {
    /// No command within `link_timeout_ms`.
    LinkTimeout,
    /// Transport reported disconnection.
    LinkDown,
    /// Host sent `DSTOP`.
    StopCommand,
}

/// Governor state.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    /// Powered up, nothing commanded yet. Outputs zero, driver disabled.
    Idle,
    /// Following host commands.
    Active,
    /// Ramping to safe; resumes on the next move command.
    Coasting(CoastReason),
    /// Latched. Outputs zero, driver disabled, commands ignored.
    Faulted(Fault),
}

/// Latest sensor readings. `None` means "no sensor fitted"; a fitted sensor
/// that fails to read should be reported as a [`Fault::Hardware`] instead.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Sensors {
    /// Surface/motor temperature in tenths of a degree Celsius.
    pub temperature_dc: Option<i16>,
    /// Motor current in milliamps.
    pub motor_current_ma: Option<u16>,
    /// Supply voltage in millivolts.
    pub supply_mv: Option<u16>,
}

impl Sensors {
    /// The first limit a reading violates, if any.
    #[must_use]
    pub fn violation(&self, limits: &Limits) -> Option<Fault> {
        if self
            .temperature_dc
            .is_some_and(|t| t > limits.max_temperature_dc)
        {
            return Some(Fault::OverTemperature);
        }
        if self
            .motor_current_ma
            .is_some_and(|i| i > limits.max_current_ma)
        {
            return Some(Fault::OverCurrent);
        }
        if self.supply_mv.is_some_and(|v| v < limits.min_supply_mv) {
            return Some(Fault::UnderVoltage);
        }
        None
    }
}

/// Actuator setpoints for one control period.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Outputs {
    /// Vibration intensities.
    pub vibe: [Fraction; VIBE_CHANNELS],
    /// Linear positions.
    pub linear: [Fraction; LINEAR_CHANNELS],
    /// Whether the motor driver's enable/sleep pin may be asserted. `false`
    /// whenever every output is zero, so an idle device is hard-off.
    pub driver_enable: bool,
}

impl Outputs {
    /// Everything off.
    pub const OFF: Self = Self {
        vibe: [Fraction::ZERO; VIBE_CHANNELS],
        linear: [Fraction::ZERO; LINEAR_CHANNELS],
        driver_enable: false,
    };

    /// True when every channel is at zero.
    #[must_use]
    pub fn is_silent(&self) -> bool {
        self.vibe
            .iter()
            .chain(self.linear.iter())
            .all(|f| *f == Fraction::ZERO)
    }
}

/// What the governor did with a command.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Disposition {
    /// Accepted (possibly clamped).
    Applied,
    /// A query the firmware should answer; see [`DeviceCommand::reply`] and
    /// [`AXIS_LIST`].
    Reply(DeviceCommand),
    /// Dropped because the governor is faulted.
    IgnoredFaulted,
    /// Dropped because the axis is not fitted on this device.
    IgnoredUnsupportedAxis,
}

/// The safety governor. See the [module docs](self) for the guarantees.
#[derive(Clone, Debug)]
pub struct Governor {
    limits: Limits,
    state: State,
    vibe: [AxisPlanner; VIBE_CHANNELS],
    linear: [AxisPlanner; LINEAR_CHANNELS],
    heat: [u64; VIBE_CHANNELS],
    derated: [bool; VIBE_CHANNELS],
    last_command_ms: u64,
    last_tick_ms: Option<u64>,
    outputs: Outputs,
}

impl Governor {
    /// A governor in [`State::Idle`] with all outputs off.
    #[must_use]
    pub const fn new(limits: Limits) -> Self {
        Self {
            limits,
            state: State::Idle,
            vibe: [AxisPlanner::new(Fraction::ZERO); VIBE_CHANNELS],
            linear: [AxisPlanner::new(Fraction::ZERO); LINEAR_CHANNELS],
            heat: [0; VIBE_CHANNELS],
            derated: [false; VIBE_CHANNELS],
            last_command_ms: 0,
            last_tick_ms: None,
            outputs: Outputs::OFF,
        }
    }

    /// Current state.
    #[must_use]
    pub const fn state(&self) -> State {
        self.state
    }

    /// The limits in force.
    #[must_use]
    pub const fn limits(&self) -> &Limits {
        &self.limits
    }

    /// Outputs from the most recent tick.
    #[must_use]
    pub const fn outputs(&self) -> Outputs {
        self.outputs
    }

    /// Whether a channel is currently thermally derated.
    #[must_use]
    pub fn is_derated(&self, vibe_channel: usize) -> bool {
        self.derated.get(vibe_channel).copied().unwrap_or(false)
    }

    /// Feed a parsed command received at `now_ms`.
    pub fn handle(&mut self, cmd: &Command, now_ms: u64) -> Disposition {
        if let State::Faulted(_) = self.state {
            return Disposition::IgnoredFaulted;
        }
        match *cmd {
            Command::Device(DeviceCommand::Stop) => {
                self.touch(now_ms);
                self.coast(CoastReason::StopCommand);
                Disposition::Applied
            }
            Command::Device(query) => {
                self.touch(now_ms);
                Disposition::Reply(query)
            }
            Command::Move {
                axis,
                target,
                modifier,
            } => {
                let idx = usize::from(axis.index);
                let planner = match axis.kind {
                    AxisKind::Vibrate => self.vibe.get_mut(idx),
                    AxisKind::Linear => self.linear.get_mut(idx),
                    AxisKind::Rotate | AxisKind::Aux => None,
                };
                let Some(planner) = planner else {
                    return Disposition::IgnoredUnsupportedAxis;
                };
                let target = if axis.kind == AxisKind::Vibrate {
                    target.min(self.limits.max_vibe)
                } else {
                    target
                };
                planner.command(target, modifier);
                self.touch(now_ms);
                self.state = State::Active;
                Disposition::Applied
            }
        }
    }

    /// The transport lost the host (USB suspend, DTR dropped, socket closed).
    pub fn link_down(&mut self) {
        if !matches!(self.state, State::Faulted(_)) {
            self.coast(CoastReason::LinkDown);
        }
    }

    /// Latch a fault. Takes effect on the next [`Self::tick`]; the firmware
    /// should also cut the driver enable line directly if it can.
    pub fn report(&mut self, fault: Fault) {
        if !matches!(self.state, State::Faulted(_)) {
            self.state = State::Faulted(fault);
        }
        self.kill();
    }

    /// Attempt to clear a latched fault after a deliberate local action.
    /// Succeeds only if `sensors` are within limits. Returns the new state.
    pub fn clear_fault(&mut self, sensors: &Sensors) -> State {
        if let State::Faulted(_) = self.state {
            if sensors.violation(&self.limits).is_none() {
                self.state = State::Idle;
                self.heat = [0; VIBE_CHANNELS];
                self.derated = [false; VIBE_CHANNELS];
                self.kill();
            }
        }
        self.state
    }

    /// Advance to `now_ms` and compute the outputs for this period.
    pub fn tick(&mut self, now_ms: u64, sensors: &Sensors) -> Outputs {
        let dt = self.advance_clock(now_ms);

        if let Some(fault) = sensors.violation(&self.limits) {
            self.report(fault);
        }
        if let State::Faulted(_) = self.state {
            self.kill();
            return self.outputs;
        }

        if self.state == State::Active
            && now_ms.saturating_sub(self.last_command_ms) > u64::from(self.limits.link_timeout_ms)
        {
            self.coast(CoastReason::LinkTimeout);
        }

        if dt == 0 {
            return self.outputs;
        }

        let mut out = Outputs::OFF;

        let vibe_slew = self.limits.vibe_slew_per_ms;
        let heat = self.limits.heat;
        for (((planner, out_v), acc), derated) in self
            .vibe
            .iter_mut()
            .zip(out.vibe.iter_mut())
            .zip(self.heat.iter_mut())
            .zip(self.derated.iter_mut())
        {
            let mut level = planner.step(dt, vibe_slew);

            // Leaky-bucket thermal integrator.
            let gained = u64::from(level.raw()).saturating_mul(u64::from(dt));
            let lost = heat.cool_per_ms.saturating_mul(u64::from(dt));
            *acc = acc.saturating_add(gained).saturating_sub(lost);
            if *acc > heat.limit {
                *derated = true;
            } else if *acc < heat.limit / 2 {
                *derated = false;
            }
            if *derated {
                level = level.min(heat.derate);
            }

            // Belt and braces: the ceiling is applied at command time too.
            *out_v = level.min(self.limits.max_vibe);
        }

        let linear_slew = self.limits.linear_slew_per_ms;
        for (planner, out_l) in self.linear.iter_mut().zip(out.linear.iter_mut()) {
            *out_l = planner.step(dt, linear_slew);
        }

        out.driver_enable = !out.is_silent();
        self.outputs = out;
        out
    }

    fn touch(&mut self, now_ms: u64) {
        self.last_command_ms = now_ms;
    }

    /// Steer toward safe: vibration to zero, linear holds position.
    ///
    /// Uses an `Immediate` command rather than `retarget` so that a slow
    /// `I`/`S` modifier chosen by the host cannot stretch the ramp-down;
    /// only the governor's own slew ceiling bounds it.
    fn coast(&mut self, reason: CoastReason) {
        self.state = State::Coasting(reason);
        for p in &mut self.vibe {
            p.command(Fraction::ZERO, Modifier::Immediate);
        }
        for p in &mut self.linear {
            let hold = p.current();
            p.command(hold, Modifier::Immediate);
        }
    }

    /// Immediate hard-off.
    fn kill(&mut self) {
        for p in self.vibe.iter_mut().chain(self.linear.iter_mut()) {
            p.force(Fraction::ZERO);
        }
        self.outputs = Outputs::OFF;
    }

    /// Returns clamped `dt` since the previous tick (0 on the first call or
    /// if time went backwards).
    fn advance_clock(&mut self, now_ms: u64) -> u32 {
        let dt = match self.last_tick_ms {
            None => 0,
            Some(prev) => now_ms.saturating_sub(prev),
        };
        self.last_tick_ms = Some(now_ms);
        let dt = u32::try_from(dt).unwrap_or(u32::MAX);
        dt.min(self.limits.max_tick_ms)
    }
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::indexing_slicing,
    clippy::arithmetic_side_effects,
    clippy::unreachable,
    clippy::panic
)]
mod tests {
    use super::*;
    use crate::tcode::Axis;

    fn f(raw: u16) -> Fraction {
        Fraction::new(raw).unwrap()
    }

    fn vibe(index: u8, raw: u16, modifier: Modifier) -> Command {
        Command::Move {
            axis: Axis {
                kind: AxisKind::Vibrate,
                index,
            },
            target: f(raw),
            modifier,
        }
    }

    fn run(g: &mut Governor, from_ms: u64, to_ms: u64, step: u64) -> Outputs {
        let mut t = from_ms;
        let mut out = g.outputs();
        while t <= to_ms {
            out = g.tick(t, &Sensors::default());
            t += step;
        }
        out
    }

    #[test]
    fn defaults_validate() {
        assert_eq!(Limits::DEFAULT.validated(), Ok(Limits::DEFAULT));
        let mut bad = Limits::DEFAULT;
        bad.vibe_slew_per_ms = 0;
        assert_eq!(bad.validated(), Err(LimitsError::ZeroSlew));
        bad = Limits::DEFAULT;
        bad.heat.derate = Fraction::MAX;
        assert_eq!(bad.validated(), Err(LimitsError::DerateAboveCeiling));
    }

    #[test]
    fn idle_until_commanded_then_ceiling_and_slew_apply() {
        let mut g = Governor::new(Limits::DEFAULT);
        assert_eq!(g.tick(0, &Sensors::default()), Outputs::OFF);
        assert_eq!(g.state(), State::Idle);

        assert_eq!(
            g.handle(&vibe(0, 9999, Modifier::Immediate), 0),
            Disposition::Applied
        );
        assert_eq!(g.state(), State::Active);
        let out = g.tick(1, &Sensors::default());
        assert_eq!(out.vibe[0], f(20)); // 20 raw units per ms
        assert!(out.driver_enable);
        let out = run(&mut g, 2, 2000, 1);
        assert_eq!(out.vibe[0], Limits::DEFAULT.max_vibe);
    }

    #[test]
    fn stop_command_ramps_down_and_disables_driver() {
        let mut g = Governor::new(Limits::DEFAULT);
        g.handle(&vibe(0, 5000, Modifier::Immediate), 0);
        run(&mut g, 0, 1000, 1);
        g.handle(&Command::Device(DeviceCommand::Stop), 1000);
        assert_eq!(g.state(), State::Coasting(CoastReason::StopCommand));
        let out = run(&mut g, 1001, 2000, 1);
        assert_eq!(out, Outputs::OFF);
        // Next move resumes.
        g.handle(&vibe(0, 1000, Modifier::Immediate), 2001);
        assert_eq!(g.state(), State::Active);
    }

    #[test]
    fn link_timeout_coasts() {
        let mut g = Governor::new(Limits::DEFAULT);
        g.handle(&vibe(1, 5000, Modifier::Immediate), 0);
        run(&mut g, 0, 2000, 10);
        assert_eq!(g.state(), State::Active);
        run(&mut g, 2010, 2010, 1);
        assert_eq!(g.state(), State::Coasting(CoastReason::LinkTimeout));
        let out = run(&mut g, 2020, 3000, 10);
        assert_eq!(out.vibe[1], Fraction::ZERO);
        assert!(!out.driver_enable);
    }

    #[test]
    fn link_down_holds_linear_and_zeroes_vibe() {
        let mut g = Governor::new(Limits::DEFAULT);
        let stroke = Command::Move {
            axis: Axis {
                kind: AxisKind::Linear,
                index: 0,
            },
            target: f(7000),
            modifier: Modifier::Immediate,
        };
        g.handle(&stroke, 0);
        g.handle(&vibe(0, 5000, Modifier::Immediate), 0);
        run(&mut g, 0, 1000, 1);
        g.link_down();
        let out = run(&mut g, 1001, 2000, 1);
        assert_eq!(out.vibe[0], Fraction::ZERO);
        assert_eq!(out.linear[0], f(7000));
        assert!(out.driver_enable); // linear still holding
    }

    #[test]
    fn sensor_fault_latches_and_ignores_commands() {
        let mut g = Governor::new(Limits::DEFAULT);
        g.handle(&vibe(0, 5000, Modifier::Immediate), 0);
        run(&mut g, 0, 500, 1);
        let hot = Sensors {
            temperature_dc: Some(425),
            ..Sensors::default()
        };
        assert_eq!(g.tick(501, &hot), Outputs::OFF);
        assert_eq!(g.state(), State::Faulted(Fault::OverTemperature));
        assert_eq!(
            g.handle(&vibe(0, 5000, Modifier::Immediate), 502),
            Disposition::IgnoredFaulted
        );
        assert_eq!(run(&mut g, 503, 5000, 1), Outputs::OFF);
        // Still hot: cannot clear.
        assert_eq!(g.clear_fault(&hot), State::Faulted(Fault::OverTemperature));
        // Cooled: clears to Idle, outputs stay off until commanded.
        assert_eq!(g.clear_fault(&Sensors::default()), State::Idle);
        assert_eq!(g.tick(5001, &Sensors::default()), Outputs::OFF);
    }

    #[test]
    fn reported_fault_takes_effect_immediately() {
        let mut g = Governor::new(Limits::DEFAULT);
        g.handle(&vibe(0, 5000, Modifier::Immediate), 0);
        run(&mut g, 0, 500, 1);
        assert!(g.outputs().driver_enable);
        g.report(Fault::EmergencyStop);
        assert_eq!(g.outputs(), Outputs::OFF);
        assert_eq!(g.state(), State::Faulted(Fault::EmergencyStop));
        // A later, different fault does not overwrite the first cause.
        g.report(Fault::Hardware);
        assert_eq!(g.state(), State::Faulted(Fault::EmergencyStop));
    }

    #[test]
    fn other_sensor_faults() {
        let l = Limits::DEFAULT;
        let s = Sensors {
            motor_current_ma: Some(l.max_current_ma + 1),
            ..Sensors::default()
        };
        assert_eq!(s.violation(&l), Some(Fault::OverCurrent));
        let s = Sensors {
            supply_mv: Some(l.min_supply_mv - 1),
            ..Sensors::default()
        };
        assert_eq!(s.violation(&l), Some(Fault::UnderVoltage));
    }

    #[test]
    fn thermal_budget_derates_and_recovers() {
        let mut limits = Limits::DEFAULT;
        limits.heat = HeatBudget {
            limit: 5_000 * 1_000, // one second at 50 % above the baseline
            cool_per_ms: 0,
            derate: f(1000),
        };
        let mut g = Governor::new(limits);
        g.handle(&vibe(0, 5000, Modifier::Immediate), 0);
        // Keep the link alive while integrating.
        let mut t = 0;
        let mut out = Outputs::OFF;
        while t <= 2000 {
            g.handle(&vibe(0, 5000, Modifier::Immediate), t);
            out = g.tick(t, &Sensors::default());
            t += 1;
        }
        assert!(g.is_derated(0));
        assert_eq!(out.vibe[0], f(1000));
        assert!(!g.is_derated(1));
        // Clearing a fault resets the budget.
        g.report(Fault::Hardware);
        g.clear_fault(&Sensors::default());
        assert!(!g.is_derated(0));
    }

    #[test]
    fn unsupported_axes_are_ignored() {
        let mut g = Governor::new(Limits::DEFAULT);
        let rot = Command::Move {
            axis: Axis {
                kind: AxisKind::Rotate,
                index: 0,
            },
            target: f(1),
            modifier: Modifier::Immediate,
        };
        assert_eq!(g.handle(&rot, 0), Disposition::IgnoredUnsupportedAxis);
        assert_eq!(
            g.handle(&vibe(9, 1, Modifier::Immediate), 0),
            Disposition::IgnoredUnsupportedAxis
        );
        assert_eq!(g.state(), State::Idle);
        assert_eq!(
            g.handle(&Command::Device(DeviceCommand::Identify), 0),
            Disposition::Reply(DeviceCommand::Identify)
        );
    }

    #[test]
    fn huge_time_gap_is_clamped() {
        let mut g = Governor::new(Limits::DEFAULT);
        g.handle(&vibe(0, 8000, Modifier::Immediate), 0);
        g.tick(0, &Sensors::default());
        // Keep the link alive, then jump the clock a long way.
        g.handle(&vibe(0, 8000, Modifier::Immediate), 1_000_000);
        let out = g.tick(1_000_000, &Sensors::default());
        // dt clamped to max_tick_ms (250) * slew (20) = 5000.
        assert_eq!(out.vibe[0], f(5000));
        // Time going backwards is a zero-length tick.
        assert_eq!(g.tick(5, &Sensors::default()).vibe[0], f(5000));
    }
}
