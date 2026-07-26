"""
Static data about programmers and MCUs supported by the GUI.

This module contains *only* data and a few tiny helper functions, so that
adding a new programmer or MCU later is as simple as editing one of the
lists/dictionaries below.
"""

# ---------------------------------------------------------------------------
# Programmers
# ---------------------------------------------------------------------------
# Display name -> avrdude -c value.
# Add a new entry here and it will automatically appear in the GUI dropdown.
PROGRAMMERS = [
    ("Arduino (arduino)", "arduino"),
    ("STK500 v1 (stk500v1)", "stk500v1"),
    ("USBasp (usbasp)", "usbasp"),
    ("USBtinyISP (usbtiny)", "usbtiny"),
]

# ---------------------------------------------------------------------------
# MCUs
# ---------------------------------------------------------------------------
# Each entry is a dict with:
#   display : text shown in the GUI dropdown
#   id      : value passed to avrdude with -p
#   efuse   : True if this MCU has an Extended Fuse byte (EFUSE)
MCUS = [
    {"display": "ATtiny85 (t85)", "id": "t85", "efuse": True},
    {"display": "ATmega16 (m16)", "id": "m16", "efuse": False},
    {"display": "ATmega32 (m32)", "id": "m32", "efuse": False},
    {"display": "ATmega328P (m328p)", "id": "m328p", "efuse": True},
]


def programmer_ids():
    """Return a list of the avrdude -c ids (strings only)."""
    return [p[1] for p in PROGRAMMERS]


def mcu_by_display(display):
    """Return the MCU dict that matches the given display name, or None."""
    for mcu in MCUS:
        if mcu["display"] == display:
            return mcu
    return None


def mcu_id_by_display(display):
    """Return the avrdude -p id for the given display name, or None."""
    mcu = mcu_by_display(display)
    return mcu["id"] if mcu else None


def mcu_supports_efuse(display):
    """Return True if the MCU has an EFUSE byte, False otherwise."""
    mcu = mcu_by_display(display)
    return mcu["efuse"] if mcu else False
