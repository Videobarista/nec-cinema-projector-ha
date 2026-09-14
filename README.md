# Sharp NEC Cinema Projector for Home Assistant

[![Release](https://img.shields.io/github/v/release/Videobarista/nec-cinema-projector-ha)](https://github.com/Videobarista/nec-cinema-projector-ha/releases)
[![Tests](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/test.yml/badge.svg)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/test.yml)
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
| Douser | `cover` (shutter) | Open and close the mechanical douser |
| Douser open | `switch` | The same douser as a plain switch (disabled by default) |
| Picture mute | `switch` | Electronic blanking, douser stays put |
| Macro | `select` | Preset (macro) keys you named in the options |
| Status | `sensor` | Standby, ignition, running, cooling, light error, … |
| Light source hours | `sensor` | Lamp or laser usage time |
| Light output | `sensor` | Configured output power in percent |
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

Written against rev. 15.0 of the protocol document, which covers NC900C-A through NC2443ML,
NP-02HD and NP-42HD. Model dependent commands are probed at startup and the integration falls back
automatically:

- lamp hours: `LAMP INFORMATION REQUEST 3` (235-31), falling back to `2` (037-2) on older heads;
- temperatures: `PARTS COUNT` / `COMMON CURRENT STATUS` (305-1, 300-20) on newer heads, falling back
  to `TEMPERATURE STATUS REQUEST 3` (078-204) on older ones.

## Known limitations

- Some heads accept only one control connection at a time on port 43728. If a TMS or the NEC service
  software holds that session, the integration cannot connect until it is released.
- The protocol offers no separate lamp/light on-off command; power on and off cover both.
- The title list cannot be enumerated, only the current title is readable. Hence the macro naming
  in the options instead of a full list.
- While the head is powering up or cooling down it refuses most commands. Those refusals are logged
  at debug level and do not raise errors.
- `PICTURE MUTE OFF` does nothing while the douser is closed — that is the projector's behaviour,
  not a bug in the integration.

## Development

The protocol layer is covered by tests that run a fake projector on a local
socket and speak the real frame format to it. No dependencies are needed — not
even Home Assistant:

```bash
python -m unittest discover -s tests -t tests -v
```

`pytest tests` works too. The documented command frames are asserted byte for
byte against the protocol document, so a change that would silently stop the
projector from answering fails the build instead.

## License

MIT © 2026 VideoBarista
