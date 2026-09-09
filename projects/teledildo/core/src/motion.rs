//! Per-axis motion planning under a hard slew ceiling.

use crate::tcode::Modifier;
use crate::value::Fraction;

/// Tracks one axis's commanded target and interpolates the live setpoint
/// toward it.
///
/// The planner honours the TCode `I` (interval) and `S` (speed) modifiers but
/// never moves faster than the `max_step_per_ms` passed to [`Self::step`],
/// which is how the governor imposes a slew limit the host cannot override.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AxisPlanner {
    current: Fraction,
    target: Fraction,
    /// Milliseconds left in an `I` move; 0 when not in a timed move.
    remaining_ms: u32,
    /// Raw units per second for an `S` move; 0 when unlimited.
    rate_per_s: u32,
}

impl Default for AxisPlanner {
    fn default() -> Self {
        Self::new(Fraction::ZERO)
    }
}

impl AxisPlanner {
    /// A planner resting at `start`.
    #[must_use]
    pub const fn new(start: Fraction) -> Self {
        Self {
            current: start,
            target: start,
            remaining_ms: 0,
            rate_per_s: 0,
        }
    }

    /// Live setpoint.
    #[must_use]
    pub const fn current(&self) -> Fraction {
        self.current
    }

    /// Commanded target.
    #[must_use]
    pub const fn target(&self) -> Fraction {
        self.target
    }

    /// Whether the setpoint has reached the target.
    #[must_use]
    pub fn is_settled(&self) -> bool {
        self.current == self.target
    }

    /// Accept a new target with a TCode timing modifier.
    pub fn command(&mut self, target: Fraction, modifier: Modifier) {
        self.target = target;
        match modifier {
            Modifier::Immediate => {
                self.remaining_ms = 0;
                self.rate_per_s = 0;
            }
            Modifier::Interval { millis } => {
                self.remaining_ms = millis;
                self.rate_per_s = 0;
            }
            Modifier::Speed { per_second } => {
                self.remaining_ms = 0;
                self.rate_per_s = per_second;
            }
        }
    }

    /// Jump both setpoint and target to `value` (used for hard stops).
    pub fn force(&mut self, value: Fraction) {
        self.current = value;
        self.target = value;
        self.remaining_ms = 0;
        self.rate_per_s = 0;
    }

    /// Retarget without changing timing (used to steer toward safe).
    pub fn retarget(&mut self, target: Fraction) {
        self.target = target;
    }

    /// Advance by `dt_ms`, moving at most `max_step_per_ms * dt_ms` raw units.
    /// Returns the new setpoint.
    pub fn step(&mut self, dt_ms: u32, max_step_per_ms: u16) -> Fraction {
        if dt_ms == 0 {
            return self.current;
        }
        let distance = u32::from(self.current.abs_diff(self.target));
        if distance == 0 {
            self.remaining_ms = 0;
            return self.current;
        }

        // Requested step from the modifier, before the safety ceiling.
        let requested: u32 = if self.remaining_ms > 0 {
            // Cover `distance` over `remaining_ms`, rounding up so we land
            // exactly on time rather than one tick late.
            let num = distance.saturating_mul(dt_ms);
            let den = self.remaining_ms.max(1);
            num.checked_div(den).map_or(distance, |q| {
                if num.checked_rem(den).unwrap_or(0) > 0 {
                    q.saturating_add(1)
                } else {
                    q
                }
            })
        } else if self.rate_per_s > 0 {
            self.rate_per_s.saturating_mul(dt_ms) / 1000
        } else {
            distance
        };

        // Hard ceiling from the governor.
        let ceiling = u32::from(max_step_per_ms).saturating_mul(dt_ms);
        let step = requested.min(ceiling).min(distance);
        let step = u16::try_from(step).unwrap_or(u16::MAX);

        self.current = if self.target > self.current {
            self.current.saturating_add(step)
        } else {
            self.current.saturating_sub(step)
        };
        self.remaining_ms = self.remaining_ms.saturating_sub(dt_ms);
        self.current
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

    fn f(raw: u16) -> Fraction {
        Fraction::new(raw).unwrap()
    }

    #[test]
    fn immediate_move_is_slew_limited() {
        let mut p = AxisPlanner::new(Fraction::ZERO);
        p.command(f(9999), Modifier::Immediate);
        assert_eq!(p.step(1, 20), f(20));
        assert_eq!(p.step(10, 20), f(220));
        // Large dt saturates onto the target, never beyond.
        assert_eq!(p.step(10_000, 20), f(9999));
        assert!(p.is_settled());
    }

    #[test]
    fn interval_move_lands_on_time() {
        let mut p = AxisPlanner::new(Fraction::ZERO);
        p.command(f(1000), Modifier::Interval { millis: 100 });
        for _ in 0..100 {
            p.step(1, u16::MAX);
        }
        assert_eq!(p.current(), f(1000));
    }

    #[test]
    fn interval_move_never_exceeds_ceiling() {
        let mut p = AxisPlanner::new(Fraction::ZERO);
        p.command(f(9999), Modifier::Interval { millis: 1 });
        assert_eq!(p.step(1, 50), f(50));
    }

    #[test]
    fn speed_move_uses_rate() {
        let mut p = AxisPlanner::new(f(5000));
        p.command(f(0), Modifier::Speed { per_second: 1000 });
        assert_eq!(p.step(100, u16::MAX), f(4900));
        assert_eq!(p.step(100, 5), f(4800)); // rate (100) below ceiling (500)
        p.command(f(0), Modifier::Speed { per_second: 10_000 });
        assert_eq!(p.step(100, 5), f(4300)); // ceiling 5*100 = 500 wins
    }

    #[test]
    fn force_and_retarget() {
        let mut p = AxisPlanner::new(f(5000));
        p.command(f(9999), Modifier::Interval { millis: 500 });
        p.retarget(Fraction::ZERO);
        assert_eq!(p.target(), Fraction::ZERO);
        p.force(f(123));
        assert_eq!(p.current(), f(123));
        assert!(p.is_settled());
        assert_eq!(p.step(0, 10), f(123));
    }
}
