"""
Tkinter GUI for the avrdude wrapper.

The window is intentionally laid out in three sections, top to bottom:

    TOP    : programmer / MCU / COM port / refresh / HEX file / browse
    MIDDLE : big action buttons (read signature, program, verify, read/write fuses)
    BOTTOM : scrollable console log

All avrdude work happens in a background thread (see avrdude_runner.run_avrdude).
Lines from that thread are pushed onto a queue, and the GUI polls the queue
with tk.after so updates always happen on the main thread - the safe way to
update Tkinter widgets.

The colour palette lives in PALETTE near the top so a future "dark mode" can
be added by swapping the palette (e.g. from a settings file) without touching
the layout code.
"""

import queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import avrdude_runner
import mcu_database
import serial_ports
import utils

# ---------------------------------------------------------------------------
# Colour palette (swap this for a future dark mode)
# ---------------------------------------------------------------------------
PALETTE = {
    "bg": "#f0f0f0",
    "console_bg": "#1e1e1e",
    "console_fg": "#dcdcdc",
    "ok": "#2e7d32",  # green
    "warn": "#ef6c00",  # orange
    "error": "#c62828",  # red
    "command": "#1565c0",  # blue (printed command header)
}

# Example fuse settings grouped by avrdude MCU id.  Preset selection only
# fills the editable fuse fields; it never starts an avrdude operation.
FUSE_PRESETS = {
    "m16": {
        "Internal 8MHz RC": {"lfuse": "0xE4", "hfuse": "0x99", "efuse": None},
        "External Crystal 8-16MHz": {"lfuse": "0xFF", "hfuse": "0x99", "efuse": None},
    },
    "m32": {
        "Internal 1MHz RC": {"lfuse": "0xE1", "hfuse": "0x99", "efuse": None},
        "External Crystal 8-16MHz": {"lfuse": "0xFF", "hfuse": "0x99", "efuse": None},
    },
    "m328p": {
        "Arduino UNO 16MHz Crystal": {
            "lfuse": "0xFF",
            "hfuse": "0xDE",
            "efuse": "0xFD",
        },
        "Internal 8MHz RC": {"lfuse": "0xE2", "hfuse": "0xD9", "efuse": "0xFF"},
    },
    "t85": {
        "Internal 8MHz RC": {"lfuse": "0xE2", "hfuse": "0xDF", "efuse": "0xFF"},
        "External Crystal": {"lfuse": "0xFF", "hfuse": "0xDF", "efuse": "0xFF"},
    },
}

FUSE_PRESET_WARNING = "Fuse presets are examples. Verify clock source and bootloader requirements before writing."


class AvrGui(tk.Tk):
    """The main application window."""

    def __init__(self):
        super().__init__()
        self.title("AVRDUDE GUI Wrapper")
        self.geometry("760x720")
        self.minsize(640, 600)
        self.configure(bg=PALETTE["bg"])

        # State
        self.avrdude = avrdude_runner.find_avrdude()
        self.hex_file = tk.StringVar(value="")
        self.programmer_var = tk.StringVar()
        self.mcu_var = tk.StringVar()
        self.port_var = tk.StringVar()
        self.lfuse_var = tk.StringVar()
        self.hfuse_var = tk.StringVar()
        self.efuse_var = tk.StringVar()
        self.lfuse_enabled = tk.BooleanVar(value=False)
        self.hfuse_enabled = tk.BooleanVar(value=False)
        self.efuse_enabled = tk.BooleanVar(value=False)

        # Queue used to ferry output lines from the worker thread to the GUI.
        self._log_queue = queue.Queue()
        self._busy = False
        self._last_action = None  # remember what was running (for result messages)
        self._collected_lines = []  # lines captured for parsing (signature/fuses)

        self._build_widgets()
        self._populate_defaults()
        self._refresh_ports()

        # Warn early if avrdude is missing, but still let the user see the GUI.
        if self.avrdude is None:
            self._log(utils.ERR_NO_AVRDUDE, color=PALETTE["error"])
            messagebox.showerror("avrdude not found", utils.ERR_NO_AVRDUDE)

        # Start polling the log queue (every 80 ms).
        self.after(80, self._poll_log_queue)

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def _build_widgets(self):
        # --- Top section: parameters --------------------------------
        top = ttk.LabelFrame(self, text="Parameters", padding=10)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(top, text="Programmer:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.programmer_combo = ttk.Combobox(
            top, textvariable=self.programmer_var, state="readonly", width=28
        )
        self.programmer_combo.grid(row=0, column=1, sticky=tk.W, pady=4, padx=4)

        ttk.Label(top, text="MCU:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.mcu_combo = ttk.Combobox(
            top, textvariable=self.mcu_var, state="readonly", width=28
        )
        self.mcu_combo.grid(row=1, column=1, sticky=tk.W, pady=4, padx=4)
        self.mcu_combo.bind("<<ComboboxSelected>>", self._on_mcu_changed)

        ttk.Label(top, text="COM Port:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.port_combo = ttk.Combobox(
            top, textvariable=self.port_var, state="readonly", width=28
        )
        self.port_combo.grid(row=2, column=1, sticky=tk.W, pady=4, padx=4)

        self.refresh_btn = ttk.Button(top, text="Refresh", command=self._refresh_ports)
        self.refresh_btn.grid(row=2, column=2, padx=6, pady=4)

        ttk.Label(top, text="HEX File:").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.hex_entry = ttk.Entry(
            top, textvariable=self.hex_file, state="readonly", width=42
        )
        self.hex_entry.grid(row=3, column=1, sticky=tk.W + tk.E, pady=4, padx=4)
        self.browse_btn = ttk.Button(top, text="Browse...", command=self._browse_hex)
        self.browse_btn.grid(row=3, column=2, padx=6, pady=4)

        top.columnconfigure(1, weight=1)

        # --- Middle section: fuse presets and editors ----------------
        fuse_frame = ttk.LabelFrame(self, text="Fuses", padding=10)
        fuse_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(fuse_frame, text="Fuse Preset:").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 5)
        )
        self.fuse_preset_var = tk.StringVar(value="")
        self.fuse_preset_combo = ttk.Combobox(
            fuse_frame,
            textvariable=self.fuse_preset_var,
            state="readonly",
            width=28,
        )
        self.fuse_preset_combo.grid(
            row=0, column=1, columnspan=2, sticky=tk.W, padx=4, pady=(0, 5)
        )
        self.fuse_preset_combo.bind(
            "<<ComboboxSelected>>", self._on_fuse_preset_selected
        )

        self.fuse_warning_label = ttk.Label(
            fuse_frame,
            text=FUSE_PRESET_WARNING,
            foreground=PALETTE["warn"],
            wraplength=650,
        )
        self.fuse_warning_label.grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(0, 5)
        )

        self._add_fuse_row(
            fuse_frame, "Low Fuse", self.lfuse_var, self.lfuse_enabled, 2
        )
        self._add_fuse_row(
            fuse_frame, "High Fuse", self.hfuse_var, self.hfuse_enabled, 3
        )
        self._add_fuse_row(
            fuse_frame, "Extended Fuse", self.efuse_var, self.efuse_enabled, 4
        )

        # --- Middle section: action buttons -------------------------
        actions = ttk.Frame(self, padding=10)
        actions.pack(fill=tk.X, padx=10, pady=5)

        self.sig_btn = ttk.Button(
            actions, text="Read Signature", command=self.on_read_signature
        )
        self.prog_btn = ttk.Button(
            actions, text="Program Flash", command=self.on_program_flash
        )
        self.verify_btn = ttk.Button(
            actions, text="Verify Flash", command=self.on_verify_flash
        )
        self.read_fuse_btn = ttk.Button(
            actions, text="Read Fuses", command=self.on_read_fuses
        )
        self.write_fuse_btn = ttk.Button(
            actions, text="Write Fuses", command=self.on_write_fuses
        )

        self.sig_btn.grid(row=0, column=0, sticky=tk.E + tk.W, padx=4, pady=4, ipady=8)
        self.prog_btn.grid(row=0, column=1, sticky=tk.E + tk.W, padx=4, pady=4, ipady=8)
        self.verify_btn.grid(
            row=0, column=2, sticky=tk.E + tk.W, padx=4, pady=4, ipady=8
        )
        self.read_fuse_btn.grid(
            row=1, column=0, sticky=tk.E + tk.W, padx=4, pady=4, ipady=8, columnspan=1
        )
        self.write_fuse_btn.grid(
            row=1, column=1, sticky=tk.E + tk.W, padx=4, pady=4, ipady=8, columnspan=2
        )

        for col in range(3):
            actions.columnconfigure(col, weight=1)

        # --- Bottom section: console --------------------------------
        console_frame = ttk.LabelFrame(self, text="Console Log", padding=4)
        console_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.console = tk.Text(
            console_frame,
            wrap=tk.WORD,
            bg=PALETTE["console_bg"],
            fg=PALETTE["console_fg"],
            insertbackground=PALETTE["console_fg"],
            font=("Consolas", 10),
            relief=tk.FLAT,
        )
        scroll = ttk.Scrollbar(console_frame, command=self.console.yview)
        self.console.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.console.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Tag colours for the console.
        self.console.tag_configure("ok", foreground="#7ec07e")
        self.console.tag_configure("warn", foreground="#f0a868")
        self.console.tag_configure("error", foreground="#f07a7a")
        self.console.tag_configure("cmd", foreground="#7ab0f0")

    def _add_fuse_row(self, parent, label, value_var, enabled_var, row):
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky=tk.W, pady=3)
        cb = ttk.Checkbutton(parent, variable=enabled_var)
        cb.grid(row=row, column=1, padx=4)
        entry = ttk.Entry(parent, textvariable=value_var, width=10)
        entry.grid(row=row, column=2, sticky=tk.W, padx=4, pady=3)
        # Keep a reference so we can disable the EFUSE entry for unsupported MCUs.
        if label == "Extended Fuse":
            self.efuse_entry = entry
            self.efuse_check = cb
            self._on_mcu_changed()  # initial enable/disable state

    # ------------------------------------------------------------------
    # Default values
    # ------------------------------------------------------------------
    def _populate_defaults(self):
        # Programmer dropdown.
        prog_labels = [p[0] for p in mcu_database.PROGRAMMERS]
        self.programmer_combo["values"] = prog_labels
        if prog_labels:
            self.programmer_var.set(prog_labels[0])

        # MCU dropdown.
        mcu_labels = [m["display"] for m in mcu_database.MCUS]
        self.mcu_combo["values"] = mcu_labels
        if mcu_labels:
            self.mcu_var.set(mcu_labels[0])
            self._on_mcu_changed()

    # ------------------------------------------------------------------
    # Port handling
    # ------------------------------------------------------------------
    def _refresh_ports(self):
        labels = serial_ports.port_labels()
        self.port_combo["values"] = labels
        if labels:
            # Keep current selection if still present, else pick the first.
            current = self.port_var.get()
            if current not in labels:
                self.port_var.set(labels[0])
        else:
            self.port_var.set("")
            self._log(
                "No COM ports detected. Connect your programmer and click Refresh.",
                color=PALETTE["warn"],
            )

    # ------------------------------------------------------------------
    # HEX file browse
    # ------------------------------------------------------------------
    def _browse_hex(self):
        path = filedialog.askopenfilename(
            title="Select HEX file",
            filetypes=[("Intel HEX files", "*.hex"), ("All files", "*.*")],
        )
        if path:
            # Diagnostic: log the EXACT string returned by the OS file dialog,
            # so it is visible that we never transform the path (no drive-letter
            # or slash conversion happens anywhere in this app).
            self._log(f"Selected HEX file: {path}", color=PALETTE["command"])
            self.hex_file.set(path)

    # ------------------------------------------------------------------
    # MCU change -> update presets and enable/disable EFUSE control
    # ------------------------------------------------------------------
    def _on_mcu_changed(self, event=None):
        supports_efuse = mcu_database.mcu_supports_efuse(self.mcu_var.get())
        new_state = "normal" if supports_efuse else "disabled"
        if hasattr(self, "efuse_entry"):
            self.efuse_entry.configure(state=new_state)
            self.efuse_check.configure(state=new_state)
        if not supports_efuse:
            self.efuse_var.set("")
            self.efuse_enabled.set(False)

        # Presets are keyed by the avrdude MCU id, not the display label.
        mcu_id = self._selected_mcu_id()
        preset_names = list(FUSE_PRESETS.get(mcu_id, {}).keys())
        self.fuse_preset_combo["values"] = preset_names
        self.fuse_preset_var.set("")

    def _on_fuse_preset_selected(self, event=None):
        """Copy the selected preset into fields; do not start any operation."""
        mcu_id = self._selected_mcu_id()
        preset = FUSE_PRESETS.get(mcu_id, {}).get(self.fuse_preset_var.get())
        if not preset:
            return

        self.lfuse_var.set(preset["lfuse"] or "")
        self.hfuse_var.set(preset["hfuse"] or "")
        self.efuse_var.set(preset["efuse"] or "")

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def _selected_programmer_id(self):
        label = self.programmer_var.get()
        for display, pid in mcu_database.PROGRAMMERS:
            if display == label:
                return pid
        return None

    def _selected_mcu_id(self):
        return mcu_database.mcu_id_by_display(self.mcu_var.get())

    def _selected_port_name(self):
        return serial_ports.port_name_from_label(self.port_var.get())

    def _check_common(self, need_hex=False, need_port=True):
        """Validate inputs shared by several actions. Returns True if OK."""
        if self.avrdude is None:
            self._log(utils.ERR_NO_AVRDUDE, color=PALETTE["error"])
            messagebox.showerror("avrdude not found", utils.ERR_NO_AVRDUDE)
            return False
        if need_port and not self._selected_port_name():
            self._log(utils.ERR_NO_COM, color=PALETTE["error"])
            messagebox.showerror("No COM port", utils.ERR_NO_COM)
            return False
        if need_hex:
            if not self.hex_file.get():
                self._log(utils.ERR_NO_HEX, color=PALETTE["error"])
                messagebox.showerror("No HEX file", utils.ERR_NO_HEX)
                return False
            if not utils.looks_like_hex(self.hex_file.get()):
                self._log(utils.ERR_INVALID_HEX, color=PALETTE["error"])
                messagebox.showerror("Invalid HEX", utils.ERR_INVALID_HEX)
                return False
        return True

    # ------------------------------------------------------------------
    # Console helpers (thread-safe via queue)
    # ------------------------------------------------------------------
    def _log(self, text, color=None):
        """Put a message on the queue to be shown in the console.

        Standardised protocol: every message is a 2-tuple
            (kind, payload)
        where kind == "text"  -> payload is (text, color)
              kind == "line"   -> payload is a single output line (str)
              kind == "action_done" -> payload is a return code (int)
        Both producers (main thread via _log, and the worker thread via
        _on_line / _on_done) use the exact same shape, so the consumer can
        unpack a 2-tuple safely.
        """
        self._log_queue.put(("text", (text, color)))

    def _log_command(self, args):
        self._log_queue.put(
            ("text", ("$ " + utils.pretty_command(args), PALETTE["command"]))
        )

    def _poll_log_queue(self):
        """Drain the queue on the Tkinter main thread.

        Every call processes ALL pending messages (so a burst of avrdude
        output is rendered without delay), then reschedules itself.  Any
        unexpected error inside a handler is caught and written to the
        console rather than crashing the event loop.
        """
        try:
            while True:
                kind, payload = self._log_queue.get_nowait()
                try:
                    if kind == "text":
                        text, color = payload
                        tag = self._color_tag(color)
                        self.console.configure(state=tk.NORMAL)
                        self.console.insert(tk.END, text + "\n", tag)
                        self.console.see(tk.END)
                        self.console.configure(state=tk.DISABLED)
                    elif kind == "line":
                        self.console.configure(state=tk.NORMAL)
                        self.console.insert(tk.END, payload + "\n")
                        self.console.see(tk.END)
                        self.console.configure(state=tk.DISABLED)
                    elif kind == "action_done":
                        self._handle_action_done(payload)
                    else:
                        # Unknown message type - log it instead of crashing.
                        self.console.configure(state=tk.NORMAL)
                        self.console.insert(
                            tk.END, f"[unknown queue message] {kind!r}\n"
                        )
                        self.console.see(tk.END)
                        self.console.configure(state=tk.DISABLED)
                except Exception as exc:  # noqa: BLE001
                    self.console.configure(state=tk.NORMAL)
                    self.console.insert(tk.END, f"[GUI error] {exc}\n", "error")
                    self.console.see(tk.END)
                    self.console.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(80, self._poll_log_queue)

    def _color_tag(self, color):
        mapping = {
            PALETTE["ok"]: "ok",
            PALETTE["warn"]: "warn",
            PALETTE["error"]: "error",
            PALETTE["command"]: "cmd",
        }
        return mapping.get(color)

    # ------------------------------------------------------------------
    # Running avrdude
    # ------------------------------------------------------------------
    def _run(self, args, action_name):
        if self._busy:
            self._log(
                "A command is already running. Please wait...", color=PALETTE["warn"]
            )
            return
        self._busy = True
        self._last_action = action_name
        self._collected_lines = []
        self._set_buttons_state(tk.DISABLED)
        self._log_command(args)

        avrdude_runner.run_avrdude(
            args,
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _on_line(self, line):
        # Called from the worker thread - just queue it for the GUI.
        self._log_queue.put(("line", line))
        self._collected_lines.append(line)

    def _on_done(self, return_code):
        # Called from the worker thread.
        self._log_queue.put(("action_done", return_code))

    def _handle_action_done(self, return_code):
        # Called on the main thread (from _poll_log_queue).
        action = self._last_action
        self._last_action = None
        self._busy = False
        self._set_buttons_state(tk.NORMAL)

        if action == "read_signature":
            sig = utils.parse_signature(self._collected_lines)
            if sig:
                self._log(f"Device signature = {sig}", color=PALETTE["ok"])
            elif return_code != 0:
                self._log(
                    "Could not read the device signature.", color=PALETTE["error"]
                )
        elif action == "program_flash":
            if return_code == 0:
                self._log("Programming complete.", color=PALETTE["ok"])
            else:
                self._log(utils.ERR_PROGRAMMING_FAILED, color=PALETTE["error"])
                messagebox.showerror("Programming failed", utils.ERR_PROGRAMMING_FAILED)
        elif action == "verify_flash":
            if return_code == 0:
                self._log("Verification OK.", color=PALETTE["ok"])
            else:
                self._log(utils.ERR_VERIFY_FAILED, color=PALETTE["error"])
                messagebox.showerror("Verification failed", utils.ERR_VERIFY_FAILED)
        elif action == "read_fuses":
            if return_code == 0:
                fuses = utils.parse_fuses_from_output(self._collected_lines)
                if fuses["lfuse"]:
                    self.lfuse_var.set(fuses["lfuse"][2:].upper())  # strip "0x"
                if fuses["hfuse"]:
                    self.hfuse_var.set(fuses["hfuse"][2:].upper())
                if fuses["efuse"]:
                    self.efuse_var.set(fuses["efuse"][2:].upper())
                self._log("Fuses read successfully.", color=PALETTE["ok"])
            else:
                self._log("Failed to read fuses.", color=PALETTE["error"])
        elif action == "write_fuses":
            if return_code == 0:
                self._log("Fuses written successfully.", color=PALETTE["ok"])
            else:
                self._log(utils.ERR_FUSE_WRITE_FAILED, color=PALETTE["error"])
                messagebox.showerror("Fuse write failed", utils.ERR_FUSE_WRITE_FAILED)

    def _set_buttons_state(self, state):
        for btn in (
            self.sig_btn,
            self.prog_btn,
            self.verify_btn,
            self.read_fuse_btn,
            self.write_fuse_btn,
        ):
            btn.configure(state=state)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------
    def on_read_signature(self):
        if not self._check_common(need_port=True):
            return
        args = avrdude_runner.build_read_signature(
            self.avrdude,
            self._selected_programmer_id(),
            self._selected_mcu_id(),
            self._selected_port_name(),
        )
        self._run(args, "read_signature")

    def on_program_flash(self):
        if not self._check_common(need_hex=True, need_port=True):
            return
        args = avrdude_runner.build_program_flash(
            self.avrdude,
            self._selected_programmer_id(),
            self._selected_mcu_id(),
            self._selected_port_name(),
            self.hex_file.get(),
        )
        self._run(args, "program_flash")

    def on_verify_flash(self):
        if not self._check_common(need_hex=True, need_port=True):
            return
        args = avrdude_runner.build_verify_flash(
            self.avrdude,
            self._selected_programmer_id(),
            self._selected_mcu_id(),
            self._selected_port_name(),
            self.hex_file.get(),
        )
        self._run(args, "verify_flash")

    def on_read_fuses(self):
        if not self._check_common(need_port=True):
            return
        include_efuse = mcu_database.mcu_supports_efuse(self.mcu_var.get())
        args = avrdude_runner.build_read_fuses(
            self.avrdude,
            self._selected_programmer_id(),
            self._selected_mcu_id(),
            self._selected_port_name(),
            include_efuse,
        )
        self._run(args, "read_fuses")

    def on_write_fuses(self):
        if not self._check_common(need_port=True):
            return

        # Build the list of fuses to actually write.
        lfuse = hfuse = efuse = None
        any_selected = False

        if self.lfuse_enabled.get():
            lfuse = utils.normalize_fuse_value(self.lfuse_var.get())
            if lfuse is None:
                self._log(
                    "Low Fuse: " + utils.ERR_FUSE_BAD_VALUE, color=PALETTE["error"]
                )
                messagebox.showerror("Bad fuse value", utils.ERR_FUSE_BAD_VALUE)
                return
            any_selected = True

        if self.hfuse_enabled.get():
            hfuse = utils.normalize_fuse_value(self.hfuse_var.get())
            if hfuse is None:
                self._log(
                    "High Fuse: " + utils.ERR_FUSE_BAD_VALUE, color=PALETTE["error"]
                )
                messagebox.showerror("Bad fuse value", utils.ERR_FUSE_BAD_VALUE)
                return
            any_selected = True

        if self.efuse_enabled.get() and mcu_database.mcu_supports_efuse(
            self.mcu_var.get()
        ):
            efuse = utils.normalize_fuse_value(self.efuse_var.get())
            if efuse is None:
                self._log(
                    "Extended Fuse: " + utils.ERR_FUSE_BAD_VALUE, color=PALETTE["error"]
                )
                messagebox.showerror("Bad fuse value", utils.ERR_FUSE_BAD_VALUE)
                return
            any_selected = True

        if not any_selected:
            self._log(utils.ERR_FUSE_NO_SELECTION, color=PALETTE["error"])
            messagebox.showerror("No fuse selected", utils.ERR_FUSE_NO_SELECTION)
            return

        args = avrdude_runner.build_write_fuses(
            self.avrdude,
            self._selected_programmer_id(),
            self._selected_mcu_id(),
            self._selected_port_name(),
            lfuse,
            hfuse,
            efuse,
        )
        self._run(args, "write_fuses")
