//! Zero-allocation parser for the TCode v0.3 text protocol.
//!
//! A TCode line is a sequence of whitespace-separated tokens terminated by
//! `\n`. Each token is either an axis command such as `L0500I1000`
//! (`axis` `magnitude` [`modifier` `value`]) or a device command such as
//! `D0` or `DSTOP`. Letters are case-insensitive.
//!
//! ```text
//! L0500        move linear axis 0 to 0.5000 immediately (slew-limited)
//! V09999I2000  ramp vibration axis 0 to 0.9999 over 2000 ms
//! R1250S500    move rotation axis 1 to 0.25 at 500 units/s
//! DSTOP        stop all motion
//! ```
//!
//! The parser never panics on any input (see `proofs::parse_never_panics`)
//! and reports each malformed token individually so a bad token cannot mask
//! good ones on the same line.

use crate::value::Fraction;

/// Axis families defined by TCode.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum AxisKind {
    /// `L` — linear position.
    Linear,
    /// `R` — rotation.
    Rotate,
    /// `V` — vibration intensity.
    Vibrate,
    /// `A` — auxiliary (valve, suction, ...).
    Aux,
}

impl AxisKind {
    fn from_letter(letter: u8) -> Option<Self> {
        match letter.to_ascii_uppercase() {
            b'L' => Some(Self::Linear),
            b'R' => Some(Self::Rotate),
            b'V' => Some(Self::Vibrate),
            b'A' => Some(Self::Aux),
            _ => None,
        }
    }

    /// The TCode letter for this family.
    #[must_use]
    pub const fn letter(self) -> u8 {
        match self {
            Self::Linear => b'L',
            Self::Rotate => b'R',
            Self::Vibrate => b'V',
            Self::Aux => b'A',
        }
    }
}

/// An addressed axis: family plus a single-digit index (`0..=9`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Axis {
    /// Axis family.
    pub kind: AxisKind,
    /// Channel within the family, `0..=9`.
    pub index: u8,
}

/// Timing modifier attached to a move.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Modifier {
    /// No modifier: reach the target as fast as the slew limit allows.
    Immediate,
    /// `I<n>`: reach the target in `n` milliseconds.
    Interval {
        /// Duration of the move in milliseconds.
        millis: u32,
    },
    /// `S<n>`: move at `n` raw units (1/10000 of full scale) per second.
    Speed {
        /// Rate in raw units per second.
        per_second: u32,
    },
}

/// `D`-prefixed device commands.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeviceCommand {
    /// `D0` — identify. The device answers `TCode v0.3`.
    Identify,
    /// `D1` — firmware name/version.
    Version,
    /// `D2` — list supported axes.
    ListAxes,
    /// `DSTOP` — halt all motion.
    Stop,
}

/// One parsed TCode token.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    /// Move an axis toward a target magnitude.
    Move {
        /// Which axis.
        axis: Axis,
        /// Target magnitude.
        target: Fraction,
        /// How fast to get there.
        modifier: Modifier,
    },
    /// A device-level command.
    Device(DeviceCommand),
}

/// Why a token was rejected.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ParseError {
    /// First byte is not one of `L R V A D`.
    UnknownPrefix(u8),
    /// Axis letter not followed by a digit.
    MissingIndex,
    /// Magnitude missing, longer than 4 digits, or not digits.
    BadMagnitude,
    /// Modifier letter not `I`/`S`, or its value missing/too long/not digits.
    BadModifier,
    /// `D` followed by something other than `0`, `1`, `2` or `STOP`.
    UnknownDeviceCommand,
    /// Unexpected bytes after an otherwise valid token.
    Trailing,
}

const MAX_MODIFIER_DIGITS: usize = 10; // u32::MAX has 10 digits; overflow is checked

fn split_digits(input: &[u8]) -> (&[u8], &[u8]) {
    let n = input.iter().take_while(|b| b.is_ascii_digit()).count();
    input.split_at(n.min(input.len()))
}

fn parse_u32(digits: &[u8]) -> Option<u32> {
    if digits.is_empty() || digits.len() > MAX_MODIFIER_DIGITS {
        return None;
    }
    let mut value: u32 = 0;
    for &d in digits {
        let digit = u32::from(d.wrapping_sub(b'0'));
        if digit > 9 {
            return None;
        }
        value = value.checked_mul(10)?.checked_add(digit)?;
    }
    Some(value)
}

fn parse_device(rest: &[u8]) -> Result<Command, ParseError> {
    let cmd = match rest {
        b"0" => DeviceCommand::Identify,
        b"1" => DeviceCommand::Version,
        b"2" => DeviceCommand::ListAxes,
        _ if rest.eq_ignore_ascii_case(b"STOP") => DeviceCommand::Stop,
        _ => return Err(ParseError::UnknownDeviceCommand),
    };
    Ok(Command::Device(cmd))
}

fn parse_move(kind: AxisKind, rest: &[u8]) -> Result<Command, ParseError> {
    let (&idx, rest) = rest.split_first().ok_or(ParseError::MissingIndex)?;
    if !idx.is_ascii_digit() {
        return Err(ParseError::MissingIndex);
    }
    let axis = Axis {
        kind,
        index: idx.wrapping_sub(b'0'),
    };
    let (mag, rest) = split_digits(rest);
    let target = Fraction::from_tcode_digits(mag).ok_or(ParseError::BadMagnitude)?;
    let modifier = match rest.split_first() {
        None => Modifier::Immediate,
        Some((&m, rest)) => {
            let (digits, tail) = split_digits(rest);
            if !tail.is_empty() {
                return Err(ParseError::Trailing);
            }
            let value = parse_u32(digits).ok_or(ParseError::BadModifier)?;
            match m.to_ascii_uppercase() {
                b'I' => Modifier::Interval { millis: value },
                b'S' => Modifier::Speed { per_second: value },
                _ => return Err(ParseError::BadModifier),
            }
        }
    };
    Ok(Command::Move {
        axis,
        target,
        modifier,
    })
}

/// Parse a single whitespace-free token.
///
/// # Errors
/// Returns a [`ParseError`] describing the first problem found.
pub fn parse_token(token: &[u8]) -> Result<Command, ParseError> {
    let (&first, rest) = token.split_first().ok_or(ParseError::UnknownPrefix(0))?;
    if first.eq_ignore_ascii_case(&b'D') {
        return parse_device(rest);
    }
    let kind = AxisKind::from_letter(first).ok_or(ParseError::UnknownPrefix(first))?;
    parse_move(kind, rest)
}

/// Iterator over the tokens of one TCode line.
///
/// Whitespace (space, tab, CR, LF) separates tokens; empty runs are skipped.
#[derive(Clone, Debug)]
pub struct Tokens<'a> {
    rest: &'a [u8],
}

fn is_separator(b: u8) -> bool {
    matches!(b, b' ' | b'\t' | b'\r' | b'\n')
}

impl Iterator for Tokens<'_> {
    type Item = Result<Command, ParseError>;

    fn next(&mut self) -> Option<Self::Item> {
        let skip = self.rest.iter().take_while(|&&b| is_separator(b)).count();
        let rest = self.rest.get(skip..).unwrap_or(&[]);
        if rest.is_empty() {
            self.rest = rest;
            return None;
        }
        let len = rest.iter().take_while(|&&b| !is_separator(b)).count();
        let (token, tail) = rest.split_at(len.min(rest.len()));
        self.rest = tail;
        Some(parse_token(token))
    }
}

/// Split a line into tokens and parse each one.
#[must_use]
pub fn parse_line(line: &[u8]) -> Tokens<'_> {
    Tokens { rest: line }
}

impl DeviceCommand {
    /// Canonical response text for query commands, without line ending.
    /// `Stop` has no response.
    #[must_use]
    pub const fn reply(self, firmware: &'static str) -> Option<&'static str> {
        match self {
            Self::Identify => Some("TCode v0.3"),
            Self::Version => Some(firmware),
            // The axis list is built by the governor, which knows its channels.
            Self::ListAxes | Self::Stop => None,
        }
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
    use std::vec::Vec;

    fn one(tok: &[u8]) -> Result<Command, ParseError> {
        parse_token(tok)
    }

    fn mv(kind: AxisKind, index: u8, raw: u16, modifier: Modifier) -> Command {
        Command::Move {
            axis: Axis { kind, index },
            target: Fraction::new(raw).unwrap(),
            modifier,
        }
    }

    #[test]
    fn parses_basic_moves() {
        assert_eq!(
            one(b"L0500"),
            Ok(mv(AxisKind::Linear, 0, 5000, Modifier::Immediate))
        );
        assert_eq!(
            one(b"v19999I2000"),
            Ok(mv(
                AxisKind::Vibrate,
                1,
                9999,
                Modifier::Interval { millis: 2000 }
            ))
        );
        assert_eq!(
            one(b"R2250s500"),
            Ok(mv(
                AxisKind::Rotate,
                2,
                2500,
                Modifier::Speed { per_second: 500 }
            ))
        );
        assert_eq!(
            one(b"A00"),
            Ok(mv(AxisKind::Aux, 0, 0, Modifier::Immediate))
        );
    }

    #[test]
    fn parses_device_commands() {
        assert_eq!(one(b"D0"), Ok(Command::Device(DeviceCommand::Identify)));
        assert_eq!(one(b"d1"), Ok(Command::Device(DeviceCommand::Version)));
        assert_eq!(one(b"D2"), Ok(Command::Device(DeviceCommand::ListAxes)));
        assert_eq!(one(b"DSTOP"), Ok(Command::Device(DeviceCommand::Stop)));
        assert_eq!(one(b"dstop"), Ok(Command::Device(DeviceCommand::Stop)));
        assert_eq!(one(b"D9"), Err(ParseError::UnknownDeviceCommand));
    }

    #[test]
    fn rejects_malformed_tokens() {
        assert_eq!(one(b""), Err(ParseError::UnknownPrefix(0)));
        assert_eq!(one(b"X0500"), Err(ParseError::UnknownPrefix(b'X')));
        assert_eq!(one(b"L"), Err(ParseError::MissingIndex));
        assert_eq!(one(b"LA500"), Err(ParseError::MissingIndex));
        assert_eq!(one(b"L0"), Err(ParseError::BadMagnitude));
        assert_eq!(one(b"L012345"), Err(ParseError::BadMagnitude));
        assert_eq!(one(b"L0500I"), Err(ParseError::BadModifier));
        assert_eq!(one(b"L0500X100"), Err(ParseError::BadModifier));
        assert_eq!(one(b"L0500I12345678901"), Err(ParseError::BadModifier));
        assert_eq!(one(b"L0500I4294967296"), Err(ParseError::BadModifier));
        assert!(one(b"L0500I4294967295").is_ok());
        assert_eq!(one(b"L0500I100x"), Err(ParseError::Trailing));
    }

    #[test]
    fn line_tokenizes_and_isolates_errors() {
        let got: Vec<_> = parse_line(b"  L0500 \t bogus V09999I1000\r\n").collect();
        assert_eq!(got.len(), 3);
        assert!(got[0].is_ok());
        assert_eq!(got[1], Err(ParseError::UnknownPrefix(b'b')));
        assert!(got[2].is_ok());
        assert_eq!(parse_line(b"   \r\n").count(), 0);
        assert_eq!(parse_line(b"").count(), 0);
    }

    #[test]
    fn replies() {
        assert_eq!(DeviceCommand::Identify.reply("fw"), Some("TCode v0.3"));
        assert_eq!(DeviceCommand::Version.reply("fw 1.0"), Some("fw 1.0"));
        assert_eq!(DeviceCommand::Stop.reply("fw"), None);
    }
}
