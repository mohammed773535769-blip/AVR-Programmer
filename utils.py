"""
Small helper functions used by the GUI layer.

Kept separate from the GUI so they can be unit-tested or reused without
pulling in Tkinter.  Everything here is intentionally simple and self-contained.
"""

import os
import re

# ---------------------------------------------------------------------------
# Friendly error messages
# ---------------------------------------------------------------------------
# Centralised so the wording stays consistent across the whole app.

ERR_NO_COM = "No COM port selected. Please pick a port from the dropdown and try again."
ERR_NO_HEX = "No HEX file selected. Please click Browse and choose a .hex file."
ERR_NO_AVRDUDE = (
    "avrdude was not found.\n\n"
    "Expected one of:\n"
    "  - ./avrdude/avrdude.exe (inside the project folder)\n"
    "  - C:\\avrdude\\avrdude.exe\n\n"
    "Please place avrdude.exe and avrdude.conf in one of these folders."
)
ERR_INVALID_HEX = (
    "The selected file does not look like a valid .hex file. Please choose a .hex file."
)
ERR_PROGRAMMING_FAILED = "Programming failed. Check the console log for details."
ERR_VERIFY_FAILED = "Verification failed. The flash contents do not match the HEX file."
ERR_FUSE_WRITE_FAILED = "Fuse write failed. Check the console log for details."
ERR_FUSE_NO_SELECTION = (
    "No fuse byte is selected. Tick at least one fuse checkbox before writing."
)
ERR_FUSE_BAD_VALUE = "Fuse values must be a valid hex byte, e.g. 0xE2 or E2."


# ---------------------------------------------------------------------------
# HEX file helpers
# ---------------------------------------------------------------------------


def looks_like_hex(path):
    """
    Basic sanity check that a file looks like an Intel HEX file.

    A valid Intel HEX line starts with ':' and the file is non-empty.
    This is a quick heuristic, not a full parser - enough to warn the user
    before sending a wrong file to avrdude.
    """
    if not path or not os.path.isfile(path):
        return False
    if not path.lower().endswith(".hex"):
        return False
    try:
        with open(path, "r", encoding="ascii", errors="replace") as f:
            for _ in range(50):  # only peek at the first lines
                line = f.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped:
                    return stripped.startswith(":")
            return False
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Fuse value helpers
# ---------------------------------------------------------------------------


def normalize_fuse_value(text):
    """
    Accept user input like "0xE2", "E2", "0xe2", "e2" and return the
    canonical "0xE2" form (upper-case, with 0x prefix).

    Returns None if the value is empty or invalid.
    """
    if text is None:
        return None
    text = text.strip()
    if text == "":
        return None
    # Allow optional 0x prefix.
    cleaned = text[2:] if text.lower().startswith("0x") else text
    if not re.fullmatch(r"[0-9a-fA-F]{1,2}", cleaned):
        return None
    return "0x" + cleaned.upper().zfill(2)


def is_valid_fuse_value(text):
    """True if normalize_fuse_value would succeed for the given text."""
    return normalize_fuse_value(text) is not None


# ---------------------------------------------------------------------------
# avrdude output parsing
# ---------------------------------------------------------------------------

# Matches lines like:
#   Device signature = 0x1E9403
#   avrdude: Device signature = 0x1e9403
_SIGNATURE_RE = re.compile(r"signature\s*=\s*(0x[0-9a-fA-F]{6})", re.IGNORECASE)

# Matches the hex dump produced by "-U lfuse:r:-:h" style reads, e.g.:
#   :01000000E22F        -> data byte E2
# We only care about the data byte of a single-byte record.
_HEX_BYTE_RE = re.compile(r"^:01000000([0-9A-Fa-f]{2})")


def parse_signature(lines):
    """
    Search a list of avrdude output lines for a device signature.

    Returns the signature string (e.g. "0x1E9403") or None.
    """
    for line in lines:
        m = _SIGNATURE_RE.search(line)
        if m:
            return m.group(1)
    return None


def parse_fuses_from_output(lines):
    """
    Parse lfuse/hfuse/efuse values from avrdude "r:-:h" output.

    avrdude prints a single-line Intel-HEX record for each fuse read, in the
    order they were requested (lfuse, hfuse, efuse).  Missing records or an
    unsupported efuse result in a None value.

    Returns a dict: {"lfuse": "0xE2"|None, "hfuse": "0xD9"|None, "efuse": ...}
    """
    result = {"lfuse": None, "hfuse": None, "efuse": None}
    found = []
    for line in lines:
        m = _HEX_BYTE_RE.match(line.strip())
        if m:
            found.append("0x" + m.group(1).upper())

    keys = ["lfuse", "hfuse", "efuse"]
    for i, value in enumerate(found):
        if i < len(keys):
            result[keys[i]] = value
    return result


# ---------------------------------------------------------------------------
# Small GUI helpers
# ---------------------------------------------------------------------------


def pretty_command(args):
    """Turn an argument list into a readable string for the console header."""
    # Quote paths that contain spaces.
    parts = []
    for a in args:
        if " " in a:
            parts.append(f'"{a}"')
        else:
            parts.append(a)
    return " ".join(parts)
