//! # teledildo-core
//!
//! Hardware-independent logic for an open-source teledildonics device:
//!
//! * [`tcode`] — a zero-allocation parser for the TCode v0.3 text protocol
//!   (the protocol spoken by OSR-family strokers and supported by
//!   [Buttplug](https://buttplug.io) / Intiface for remote control).
//! * [`line`] — a fixed-capacity line assembler that turns a byte stream into
//!   complete TCode lines without ever growing.
//! * [`motion`] — a per-axis planner that interpolates toward targets under a
//!   hard slew-rate ceiling.
//! * [`lookup`] — integer ADC-to-units conversion so sensor thresholds are
//!   computed by verified code.
//! * [`governor`] — the safety envelope. Every actuator setpoint the firmware
//!   is allowed to emit passes through [`governor::Governor::tick`], which
//!   enforces intensity ceilings, slew limits, a thermal duty budget, a link
//!   watchdog, and latched hardware faults.
//!
//! ## Design rules
//!
//! * `#![no_std]`, no allocator, no dependencies, `#![forbid(unsafe_code)]`.
//! * All arithmetic is checked or saturating; indexing goes through `get`.
//!   Clippy's restriction lints (`arithmetic_side_effects`,
//!   `indexing_slicing`, `unwrap_used`, ...) are denied in `Cargo.toml`,
//!   so a panic path is a compile error rather than a code-review item.
//! * Time is passed in explicitly as `u64` milliseconds. The crate never
//!   reads a clock, so every behaviour is reproducible on a host and can be
//!   model-checked with [Kani](https://model-checking.github.io/kani/)
//!   (see `src/proofs.rs`).
//! * The governor is *fail-silent*: when in doubt it drives outputs to zero
//!   and disables the motor driver, and a latched fault can only be cleared
//!   by an explicit local action once the sensors read healthy again.

#![no_std]
#![forbid(unsafe_code)]

#[cfg(test)]
extern crate std;

pub mod governor;
pub mod line;
pub mod lookup;
pub mod motion;
pub mod tcode;
pub mod value;

#[cfg(kani)]
mod proofs;

pub use governor::{Disposition, Fault, Governor, Limits, Outputs, Sensors, State};
pub use tcode::{Axis, AxisKind, Command, DeviceCommand, Modifier, ParseError};
pub use value::Fraction;
