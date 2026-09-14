# Sharp NEC Cinema Projector for Home Assistant

[![Release](https://img.shields.io/github/v/release/Videobarista/nec-cinema-projector-ha)](https://github.com/Videobarista/nec-cinema-projector-ha/releases)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![HACS](https://img.shields.io/badge/HACS-custom-orange)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Home Assistant custom integration for **Sharp NEC digital cinema projectors** (NC series, Series 2).
It talks to the projector head over the documented cinema control protocol on **TCP port 43728** —
no cloud, no vendor software, no TMS in between.

Built from *Control Commands for Cinema Projector Series 2*, rev. 15.0 (document LDC0001).

> Note: this is **not** the NEC installation projector protocol on port 7142. That command set is a
> different one and does not work on cinema heads.

## What you get

| Entity | Type | What it does |
| --- | --- | --- |
| Projector | `media_player` | On/off, input port selection, current title |
| Light source | `switch` | Light the lamp or laser without cycling projector power |
| Light control mode | `select` | Follow power, forced on, or forced off |
| Douser | `cover` (shutter) | Open and close the mechanical douser |
| Douser open | `switch` | The same douser as a plain switch (disabled by default) |
| Picture mute | `switch` | Electronic blanking, douser stays put |
| Macro | `select` | Preset (macro) keys you named in the options |
| Status | `sensor` | Standby, ignition, running, cooling, light error, … |
| Light source hours | `sensor` | Lamp or laser usage time |
| Light output | `sensor` | Configured output power in percent (newer heads) |
| Lamp power / current / voltage | `sensor` | Measured by the lamp power supply (NC3240S-A, NC3200S, NC2000C, NC1200C) |
| Cooling remaining | `sensor` | Seconds of cooling left |
| Current title | `sensor` | Title name, with title and preset number as attributes |
| Active errors | `sensor` | Error count, with the decoded messages as an attribute |
| Last seen | `sensor` | Timestamp of the last successful poll |
| Temperatures | `sensor` | One per thermal sensor, discovered from the projector |
| Light source | `binary_sensor` | Whether the lamp or laser is actually lit |
| Projector error | `binary_sensor` | Problem class, with the messages as an attribute |
| Test pattern | `binary_sensor` | Whether a test pattern is on screen |
| Media block selected | `binary_sensor` | Whether the IMB/IMS port is the active input |
| Control port | `binary_sensor` | Whether the projector answers |

Lamp status is read from the projector, never assumed. If the head is unreachable the media player
reports **off**, the control port sensor goes off, and the other entities go unavailable.

## Actions

All actions target the media player entity.

- `nec_cinema.select_title` — pick an entry from the title list (0–99)
- `nec_cinema.select_macro` — press a preset key (1–20)
- `nec_cinema.picture_mute` — electronic blanking on or off
- `nec_cinema.lens_control` — nudge zoom, focus or lens shift

```yaml
action: nec_cinema.select_macro
target:
  entity_id: media_player.nc2000c
data:
  macro: 2
```

## Installation

1. HACS → Custom repositories → add this repository, category **Integration**.
2. Install, restart Home Assistant.
3. Settings → Devices & services → Add integration → **Sharp NEC Cinema Projector**.
4. Enter the IP address of the projector head. Port 43728 and projector ID 0 (broadcast) suit
   virtually every single projector installation.

In the integration options you can set the polling interval and name your macro keys, for example:

```
1: Flat, 2: Scope, 3: Alternative content
```

Only the macros you list appear in the `select` entity. The service call works for all 20 regardless.

## Switching the light

`POWER ON` and `POWER OFF` cover the whole head. To light the lamp or laser on
its own, the **Light source** switch uses `LAMP CONTROL MODE SET` (235-19).

That command sets a mode rather than pressing a button: turning the switch off
puts the head in "light off mode", where it stays dark even after a power cycle,
until the switch is turned back on or the **Light control mode** select is put
back to *Follow projector power*. If a projector refuses to ignite, check that
select first.

## Media block (IMS / IMB)

The projector protocol has **no playback commands**. Ports 43744–43759 belong to the media block
itself and every brand speaks its own protocol there — a Dolby IMS3000, a GDC SR-1000 and an NEC IMB
have nothing in common at that level.

This integration therefore handles the media block the way the projector does:

- the **IMB port** appears in the source list, so you can switch the projector to it;
- **Media block selected** tells you whether the IMB is the active input.

For actual playback control, run the integration for your specific media block next to this one and
combine them in a script. On NEC heads the usual show start is: select the macro or title (format,
lens, port), open the douser, then start playback on the media block.

## Tested against

Verified on an **NC1200C** in daily use: power, douser, light control, input selection, titles,
errors and temperatures all confirmed against the head itself.

Written against rev. 15.0 of the protocol document, which covers NC900C-A through NC2443ML,
NP-02HD and NP-42HD. Model dependent commands are chosen from the availability lists in that
document, so the right ones are used without guessing:

- lamp hours: `LAMP INFORMATION REQUEST 3` (235-31), falling back to `2` (037-2) on older heads;
- lamp output: measured watts, amps and volts via `235-1` on the four heads that support it, a
  setting percentage via `235-29` on all others;
- temperatures: `PARTS COUNT` / `COMMON CURRENT STATUS` (305-1, 300-20) on newer heads, falling back
  to `TEMPERATURE STATUS REQUEST 3` (078-204) on older ones.

## Known limitations

- Some heads accept only one control connection at a time on port 43728. If a TMS or the NEC service
  software holds that session, the integration cannot connect until it is released.
- The title list cannot be enumerated, only the current title is readable. Hence the macro naming
  in the options instead of a full list.
- While the head is igniting, cooling or switching, it refuses commands with a NAK that clears by
  itself. Those are retried for a few seconds; if the head is still busy, the action reports that
  rather than quoting the protocol.
- `PICTURE MUTE OFF` does nothing while the douser is closed — that is the projector's behaviour,
  not a bug in the integration.

## Brand images

The `custom_components/nec_cinema/brand/` folder is where Home Assistant looks
for the integration's icon. No images are shipped, to stay clear of
manufacturer trademarks. See the README in that folder for the sizes if you
want to add your own.

## License

MIT © 2026 VideoBarista
