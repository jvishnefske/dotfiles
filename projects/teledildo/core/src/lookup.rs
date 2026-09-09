//! Integer helpers for turning ADC counts into engineering units.
//!
//! Kept here rather than in the firmware so the conversions that feed the
//! governor's fault thresholds are host-testable and covered by the same
//! no-panic lints.

/// Linear interpolation over a table of `(x, y)` points with strictly
/// increasing `x`. Returns `None` if `x` is outside the table (which callers
/// should treat as a sensor fault: open or shorted probe).
#[must_use]
pub fn interpolate(table: &[(u16, i16)], x: u16) -> Option<i16> {
    let (&(x0, y0), _) = table.split_first()?;
    let (&(xn, yn), _) = table.split_last()?;
    if x < x0 || x > xn {
        return None;
    }
    if x == xn {
        return Some(yn);
    }
    if x == x0 {
        return Some(y0);
    }
    // Find the segment [lo, hi] containing x.
    for pair in table.windows(2) {
        let [(xa, ya), (xb, yb)] = pair else {
            return None;
        };
        let (xa, ya, xb, yb) = (*xa, *ya, *xb, *yb);
        if xa <= x && x <= xb {
            let span = i32::from(xb).checked_sub(i32::from(xa))?;
            if span <= 0 {
                return None; // not strictly increasing
            }
            let dx = i32::from(x).checked_sub(i32::from(xa))?;
            let dy = i32::from(yb).checked_sub(i32::from(ya))?;
            let delta = dy.checked_mul(dx)?.checked_div(span)?;
            let y = i32::from(ya).checked_add(delta)?;
            return i16::try_from(y).ok();
        }
    }
    None
}

/// Scale a raw ADC count to engineering units: `count * full_scale / max`.
/// Returns `None` if `max` is zero.
#[must_use]
pub fn scale(count: u16, full_scale: u32, max: u16) -> Option<u32> {
    let num = u64::from(count).saturating_mul(u64::from(full_scale));
    let q = num.checked_div(u64::from(max))?;
    u32::try_from(q).ok()
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::indexing_slicing,
    clippy::arithmetic_side_effects
)]
mod tests {
    use super::*;

    const T: &[(u16, i16)] = &[(100, 0), (200, 100), (400, 200)];

    #[test]
    fn interpolates_and_hits_endpoints() {
        assert_eq!(interpolate(T, 100), Some(0));
        assert_eq!(interpolate(T, 150), Some(50));
        assert_eq!(interpolate(T, 200), Some(100));
        assert_eq!(interpolate(T, 300), Some(150));
        assert_eq!(interpolate(T, 400), Some(200));
    }

    #[test]
    fn out_of_range_is_none() {
        assert_eq!(interpolate(T, 99), None);
        assert_eq!(interpolate(T, 401), None);
        assert_eq!(interpolate(&[], 5), None);
        assert_eq!(interpolate(&[(7, 7)], 7), Some(7));
        assert_eq!(interpolate(&[(200, 0), (100, 10)], 150), None);
    }

    #[test]
    fn scales() {
        assert_eq!(scale(4095, 3300, 4095), Some(3300));
        assert_eq!(scale(0, 3300, 4095), Some(0));
        assert_eq!(scale(2048, 9900, 4095), Some(4951));
        assert_eq!(scale(1, 1, 0), None);
    }
}
