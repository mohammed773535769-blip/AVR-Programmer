"""
Thin wrapper around the avrdude.exe command-line tool.

This module never talks to a chip directly; it only locates avrdude, builds
argument lists, and runs it in a background thread so the Tkinter GUI stays
responsive.  All stdout/stderr is streamed back to the caller line by line.

Run order (see find_avrdude):
    1. <project folder>/avrdude/avrdude.exe
    2. C:\\avrdude\\avrdude.exe
"""

import os
import subprocess
import sys
import threading

# Fixed baud rate used everywhere in this app (per spec).
BAUDRATE = "19200"


def find_avrdude():
    """
    Locate avrdude.exe and its conf file.

    Returns a dict: {"exe": path_to_exe, "conf": path_to_conf}
    Returns None if avrdude could not be found.
    """
    # 1) Project-local folder: <this file's dir>/avrdude
    project_folder = os.path.dirname(os.path.abspath(__file__))
    local_folder = os.path.join(project_folder, "avrdude")
    if _check_folder(local_folder):
        return {
            "exe": os.path.join(local_folder, "avrdude.exe"),
            "conf": os.path.join(local_folder, "avrdude.conf"),
        }

    # 2) System-wide fallback: C:\avrdude
    system_folder = r"C:\avrdude"
    if _check_folder(system_folder):
        return {
            "exe": os.path.join(system_folder, "avrdude.exe"),
            "conf": os.path.join(system_folder, "avrdude.conf"),
        }

    return None


def _check_folder(folder):
    """Return True if both avrdude.exe and avrdude.conf exist in folder."""
    exe = os.path.join(folder, "avrdude.exe")
    conf = os.path.join(folder, "avrdude.conf")
    return os.path.isfile(exe) and os.path.isfile(conf)


# ---------------------------------------------------------------------------
# Command builders
# ---------------------------------------------------------------------------
# Each builder returns a list of arguments ready for subprocess.  The conf is
# passed via -C so the bundled avrdude.conf is always used, even if a system
# avrdude is later found on PATH.
#
# IMPORTANT: HEX paths are passed through exactly as supplied by Tkinter's
# filedialog.  Do not use pathlib, abspath, normpath, slash replacement, or
# manual quoting here.  A path containing spaces is safe because each item in
# this list is one subprocess argument and shell=False is used below.


def _common_args(avrdude, programmer, mcu_id, port):
    """Arguments shared by every command in this app."""
    args = [
        avrdude["exe"],
        "-C",
        avrdude["conf"],
        "-c",
        programmer,
        "-b",
        BAUDRATE,
        "-p",
        mcu_id,
    ]
    if port:
        args += ["-P", port]
    return args


def build_read_signature(avrdude, programmer, mcu_id, port):
    """avrdude -c <prog> -b 19200 -p <mcu> -P <com> -n"""
    return _common_args(avrdude, programmer, mcu_id, port) + ["-n"]


def build_program_flash(avrdude, programmer, mcu_id, port, hex_file):
    """Build one Intel HEX flash-write specifier without changing its path."""
    args = _common_args(avrdude, programmer, mcu_id, port)
    args.extend(["-U", "flash:w:" + hex_file + ":i"])
    return args


def build_verify_flash(avrdude, programmer, mcu_id, port, hex_file):
    """Build one Intel HEX flash-verify specifier without changing its path."""
    args = _common_args(avrdude, programmer, mcu_id, port)
    args.extend(["-U", "flash:v:" + hex_file + ":i"])
    return args


def build_read_fuses(avrdude, programmer, mcu_id, port, include_efuse):
    """Read lfuse, hfuse and (optionally) efuse without writing."""
    args = _common_args(avrdude, programmer, mcu_id, port)
    args += ["-U", "lfuse:r:-:h", "-U", "hfuse:r:-:h"]
    if include_efuse:
        args += ["-U", "efuse:r:-:h"]
    return args


def build_write_fuses(avrdude, programmer, mcu_id, port, lfuse, hfuse, efuse):
    """
    Write only the fuses that are not None.

    lfuse/hfuse/efuse are either a hex string like "0xE2" or None to skip.
    """
    args = _common_args(avrdude, programmer, mcu_id, port)
    if lfuse is not None:
        args += ["-U", f"lfuse:w:{lfuse}:m"]
    if hfuse is not None:
        args += ["-U", f"hfuse:w:{hfuse}:m"]
    if efuse is not None:
        args += ["-U", f"efuse:w:{efuse}:m"]
    return args


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run_avrdude(args, on_line, on_done):
    """
    Run an avrdude command in a background thread.

    The subprocess is started here and read line by line, so output is
    streamed (not buffered until the end).  Tkinter never calls this
    synchronously; the GUI receives results through the on_line/on_done
    callbacks, which the GUI marshals onto its own thread via a Queue.

    on_line : callable(str) called for every line of stdout/stderr (merged).
              Called from the worker thread only.
    on_done : callable(int return_code) called exactly once when the process
              exits (or fails to start).  Called from the worker thread only.
    """

    def safe(callback, *args):
        """Call a callback without stopping the worker thread on callback errors."""
        try:
            callback(*args)
        except Exception as exc:  # pragma: no cover - callback boundary  # noqa: BLE001
            print(f"[avrdude_runner] callback error: {exc}", file=sys.stderr)

    def worker():
        return_code = -1  # default if the process never starts
        proc = None
        try:
            if not isinstance(args, list):
                raise TypeError("avrdude arguments must be provided as a list")

            # Merge stderr into stdout so nothing is lost.  shell=False and a
            # list preserve Windows drive letters, slashes, and spaces exactly;
            # no manual quoting or escaping is needed.
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,  # line buffered
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW,  # hide console on Windows
            )
            # Read line by line until the process ends.  Because this is a
            # blocking readline on the worker thread (not the GUI thread),
            # the Tkinter event loop keeps running while lines stream in.
            for line in iter(proc.stdout.readline, ""):
                if line:
                    # Keep the trailing newline stripped for consistent display.
                    safe(on_line, line.rstrip("\r\n"))
            proc.stdout.close()
            return_code = proc.wait()
        except FileNotFoundError:
            safe(on_line, "[Error] avrdude.exe was not found at the expected path.")
            return_code = -1
        except Exception as exc:  # pragma: no cover - process boundary  # noqa: BLE001
            safe(on_line, f"[Error] Failed to run avrdude: {exc}")
            return_code = -1
            if proc is not None and proc.poll() is None:
                proc.kill()
        finally:
            safe(on_done, return_code)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
