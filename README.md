# Sharp NEC Cinema Projector for Home Assistant

[![Release](https://img.shields.io/github/v/release/Videobarista/nec-cinema-projector-ha)](https://github.com/Videobarista/nec-cinema-projector-ha/releases)
[![Ruff](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/ruff.yml/badge.svg?branch=main)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/ruff.yml)
[![hassfest](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/hassfest.yml)
[![HACS](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/hacs.yml/badge.svg?branch=main)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/hacs.yml)
[![CodeQL](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/codeql.yml)
[![Tests](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Videobarista/nec-cinema-projector-ha/actions/workflows/tests.yml)
[![Quality scale: Bronze (aligned)](https://img.shields.io/badge/quality%20scale-bronze%20(aligned)-cd7f32.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Videobarista&repository=nec-cinema-projector-ha&category=integration)

Home Assistant custom integration for **Sharp NEC digital cinema projectors** (NC series, Series 2).
It talks to the projector head over the documented cinema control protocol on **TCP port 43728** —
no cloud, no vendor software, no TMS in between.

Built from *Control Commands for Cinema Projector Series 2*, rev. 15.0 (document LDC0001).

> Note: this is **not** the NEC installation projector protocol on port 7142. That command set is a
> different one and does not work on cinema heads.

> This is an independent community project. It is **not affiliated with, endorsed by, sponsored by
> or supported by** Sharp NEC Display Solutions, Sharp or NEC. See [Disclaimer](#disclaimer).

## What you get

| Entity | Type | What it does |
| --- | --- | --- |
| Projector | `media_player` | On/off, input port selection, current title |
| Light source | `switch` | Light the lamp or laser without cycling projector power |
| Start dark | `switch` | Power the projector up without lighting the lamp |
| Lamp mode | `select` | Both lamps, lamp 1 only or lamp 2 only, on dual lamp heads; changeable while the lamp is off |
| Douser | `cover` (shutter) | Open and close the mechanical douser |
| Douser open | `switch` | The same douser as a plain switch (disabled by default) |
| Picture mute | `switch` | Electronic blanking, douser stays put |
| Macro | `select` | Preset (macro) keys, by the names the projector gave them |
| Lens | `button` | Zoom, focus and lens shift, a quarter second per press |
| Status | `sensor` | Standby, ignition, running, cooling, light error, … |
| Light source hours | `sensor` | Lamp or laser usage time, with the warning threshold as an attribute |
| Lamp remaining | `sensor` | Remaining lamp life in percent, where the head reports it |
| Lamp 2 hours / remaining | `sensor` | The same for the second lamp, on dual lamp heads |
| Lamp strikes | `sensor` | How often the lamp has been struck |
| Light output | `sensor` | Configured output power in percent (newer heads) |
| Lamp power / current / voltage | `sensor` | Measured by the lamp power supply (NC3240S-A, NC3200S, NC2000C, NC1200C) |
| Cooling remaining | `sensor` | Seconds of cooling left, zero outside the cooling phase |
| Cooling progress | `sensor` | Cooling time left in percent, 100 down to 0, for bar and gauge cards |
| Current title | `sensor` | Title name, with title and preset number as attributes |
| Active errors | `sensor` | Error count, with the decoded messages as an attribute |
| Last seen | `sensor` | Timestamp of the last successful poll |
| Last command | `sensor` | How the most recent command went, with the projector's own wording, the status it was in and the raw NAK code as attributes |
| Temperatures | `sensor` | One per thermal sensor, discovered from the projector |
| Light source | `binary_sensor` | Whether the lamp or laser is actually lit |
| Projector error | `binary_sensor` | Problem class, with the messages as an attribute |
| Test pattern | `binary_sensor` | Whether a test pattern is on screen |
| Media block selected | `binary_sensor` | Whether the IMB/IMS port is the active input |
| Control port | `binary_sensor` | Whether the projector answers |

Lamp status is read from the projector, never assumed. If the head is unreachable the media player
reports **off**, the control port sensor goes off, and the other entities go unavailable.

A projector switched off at the mains does not block Home Assistant either. The integration
remembers what the projector reported the last time it answered: model, serial number, inputs,
lamp and temperature sensors. After a restart it sets the projector up from that, shows it as off,
and connects by itself as soon as the projector answers. Only a projector that has never answered
since version 1.12.0 has to be reachable once before it can be set up.

For a cooling bar, use **Cooling progress** rather than **Cooling remaining**. Gauge and bar cards
default to a maximum of 100, so a five minute cool-down in seconds would sit at full until the last
100 seconds. The percentage needs no maximum set, and still shows the right share after a Home
Assistant restart halfway through cooling, because the integration remembers how long the last
full cool-down took.

## Actions

All actions target the media player entity.

- `nec_cinema.select_title` — pick an entry from the title list (0–99)
- `nec_cinema.select_macro` — press a preset key (1–20)
- `nec_cinema.picture_mute` — electronic blanking on or off
- `nec_cinema.lens_control` — nudge zoom, focus or lens shift for a chosen duration

```yaml
action: nec_cinema.select_macro
target:
  entity_id: media_player.nc2000c
data:
  macro: 2
```

## Installation

1. Use the **Open in HACS** button above, or add this repository by hand:
   HACS → Custom repositories → paste the repository URL, category **Integration**.
2. Install, restart Home Assistant.
3. Settings → Devices & services → Add integration → **Sharp NEC Cinema Projector**.
4. Enter the IP address of the projector head. Port 43728 and projector ID 0 (broadcast) suit
   virtually every single projector installation.

In the integration options you can set the polling interval and, if you want, pre-fill or override
macro names — see below.

### Manual

Copy `custom_components/nec_cinema` to the `custom_components` folder of your Home Assistant
configuration, restart Home Assistant and continue with step 3 above.

The integration needs Home Assistant 2025.10 or newer.

## Removal

1. Go to **Settings → Devices & services** and open **Sharp NEC Cinema Projector**.
2. Open the menu (three dots) next to the projector and choose **Delete**.
3. To remove the files as well: in HACS, open **Sharp NEC Cinema Projector** and choose
   **Remove**, or delete `custom_components/nec_cinema` for a manual installation. Restart Home
   Assistant afterwards.

Nothing is changed on the projector itself. A light control mode the integration set (for Start
dark) is cleared by the projector the next time it enters standby.

## Macro names are learned, not configured

The protocol can report which title is active, including its name and which preset key it belongs
to, but it cannot list the titles or preset keys. Walking through them to find out would mean
actually switching the projector through every format, which is not something to do on a cinema
head.

So the names are learned instead. Whenever a different title becomes active — through this
integration, the touch panel, or a theatre management system — the name and its preset number are
recorded. After a pass through the preset keys, the **Macro** select holds them all and switching by
name works from scripts and automations.

The list starts empty, and a preset key that is never used never appears. To pre-fill or override
a name, set it in the integration options as a comma separated list, for example
`1: Flat, 2: Scope`; names written there win over learned ones. The **Forget learned macros**
button, disabled by default, clears what was learned after you reorganise the preset keys.

## Lens control

Zoom, focus and both lens shift axes are available as buttons, each press
driving the motor for a quarter of a second. Which physical direction counts as
plus depends on the lens, so try one press and watch the screen.

There is no position feedback: the protocol offers no way to read a lens
position back, and no lens memories. For longer runs use the
`nec_cinema.lens_control` action, which takes a duration of 0.25, 0.5 or 1
second.

## Switching the light

There are two controls, each with one meaning.

**Light source** acts now: it lights or extinguishes the lamp or laser without
cycling projector power, through `LAMP CONTROL MODE SET` (235-19).

**Start dark** is a preference for the next power-up and never touches the lamp
when you change it. With it on, the projector powers up without lighting, and
the lamp is lit with the Light source switch when you want it.

Behind this sits a quirk of the projector. The light control mode it uses is a
temporary override, not a setting: the projector clears it by itself the moment
it enters standby. Set again once in standby, it stays put and is honoured at
the next power-up. So with Start dark on, the integration puts forced off back
as soon as the projector has cleared it on the way into standby, and sets it
once more just before a power-up it issues. A power-up from the touch panel
therefore starts dark as well.

Start dark only ever overrules the projector's own default. A lamp switched on
during a power-up, from the Light source switch or the touch panel, is left
alone, and so is a running projector that is sent another turn on. Once the
projector is running the lamp is left entirely to the Light source switch, and
using that switch takes over from Start dark until the next shutdown.

## Seeing why a command was refused

The **Last command** sensor holds the outcome of the most recent command, so a
refusal does not have to be chased through the log. It keeps that outcome until
the next command, so a card should lead with the projector's current state and
only mention the last command when something actually needs attention:

```yaml
type: markdown
content: >
  {% set last = 'sensor.projector_last_command' %}
  {% set outcome = states(last) %}
  {% set pending = state_attr(last, 'pending') %}

  ## {{ states('sensor.projector_status') }}

  {% if pending %}
  Waiting for the projector: {{ pending | join(', ') }}
  {% elif outcome not in ['ok', 'unknown', 'unavailable'] %}
  **{{ state_attr(last, 'message') }}**
  {% if state_attr(last, 'code') %} (code {{ state_attr(last, 'code') }}){% endif %}
  while the projector reported {{ state_attr(last, 'projector_status') }},
  {{ relative_time(as_datetime(state_attr(last, 'at'))) }} ago.
  {% endif %}
```

Replace the two entity ids with your own.

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

Verified on an **NC1200C** and an **NC900C-A**: power, douser, light control, input selection, titles,
errors and temperatures all confirmed against the head itself.

Written against rev. 15.0 of the protocol document, which covers NC900C-A through NC2443ML,
NP-02HD and NP-42HD. Model dependent commands are chosen from the availability lists in that
document, so the right ones are used without guessing:

- lamp hours: `LAMP INFORMATION REQUEST 3` (235-31), falling back to `2` (037-2) on older heads;
- lamp output: measured watts, amps and volts via `235-1` on the four heads that support it, a
  setting percentage via `235-29` on all others;
- model name: taken from the projector type in `SETTING REQUEST` (078-1), since several heads
  answer the model name request with a family label such as "NC-Series";
- temperatures: `PARTS COUNT` / `COMMON CURRENT STATUS` (305-1, 300-20) on newer heads, falling back
  to `TEMPERATURE STATUS REQUEST 3` (078-204) on older ones;
- lamp mode on dual lamp heads: `LAMP MODE SET` (098-246) is sent as `03H B1H`, like every other
  setting command. Rev. 15.0 prints it as `03H B0H`, but that is the request: a head sent that only
  reports its current mode and changes nothing.

## Known limitations

- Some heads accept only one control connection at a time on port 43728. If a TMS or the NEC service
  software holds that session, the integration cannot connect until it is released.
- The title list cannot be enumerated, only the current title is readable. Hence the macro naming
  in the options instead of a full list.
- While the head is igniting, cooling or switching, it refuses commands with a NAK that clears by
  itself. Those are retried for a few seconds. A douser or picture mute command refused while
  the head is starting up is held and applied once it runs. One refused while it is shutting down
  is dropped instead: the projector closes the douser by itself on the way to standby, and a
  held "douser open" carried into standby would expose the DMD in an empty auditorium.
- The projector answers `02H 03H` both while it is busy and when manual control is locked out, for
  instance because metadata or GPIO control is enabled. The integration tells the two apart by the
  process status: refused while the head reports Running means locked, not busy, and is
  reported as such instead of suggesting you wait.
- `PICTURE MUTE OFF` does nothing while the douser is closed — that is the projector's behaviour,
  not a bug in the integration.

## Quality scale

This integration is aligned with the **Bronze** tier of the
[Home Assistant integration quality scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/).
Home Assistant only grades integrations that ship with Home Assistant itself, so this is a
self-assessment, not an official rating. The status per rule is recorded in
[`quality_scale.yaml`](custom_components/nec_cinema/quality_scale.yaml).

One rule is deliberately not followed: *test-before-setup* asks an integration to hold back its
setup while the device does not answer. A cinema projector switched off at the mains is a normal
state, so a projector that answered before is set up from what it reported then and shown as off
instead (see [What you get](#what-you-get)).

## Development

The tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
and run on every push. To run them locally (Python 3.14):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

## Brand images

`custom_components/nec_cinema/brand/` holds a plain, self-drawn projector icon.
It is deliberately generic: the Sharp NEC marks belong to Sharp NEC Display
Solutions and are not redistributed here. Replace those files with your own if
you have the right to use a manufacturer's artwork; see `Brand/README.md` for
the sizes.

## Disclaimer

This integration is an independent, community-made project. It is not affiliated with, endorsed
by, sponsored by or supported by Sharp NEC Display Solutions, Ltd., Sharp Corporation, NEC
Corporation or any of their subsidiaries. "Sharp", "NEC", "Sharp NEC" and model names such as
NC1200C and NC900C-A are trademarks of their respective owners. They are used here only to
describe which projectors the integration works with.

The integration is built from the publicly documented control protocol and provided as is,
without warranty of any kind (see the [license](LICENSE)). It switches power, the lamp, the
douser and inputs of real cinema equipment: check how it behaves on your own installation before
you rely on it during a screening. For help with the projector itself, contact Sharp NEC or your
dealer. Problems with this integration belong in this repository's issues, not with them.

## License

MIT © 2026 Videobarista
