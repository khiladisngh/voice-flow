import os
import shutil
import sys
from pathlib import Path

import pytest

# Ensure project root is at the head of sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Capability probes. CI runners have neither a writable /dev/uinput nor a
# PipeWire session, so tests that touch real devices are skipped there
# instead of failing. Locally they run for real.
UINPUT_AVAILABLE = os.access("/dev/uinput", os.W_OK)
PIPEWIRE_AVAILABLE = shutil.which("pw-record") is not None


def pytest_collection_modifyitems(config, items):
    skip_uinput = pytest.mark.skip(reason="/dev/uinput not writable (needs the 'input' group)")
    skip_pipewire = pytest.mark.skip(reason="pw-record not available (needs a PipeWire session)")

    for item in items:
        if "uinput" in item.keywords and not UINPUT_AVAILABLE:
            item.add_marker(skip_uinput)
        if "pipewire" in item.keywords and not PIPEWIRE_AVAILABLE:
            item.add_marker(skip_pipewire)
