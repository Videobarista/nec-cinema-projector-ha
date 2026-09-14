"""Import the integration's protocol modules without pulling in Home Assistant.

``custom_components/nec_cinema/__init__.py`` imports Home Assistant, which the
protocol and client modules do not need. This builds a throwaway package that
points at the same directory, so the modules can be imported on their own.
"""

import importlib
import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "nec_cinema"
_NAME = "nec_cinema_under_test"

if _NAME not in sys.modules:
    _pkg = types.ModuleType(_NAME)
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_NAME] = _pkg

const = importlib.import_module(f"{_NAME}.const")
protocol = importlib.import_module(f"{_NAME}.protocol")
client = importlib.import_module(f"{_NAME}.client")
