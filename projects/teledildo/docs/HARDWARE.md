# Reference hardware

Everything runs from 5 V USB. There is no mains connection and no battery in
the reference design; the enclosure is the only thing between the
electronics and the user.

## Bill of materials

| Qty | Part | Notes |
|---|---|---|
| 1 | Raspberry Pi Pico (RP2040) | Pico W also works; wireless is unused. |
| 1 | DRV8833 dual H-bridge breakout | 1.5 A/channel, 2.7 to 10.8 V, built-in over-current and thermal shutdown. |
| 1 to 2 | 3 V ERM or LRA vibration motor | Coin or cylinder type, typically 60 to 120 mA. |
| 1 | Hobby micro servo (optional) | For the `L0` stroke axis; powered from VBUS through its own 1 A polyfuse. |
| 1 | 10 kΩ NTC thermistor, β≈3950 | Bonded to the motor housing / contact surface. |
| 1 | 10 kΩ resistor | NTC divider. |
| 1 | INA180A1 current-sense amplifier | Gain 20 V/V. |
| 1 | 0.1 Ω 1 % shunt | In the motor supply return. |
| 1 | Momentary switch | E-stop / fault clear. |
| 1 | 10 kΩ resistor | Pull-down on DRV8833 nSLEEP so the driver is off whenever the Pico is not driving the pin. |
| 1 | 500 mA polyfuse | Series with VBUS to the motor supply. |
| 1 | 100 µF electrolytic + 100 nF ceramic | Motor supply decoupling. |

## Wiring

```
Pico            DRV8833                 Other
----            -------                 -----
GP16 ---------- AIN1        AIN2 -- GND     motor 0 across AOUT1/AOUT2
GP17 ---------- BIN1        BIN2 -- GND     motor 1 across BOUT1/BOUT2
GP20 ---------- nSLEEP      (10k to GND)
VBUS --polyfuse-- VM        GND -- shunt -- GND      (shunt in VM return)
GP18 ----------------------------------- servo signal (optional)
GP15 ----------------------------------- switch to GND (internal pull-up)
GP26/ADC0 ------------------------------ NTC to 3V3, 10k to GND
GP27/ADC1 ------------------------------ INA180 OUT (IN+/IN- across shunt)
GP29/ADC3        on-board VSYS/3, nothing to wire
GP25             on-board LED
```

With one input of each bridge tied to ground, the motor runs in one
direction and PWM on the other input sets intensity. `nSLEEP` low puts the
outputs into high-impedance regardless of PWM, which is the state at reset
and in every fault.

## PWM and sensor constants

All numbers that depend on this wiring live in `firmware/src/board.rs`:

* motor PWM 25 kHz (`MOTOR_PWM_TOP = 4999` at 125 MHz) to stay above hearing;
* servo 50 Hz, 1.0 to 2.0 ms pulse;
* NTC lookup table generated for the divider above, 0 to 95 °C in 5 °C
  steps (anything outside is a sensor fault);
* current scale 2 mV/mA, supply scale ×3.

If you change a resistor, regenerate the table (the Python one-liner is in
the git history of `board.rs`) and re-derive the scales. The governor's
thresholds are in `teledildo-core::governor::Limits::DEFAULT`.

## Mechanical and body-safety notes

* Encapsulate the motor and thermistor in **platinum-cure silicone** or
  house them in a commercially made body-safe sleeve; no exposed PCB,
  leads, or heat-shrink may contact skin.
* Route the USB cable through a strain relief and keep the electronics
  outside the body; only the sealed actuator module goes near it.
* The 42 °C thermal cutoff assumes the thermistor is thermally bonded to
  the surface that touches skin. If it is not, lower the limit.
* Clean the sealed module with the silicone's recommended agent; never
  submerge the Pico.

## USB identity

The firmware enumerates with VID `0x1209` / PID `0x0001`, which pid.codes
reserves for **testing only**. Request a free PID from
<https://pid.codes> before sharing built hardware.
