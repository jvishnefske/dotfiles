# Protocol: TCode v0.3 over USB CDC

TCode is the plain-text protocol used by the OSR2/SR6 family of open-source
strokers and supported natively by Buttplug/Intiface, which is why this
device speaks it rather than a bespoke format. The serial parameters are
irrelevant over USB CDC (any baud rate works; 115200 is conventional).

## Grammar accepted by `teledildo-core::tcode`

```
line      := (ws* token)* ws* '\n'
token     := move | device
move      := axis index magnitude modifier?
axis      := 'L' | 'R' | 'V' | 'A'          (case-insensitive)
index     := '0'..'9'
magnitude := digit{1,4}                     fraction: "5"=.5  "05"=.05  "0500"=.05
modifier  := ('I' | 'S') digit{1,10}         I = interval ms, S = raw units/s
device    := 'D0' | 'D1' | 'D2' | 'DSTOP'
ws        := ' ' | '\t' | '\r'
```

Malformed tokens are dropped individually; the rest of the line is still
processed. Lines longer than 128 bytes are discarded whole.

## Axes on this device

| Axis | Meaning | Notes |
|---|---|---|
| `V0`, `V1` | vibration motors 0 and 1 | clamped to `max_vibe` (80 %), slew-limited |
| `L0` | stroke servo | slew-limited; holds position on link loss |
| `R*`, `A*`, other indices | not fitted | ignored |

## Device commands

| Command | Response |
|---|---|
| `D0` | `TCode v0.3` |
| `D1` | `teledildo-rp2040 v<version>` |
| `D2` | `V0 Vibe0` / `V1 Vibe1` / `L0 Stroke` (one per line) |
| `DSTOP` | none; vibration ramps to zero, stroke holds |

## Timing semantics

* No modifier: move at the governor's slew ceiling.
* `I<ms>`: arrive after `ms` milliseconds, if the slew ceiling allows.
* `S<n>`: move at `n` raw units (1/10000 of full scale) per second, if the
  slew ceiling allows.

The host cannot request anything faster than the ceiling; it can only
request slower.

## Link watchdog

Any valid token, including `D0`, counts as host activity. After 2 s without
one the device coasts to safe. Host software that wants to hold a steady
intensity must re-send it (or send `D0`) at least every 2 s. Buttplug's
TCode implementation does this by design.
