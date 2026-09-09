# Safety design

This device is a mains-isolated, low-voltage motor controller that will be
held against skin by someone who may not be able to reach the off switch
quickly and who is trusting a person on the other end of a network link.
The design goal is that **no software input, network condition, or single
hardware failure can cause sustained unintended output.**

## Hazards considered

| Hazard | Mitigation |
|---|---|
| Host commands excessive intensity | Governor clamps every vibration setpoint to `Limits::max_vibe` (default 80 %). Applied at command time *and* re-checked at output time. |
| Sudden jump in intensity | Slew limit `vibe_slew_per_ms` (default 0 to 100 % in no less than 500 ms). Host `I`/`S` modifiers can only slow this down, never speed it up. |
| Host connection drops mid-session | Transport reports `LinkDown` (USB disconnect / port closed) and the governor coasts vibration to zero immediately. Independently, silence for `link_timeout_ms` (default 2 s) does the same. Coasting ignores any slow ramp the host had requested. |
| Sustained heating of motor / surface | Leaky-bucket duty integrator derates output to `heat.derate` (40 %) after roughly ten minutes at full intensity; NTC thermistor faults the device at 42.0 °C (IEC 60601-1 style limit for applied parts). |
| Motor stall / driver short | Current sense faults above 1.5 A. |
| Brown-out (driver behaviour undefined) | Supply sense faults below 4.0 V. |
| Sensor open/short | Reading outside the calibration table is a `Hardware` fault. |
| Firmware hang, panic, stuck bus | Hardware watchdog (500 ms) is fed only by a control-loop iteration that re-verified the outputs against the limits. A reset returns all GPIO to inputs; the driver's nSLEEP pull-down turns the motor off; on boot the reset reason latches a `Hardware` fault. |
| Governor bug | Firmware independently re-checks `outputs.vibe <= max_vibe` and `driver_enable == !silent` before writing PWM; a violation hard-offs and halts (watchdog reset). |
| Arithmetic overflow | Core uses checked/saturating arithmetic only, enforced by `clippy::arithmetic_side_effects = deny`. Firmware builds with `overflow-checks = true` in release. |
| Out-of-bounds access, unwrap panics | `clippy::indexing_slicing`, `unwrap_used`, `expect_used`, `panic` are `deny` in both crates; `unsafe_code` is `forbid` in core and `deny` in firmware. |
| Needing to stop *now* | Local e-stop button latches `Fault::EmergencyStop`. Faults are cleared only by a deliberate 3 s hold **and** healthy sensor readings; never by the host. |
| Unattended restart into motion | Boot state is `Idle`: outputs zero and driver disabled until a valid command arrives. |

## Fail-silent principle

Every ambiguous situation resolves to "less output":

* unknown or malformed token: ignored, other tokens on the line still apply;
* unsupported axis: ignored;
* faulted: all commands ignored, outputs zero, driver disabled;
* time going backwards or a stalled scheduler: `dt` is clamped to
  `max_tick_ms`, so a late tick cannot produce a large jump.

## What is verified, and how

`teledildo-core` has no dependencies and no `unsafe`, and takes time as an
explicit argument, so it is deterministic on the host.

* **Unit tests** cover each rule with concrete scenarios
  (`cargo test` in `core/`).
* **Property tests** (`core/tests/properties.rs`, proptest) generate random
  command/tick interleavings and check the invariants below.
* **Kani harnesses** (`core/src/proofs.rs`) check the same invariants
  exhaustively for bounded inputs (`cargo kani` in `core/`; runs in CI).

Invariants:

1. `outputs.vibe[i] <= limits.max_vibe` after every tick.
2. `outputs.vibe[i](n) <= outputs.vibe[i](n-1) + vibe_slew_per_ms * dt`.
3. After `report(fault)`: `outputs == OFF` and `state == Faulted` through any
   sequence of commands and ticks until `clear_fault` succeeds with healthy
   sensors.
4. A sensor reading outside limits faults on the tick it is observed.
5. With no commands, vibration reaches zero within
   `link_timeout_ms + SCALE / vibe_slew_per_ms` milliseconds.
6. The parser and line assembler never panic on arbitrary bytes, and every
   parsed magnitude is in range.
7. `driver_enable` is true exactly when some output is non-zero.

The property tests found one real bug during development: coasting used to
keep the host's `I` interval in force, so a long slow ramp requested by the
host stretched the ramp-*down* after link loss. Coasting now issues an
immediate zero command bounded only by the governor's own slew ceiling.

## What is *not* covered

* The firmware crate (USB stack, PWM, ADC drivers) is not formally verified.
  It is kept thin, lint-clean and free of `unsafe`, and the watchdog and the
  output re-check bound the damage a bug there can do.
* Electrical isolation, enclosure integrity, material biocompatibility and
  cleaning are hardware and manufacturing concerns; see
  [HARDWARE.md](HARDWARE.md).
* Authentication of the remote party is the job of the host software
  (Intiface's connection settings). The device trusts its USB host.

## Privacy and consent

The device stores nothing, has no radio, and speaks only to the USB host.
Remote sessions exist only for as long as the host software keeps a
connection open; when it closes, the device stops on its own.
