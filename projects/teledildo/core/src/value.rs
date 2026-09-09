//! Fixed-point magnitude type shared by the parser, planner and governor.

/// A magnitude in the TCode sense: a fraction of full scale, in units of
/// 1/10000. Valid values are `0..=9999` (`0.0000` to `0.9999`).
///
/// The type guarantees its invariant at construction, so downstream code can
/// scale it into a PWM compare value without a range check.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Fraction(u16);

impl Fraction {
    /// Number of steps in full scale (exclusive upper bound of the raw value).
    pub const SCALE: u16 = 10_000;
    /// Zero.
    pub const ZERO: Self = Self(0);
    /// Half scale (`0.5000`).
    pub const HALF: Self = Self(5_000);
    /// Largest representable value (`0.9999`).
    pub const MAX: Self = Self(9_999);

    /// Construct from a raw value, rejecting anything `>= SCALE`.
    #[must_use]
    pub const fn new(raw: u16) -> Option<Self> {
        if raw < Self::SCALE {
            Some(Self(raw))
        } else {
            None
        }
    }

    /// Construct from a raw value, clamping into range.
    #[must_use]
    pub const fn saturating(raw: u16) -> Self {
        if raw > Self::MAX.0 {
            Self::MAX
        } else {
            Self(raw)
        }
    }

    /// Construct from a wide raw value, clamping into range.
    #[must_use]
    pub fn saturating_u32(raw: u32) -> Self {
        u16::try_from(raw).map_or(Self::MAX, Self::saturating)
    }

    /// The raw value in `0..=9999`.
    #[must_use]
    pub const fn raw(self) -> u16 {
        self.0
    }

    /// Parse a TCode magnitude from 1 to 4 ASCII digits.
    ///
    /// TCode magnitudes are the digits *after* the decimal point, so `"5"`
    /// is `0.5`, `"05"` is `0.05` and `"0500"` is `0.05`. More than four
    /// digits, an empty slice, or a non-digit byte is rejected.
    #[must_use]
    pub fn from_tcode_digits(digits: &[u8]) -> Option<Self> {
        if digits.is_empty() || digits.len() > 4 {
            return None;
        }
        let mut value: u16 = 0;
        for &d in digits {
            if !d.is_ascii_digit() {
                return None;
            }
            // d is b'0'..=b'9' here, so this cannot underflow.
            let digit = u16::from(d.wrapping_sub(b'0'));
            value = value.checked_mul(10)?.checked_add(digit)?;
        }
        // Left-align: pad missing digits with zeros.
        let mut pad = 4usize.saturating_sub(digits.len());
        while pad > 0 {
            value = value.checked_mul(10)?;
            pad = pad.saturating_sub(1);
        }
        Self::new(value)
    }

    /// Scale into `0..=top`, e.g. a PWM compare value for a counter that
    /// wraps at `top`. `ZERO` maps to `0`; `MAX` (0.9999) maps to `top` or
    /// one step below it, depending on rounding.
    #[must_use]
    pub fn scale_to(self, top: u16) -> u16 {
        // (raw * (top + 1)) / SCALE <= (9999 * 65536) / 10000 < 65536, so the
        // narrowing conversion cannot fail; the fallback is defensive only.
        let span = u32::from(top).saturating_add(1);
        let scaled = u32::from(self.0).saturating_mul(span) / 10_000;
        u16::try_from(scaled).map_or(top, |v| v.min(top))
    }

    /// The smaller of two fractions.
    #[must_use]
    pub fn min(self, other: Self) -> Self {
        if other < self {
            other
        } else {
            self
        }
    }

    /// Absolute difference in raw units.
    #[must_use]
    pub const fn abs_diff(self, other: Self) -> u16 {
        self.0.abs_diff(other.0)
    }

    /// `self + delta`, clamped to `MAX`.
    #[must_use]
    pub const fn saturating_add(self, delta: u16) -> Self {
        Self::saturating(self.0.saturating_add(delta))
    }

    /// `self - delta`, clamped to `ZERO`.
    #[must_use]
    pub const fn saturating_sub(self, delta: u16) -> Self {
        Self(self.0.saturating_sub(delta))
    }

    /// Approximate percentage (integer, truncating), handy for logging.
    #[must_use]
    pub fn percent(self) -> u8 {
        u8::try_from(self.0 / 100).unwrap_or(u8::MAX)
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
    use super::Fraction;

    #[test]
    fn digits_are_left_aligned() {
        assert_eq!(Fraction::from_tcode_digits(b"5"), Fraction::new(5000));
        assert_eq!(Fraction::from_tcode_digits(b"05"), Fraction::new(500));
        assert_eq!(Fraction::from_tcode_digits(b"0500"), Fraction::new(500));
        assert_eq!(Fraction::from_tcode_digits(b"9999"), Some(Fraction::MAX));
        assert_eq!(Fraction::from_tcode_digits(b"0000"), Some(Fraction::ZERO));
    }

    #[test]
    fn digits_reject_bad_input() {
        assert_eq!(Fraction::from_tcode_digits(b""), None);
        assert_eq!(Fraction::from_tcode_digits(b"12345"), None);
        assert_eq!(Fraction::from_tcode_digits(b"12a"), None);
        assert_eq!(Fraction::from_tcode_digits(b"-1"), None);
    }

    #[test]
    fn scale_hits_endpoints() {
        assert_eq!(Fraction::ZERO.scale_to(4999), 0);
        assert_eq!(Fraction::MAX.scale_to(4999), 4999);
        assert_eq!(Fraction::HALF.scale_to(4999), 2500);
        assert_eq!(Fraction::MAX.scale_to(u16::MAX), 65_529);
        assert_eq!(Fraction::MAX.scale_to(0), 0);
    }

    #[test]
    fn construction_bounds() {
        assert_eq!(Fraction::new(10_000), None);
        assert_eq!(Fraction::saturating(60_000), Fraction::MAX);
        assert_eq!(Fraction::saturating_u32(u32::MAX), Fraction::MAX);
        assert_eq!(Fraction::MAX.saturating_add(1), Fraction::MAX);
        assert_eq!(Fraction::ZERO.saturating_sub(1), Fraction::ZERO);
        assert_eq!(Fraction::MAX.percent(), 99);
    }
}
