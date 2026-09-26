"""Constants for the Sharp NEC cinema projector integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "nec_cinema"

DEFAULT_PORT: Final = 43728
DEFAULT_NAME: Final = "Cinema projector"
DEFAULT_SCAN_INTERVAL: Final = 10
MIN_SCAN_INTERVAL: Final = 2

CONF_PROJECTOR_ID: Final = "projector_id"
CONF_MACROS: Final = "macros"

# Number of fast polls between two slow polls (lamp hours, errors, temperatures).
SLOW_POLL_EVERY: Final = 6

# --- Projector process status (RUNNING STATUS REQUEST 078-2, DATA06) -------
PROCESS_STATUS: Final = {
    0x00: "standby",
    0x01: "power_on_protect",
    0x02: "ignition",
    0x03: "power_on_running",
    0x04: "running_light_on",
    0x05: "cooling",
    0x07: "reset_wait",
    0x08: "fan_stop_error",
    0x09: "lamp_retry",
    0x0A: "light_error",
    0x0C: "running_light_off",
}
PROCESS_STATUS_UNKNOWN: Final = "unknown_state"

# --- Model names (SETTING REQUEST 078-1, DATA01-03 and DATA17) -------------
# Several heads answer MODEL NAME REQUEST with something unhelpful such as
# "NC-Series", while the projector type is specific. Prefer the type.
MODEL_TYPES: Final = {
    (0x0B, 0x00, 0x0A): "MM3000B",
    (0x0C, 0x05, 0x0A): "NC3200S",
    (0x0C, 0x07, 0x0A): "NC1200C",
    (0x0C, 0x08, 0x0A): "NC2000C",
    (0x0C, 0x0A, 0x0A): "NC3240S-A",
    (0x0C, 0x0B, 0x0A): "NC1040L-A series",
    (0x0C, 0x0C, 0x0A): "NC900C-A",
    (0x0C, 0x0F, 0x0A): "NC1100L-A",
    (0x0C, 0x0C, 0x0F): "NC1000C series",
    (0x0C, 0x0F, 0x0F): "NC1700L",
    (0x0C, 0x20, 0x0F): "NC1201L-A series",
    (0x0C, 0x21, 0x11): "NC3541L series",
    (0x0C, 0x23, 0x13): "NP-02HD series",
    (0x0C, 0x23, 0x15): "NP-42HD series",
    (0x0C, 0x24, 0x13): "NC1402L series",
}

# DATA17 narrows a series down to the exact model.
MODEL_VARIANTS: Final = {
    (0x0C, 0x0B, 0x0A): {0x02: "NC1040L-A", 0x03: "NC1440L-A"},
    (0x0C, 0x0C, 0x0F): {0x00: "NC1000C", 0x01: "NC1001C+", 0x02: "NC1005C"},
    (0x0C, 0x0F, 0x0F): {0x00: "NC1700L"},
    (0x0C, 0x20, 0x0F): {
        0x00: "NC1201L-A",
        0x01: "NC1205L-A+",
        0x02: "NC1101L-A",
        0x03: "NC1201L1-A",
    },
    (0x0C, 0x21, 0x11): {0x00: "NC3541L", 0x01: "NC2001L+", 0x02: "NC2041L"},
    (0x0C, 0x23, 0x13): {
        0x00: "NP-02HD",
        0x01: "NC2402ML",
        0x02: "NC2002ML",
        0x03: "NC1802ML",
        0x04: "NC2403ML",
        0x06: "NC1803ML",
    },
    (0x0C, 0x23, 0x15): {0x00: "NP-42HD", 0x01: "NC2443ML", 0x03: "NC1843ML"},
    (0x0C, 0x24, 0x13): {0x00: "NC1402L", 0x01: "NC1202L"},
}


# Heads that fill in the remaining-life and lamp 2 fields of 235-31. Other
# models leave those bytes as "don't care".
LAMP_DETAIL_TYPES: Final = frozenset({(0x0C, 0x0C, 0x0A), (0x0C, 0x0C, 0x0F)})

# --- Light control mode (LAMP CONTROL MODE REQUEST/SET 235-18, 235-19) ----
LIGHT_MODES: Final = {
    0x00: "standard",
    0x01: "on",
    0x02: "off",
}
LIGHT_MODE_CODES: Final = {name: code for code, name in LIGHT_MODES.items()}
LIGHT_MODE_UNKNOWN: Final = "unknown_mode"

# NAK codes that mean "busy right now", worth retrying, rather than "never".
TRANSIENT_NAK_CODES: Final = frozenset({(0x07, 0x00), (0x02, 0x02), (0x02, 0x03)})
COMMAND_ATTEMPTS: Final = 3
COMMAND_RETRY_DELAY: Final = 1.5

# --- Ports (INPUT SW CHANGE 018 / INPUT TERMINAL REQUEST 068) --------------
# Switching object 05H = "Port Switching", used by the NC series.
PORT_NAMES: Final = {
    0x1A: "292-A",
    0x1B: "292-B",
    0x1C: "292-Dual (AB)",
    0x1D: "292-Dual (AB)",
    0x38: "DVI-A",
    0x39: "DVI-B",
    0x3A: "DVI-Dual/Twin",
    0x3B: "IMB",
    0x3D: "292-C",
    0x3E: "292-D",
    0x3F: "292-Dual (CD)",
    0x40: "292-Quad",
    # MM3000B terminals (switching object 01H), for completeness.
    0x24: "SLOT1-1",
    0x25: "SLOT1-2",
    0x26: "SLOT1-3",
    0x29: "SLOT2-1",
    0x2A: "SLOT2-2",
    0x2B: "SLOT2-3",
}

# Ports the NC series accepts with switching object 05H.
NC_PORT_CODES: Final = (0x1A, 0x1B, 0x1C, 0x38, 0x39, 0x3A, 0x3B, 0x3D, 0x3E, 0x3F, 0x40)

# Fallback source list when INPUT TERMINAL REQUEST is not answered.
DEFAULT_PORT_CODES: Final = (0x1A, 0x1B, 0x1C, 0x38, 0x39, 0x3A, 0x3B)

# --- Current port (INPUT STATUS REQUEST 078-3, DATA03/DATA04) --------------
INPUT_STATUS_PORTS: Final = {
    (0x00, 0x06): "Test pattern",
    (0x01, 0x06): "292-A",
    (0x02, 0x06): "292-B",
    (0x03, 0x06): "292-Dual (AB)",
    (0x01, 0x0D): "292-C",
    (0x02, 0x0D): "292-D",
    (0x03, 0x0D): "292-Dual (CD)",
    (0x04, 0x0D): "292-Quad",
    (0x01, 0x0C): "DVI-A",
    (0x02, 0x0C): "DVI-B",
    (0x03, 0x0C): "DVI-Dual/Twin",
    (0x04, 0x0C): "IMB",
}

# --- Lens control (LENS CONTROL 053) --------------------------------------
LENS_AXES: Final = {
    "zoom": 0x00,
    "focus": 0x01,
    "shift_h": 0x02,
    "shift_v": 0x03,
}

# --- Temperature sensor names for the legacy command (078-204) -------------
# Keyed on the projector type triplet returned by SETTING REQUEST (078-1).
LEGACY_TEMP_NAMES: Final = {
    (0x0C, 0x05, 0x0A): (  # NC3200S
        "LPSU Intake", "Temp 2", "Outside Air", "DMD-B",
        "Exhaust", "Temp 6", "Temp 7", "Temp 8",
    ),
    (0x0C, 0x07, 0x0A): (  # NC1200C
        "LPSU Intake", "Temp 2", "Outside Air", "DMD-B",
        "Exhaust", "Temp 6", "Temp 7", "Temp 8",
    ),
    (0x0C, 0x08, 0x0A): (  # NC2000C
        "LPSU Intake", "Temp 2", "Outside Air", "DMD-B",
        "Exhaust", "Temp 6", "Temp 7", "Temp 8",
    ),
    (0x0C, 0x0A, 0x0A): (  # NC3240S-A
        "LPSU Intake", "Temp 2", "Outside Air", "DMD-B",
        "Exhaust", "Temp 6", "Temp 7", "Temp 8",
    ),
    (0x0C, 0x0C, 0x0A): (  # NC900C-A
        "DMD", "Inlet", "Ballast 1", "Ballast 2",
    ),
    (0x0C, 0x0B, 0x0A): (  # NC1040L-A / NC1440L-A
        "Intake", "DMD-B", "Exhaust", "Radiator",
        "LU Intake", "LU Exhaust 1", "LU Exhaust 2", "LU Humidity",
    ),
    (0x0C, 0x0F, 0x0A): (  # NC1100L-A
        "DMD", "Inlet", "Laser Diode 1", "Laser Diode 2", "Laser Diode 3",
        "Laser Diode 4", "Laser Diode 5", "Laser Y Driver 1", "Laser Y Driver 2",
        "Laser Y Driver 3", "Laser Y Driver 4", "Laser B Driver 1", "Phosphor Wheel",
    ),
}

# Model families that answer LAMP INFORMATION REQUEST 2 (037-2) instead of 3.
LEGACY_LAMP_TYPES: Final = frozenset(
    {
        (0x0C, 0x05, 0x0A),
        (0x0C, 0x07, 0x0A),
        (0x0C, 0x08, 0x0A),
        (0x0C, 0x0A, 0x0A),
        (0x0C, 0x0B, 0x0A),
    }
)

# Models that answer LAMP PARAMETER OUTPUT REQUEST (235-1) with measured
# watts, amps and volts. Every other head uses 235-29, which reports a
# percentage instead. Taken from the availability lists in the document, so the
# choice does not depend on probing a head while its lamp happens to be off.
LEGACY_LAMP_OUTPUT_TYPES: Final = frozenset(
    {
        (0x0C, 0x0A, 0x0A),  # NC3240S-A
        (0x0C, 0x05, 0x0A),  # NC3200S
        (0x0C, 0x08, 0x0A),  # NC2000C
        (0x0C, 0x07, 0x0A),  # NC1200C
    }
)

# Sensor value meaning "sensor could not be read" (7FFFH -> 3276.7 degrees).
TEMP_INVALID: Final = 0x7FFF
