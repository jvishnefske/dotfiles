# teledildo

An open-source, remotely controllable adult toy built the way safety-critical
embedded systems are built: a small verified core, a thin hardware layer, and
a hardware watchdog behind both.

* **Protocol:** [TCode v0.3](docs/PROTOCOL.md) over USB serial. Any
  [Buttplug](https://buttplug.io)-compatible app (Intiface Central, XToys,
  ScriptPlayer, ...) can drive it locally or over the network. No cloud, no
  account, no vendor app.
* **Hardware:** Raspberry Pi Pico (RP2040), a DRV8833 motor driver, one or
  two small vibration motors, optionally a hobby servo for a stroke axis, an
  NTC thermistor, a current-sense amplifier, and an e-stop button. See
  [docs/HARDWARE.md](docs/HARDWARE.md).
* **Firmware:** Rust, `no_std`, async ([Embassy](https://embassy.dev)).
* **Safety:** every setpoint passes through a governor that enforces an
  intensity ceiling, slew limits, a thermal duty budget, a link watchdog and
  latched hardware faults. The governor is a dependency-free, `unsafe`-free
  crate with unit tests, property tests, and
  [Kani](https://model-checking.github.io/kani/) proof harnesses. See
  [docs/SAFETY.md](docs/SAFETY.md).

## Layout

```
core/       teledildo-core   no_std library: TCode parser, line assembler,
                             motion planner, safety governor, ADC lookup.
                             Host-testable. Kani harnesses in src/proofs.rs.
firmware/   teledildo-rp2040 Pico firmware. Pin map and board constants in
                             src/board.rs, tasks in src/main.rs.
docs/       SAFETY.md, HARDWARE.md, PROTOCOL.md
```

`core` and `firmware` are separate Cargo projects (not a workspace) because
one targets the host and the other targets `thumbv6m-none-eabi`.

## Build and verify

```bash
# Core: unit + property tests, lints that deny every panic path
cd core
cargo fmt --check
cargo clippy --all-targets            # restriction lints are `deny` in Cargo.toml
cargo test
cargo run --example replay            # prints a setpoint timeline for a demo script

# Optional: exhaustive bounded proofs (needs `cargo install kani-verifier && cargo kani setup`)
cargo kani

# Firmware
rustup target add thumbv6m-none-eabi
cd ../firmware
cargo clippy --release
cargo build --release
```

Flash with a debug probe (`cargo run --release`, uses `probe-rs`), or produce
a UF2 for drag-and-drop:

```bash
cargo install elf2uf2-rs
elf2uf2-rs target/thumbv6m-none-eabi/release/teledildo-rp2040 teledildo.uf2
# hold BOOTSEL, plug in the Pico, copy teledildo.uf2 to the RPI-RP2 drive
```

## Use

1. Plug the device in. It enumerates as a USB serial port
   (`/dev/ttyACM*`, `COM*`). The LED is off: nothing is commanded.
2. In Intiface Central, enable the *Serial Port* device manager, add the
   port at 115200 baud, and choose the `TCode v0.3` protocol; or talk to it
   directly:

   ```bash
   printf 'D0\n'            > /dev/ttyACM0   # -> TCode v0.3
   printf 'V05000I1000\n'   > /dev/ttyACM0   # vibe 0 to 50 % over 1 s
   printf 'L09000I500\n'    > /dev/ttyACM0   # stroke to 90 % in 0.5 s
   printf 'DSTOP\n'         > /dev/ttyACM0   # stop
   ```

3. If the host goes quiet for 2 s or the port closes, the device coasts to
   off on its own. Pressing the button latches an emergency stop (fast
   blinking LED); holding it for 3 s clears the fault once the sensors read
   healthy.

## Status

Firmware compiles and the core is tested and lint-clean, but **this has not
yet been run on hardware** in this repository. Treat the pin map, PWM
geometry and sensor scaling in `firmware/src/board.rs` as a starting point
to verify against your build, and read [docs/SAFETY.md](docs/SAFETY.md)
before putting anything on a body.

## License

MIT. See [LICENSE](LICENSE).
