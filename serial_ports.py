r"""
COM-port detection helper built on top of pyserial.

If pyserial is not installed, the code falls back to scanning the Windows
registry-style list (COM1..COM9) so the GUI still launches instead of
crashing on a missing dependency.  With pyserial installed, real ports are
reported with their friendly descriptions (e.g. "USB Serial Device (COM5)").
"""

import os

try:
    import serial.tools.list_ports as _list_ports

    _HAVE_PYSERIAL = True
except ImportError:  # pragma: no cover - depends on user environment
    _HAVE_PYSERIAL = False


def list_ports():
    r"""
    Return a list of available COM ports.

    With pyserial installed, returns objects that have a ``device`` attribute
    (e.g. "COM3") and a ``description`` attribute (e.g. "Arduino Uno (COM3)").

    Without pyserial, returns simple "COMn" strings for COM1..COM9 that exist
    in the file system (Windows exposes them under \\.\).
    """
    if _HAVE_PYSERIAL:
        return list(_list_ports.comports())

    # Fallback: scan COM1..COM9 using the Windows \\.\ namespace.
    ports = []
    for n in range(1, 10):
        if os.path.exists(rf"\\.\COM{n}"):
            ports.append(f"COM{n}")
    return ports


def port_labels():
    """
    Return a list of human-readable strings suitable for a Tkinter dropdown.

    Each string looks like "COM3 - Arduino Uno (COM3)" when descriptions are
    available, or just "COM3" otherwise.
    """
    labels = []
    for port in list_ports():
        # pyserial returns an object; fallback returns a plain string.
        device = getattr(port, "device", port)
        description = getattr(port, "description", None)
        if description and description != device:
            labels.append(f"{device} - {description}")
        else:
            labels.append(device)
    return labels


def port_name_from_label(label):
    """
    Extract the bare port name (e.g. "COM3") from a label produced by
    port_labels().  If the label already is a bare name, it is returned as is.
    """
    if not label:
        return ""
    # Labels are "COM3 - description"; take the part before " - ".
    if " - " in label:
        return label.split(" - ", 1)[0]
    return label
