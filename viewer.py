"""
Lightweight CSV/TSV viewer.

- Multiple tabs (one per open file)
- Sort by column (click the header)
- Reorder columns (drag the header)
- Quickly switch delimiter per tab
- Open files passed via command line (for Windows file association)
- Drag and drop files onto the window to open them in a new tab (requires tkinterdnd2)

Dependencies: none beyond the Python stdlib.
Optional: tkinterdnd2 (drag-and-drop) -- pip install tkinterdnd2
"""
import contextlib
import csv
import json
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

DELIMITER_PRESETS = [(",", ","), (";", ";"), ("Tab", "\t"), ("|", "|")]

# row-count limit, just a basic memory/UI safeguard
MAX_ROWS_WARN = 200_000

# color palettes (light/dark) -- covers both the "hand-drawn" elements
# (zebra striping, separator lines, cell highlight, links) and the ttk style
PALETTES = {
    "light": {
        "stripe_even": "#ffffff",
        "stripe_odd": "#f0f4f8",
        "separator": "#c9c9c9",
        "cell_highlight": "#2f6fed",
        "link_fg": "#0645ad",
    },
    "dark": {
        "stripe_even": "#1e1e1e",
        "stripe_odd": "#262626",
        "separator": "#3c3c3c",
        "cell_highlight": "#569cd6",
        "link_fg": "#4fa8ff",
        # only used in dark mode, to style the ttk widgets (theme 'clam')
        "app_bg": "#1e1e1e",
        "fg": "#dcdcdc",
        "tree_bg": "#1e1e1e",
        "tree_fg": "#dcdcdc",
        "heading_bg": "#2d2d2d",
        "heading_fg": "#ffffff",
        "select_bg": "#264f78",
        "select_fg": "#ffffff",
        "entry_bg": "#2d2d2d",
        "menu_bg": "#2d2d2d",
        "menu_fg": "#dcdcdc",
        "menu_active_bg": "#264f78",
        "menu_active_fg": "#ffffff",
    },
}

URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)


def looks_like_url(value):
    return bool(value) and bool(URL_RE.match(value.strip()))


def open_link(value):
    value = value.strip()
    if value.lower().startswith("www."):
        value = "http://" + value
    webbrowser.open(value)

# when double-clicking to auto-fit column width, only look at up to
# this many rows (performance safeguard for huge files)
AUTOSIZE_SAMPLE_LIMIT = 5000

# how many rows to check to decide whether a column "has links" (sampling only)
LINK_DETECT_SAMPLE_LIMIT = 2000

# delay before a header click actually triggers a sort -- gives time
# to detect whether it turns into a double-click (e.g. trying to resize the border)
SORT_CLICK_DELAY_MS = 300

# table zoom limits (in %)
ZOOM_MIN = 50
ZOOM_MAX = 200
ZOOM_STEP = 10
ZOOM_DEFAULT = 100
BASE_ROW_HEIGHT = 20  # row height at "normal" (100%), in pixels

# minimum column width (neither manual resize nor "shrink to fit" go below this)
MIN_COLUMN_WIDTH = 60

# "pan" mode (middle-click, browser/PDF-reader style)
PAN_DEADZONE_PX = 12       # dead radius at the center where nothing scrolls
PAN_MAX_SPEED_UNITS = 24   # maximum scroll speed per tick
PAN_TICK_MS = 40           # scroll loop interval

# persisted config file (zoom, theme, recent files, etc.)
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "CSVViewer")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def resource_path(*parts):
    """Absolute path to a bundled resource.

    Works both when running from source and from a PyInstaller build, which
    unpacks bundled data into a temporary folder pointed at by sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
    except OSError:
        pass  # don't crash the app if saving fails (e.g. no permission)


def sniff_delimiter(sample_text, fallback_from_ext=None):
    """Try to detect the delimiter. If it fails, use the one suggested by the extension, or ','."""
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return fallback_from_ext or ","


def read_csv_file(path, delimiter=None):
    """Reads the whole file and returns (header, rows, delimiter_used, encoding_used)."""
    ext = os.path.splitext(path)[1].lower()
    default_by_ext = "\t" if ext == ".tsv" else ","

    # try utf-8-sig (handles BOM), fall back to latin-1 on error
    encodings_to_try = ["utf-8-sig", "cp1252", "latin-1"]
    text = None
    used_encoding = None
    for enc in encodings_to_try:
        try:
            with open(path, encoding=enc, newline="") as f:
                text = f.read()
            used_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise OSError(f"Could not decode file: {path}")

    if delimiter is None:
        sample = text[:4096]
        delimiter = sniff_delimiter(sample, fallback_from_ext=default_by_ext)

    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return [], [], delimiter, used_encoding

    header = rows[0]
    data = rows[1:]
    # normalize column count (short rows get "" padding at the end)
    ncols = len(header)
    data = [r + [""] * (ncols - len(r)) if len(r) < ncols else r[:ncols] for r in data]
    return header, data, delimiter, used_encoding


class CSVTab(ttk.Frame):
    def __init__(self, master, filepath=None, on_drop_files=None,
                 zoom_label_var=None, on_zoom_delta=None, on_zoom_reset=None,
                 get_palette=None, dark_mode_var=None, on_theme_toggle=None):
        super().__init__(master)
        self.get_palette = get_palette or (lambda: PALETTES["light"])
        self.dark_mode_var = dark_mode_var
        self.on_theme_toggle = on_theme_toggle
        self.filepath = filepath
        self.header = []
        self.rows = []
        self.sort_state = {}  # col_id -> ascending bool
        self._drag_col = None
        self._drag_start_x = None
        self.on_drop_files = on_drop_files
        self._sep_frames = []  # thin separator lines between columns
        self._pending_sort_after_id = None  # delayed sort so it doesn't fire together with a double-click
        self._sep_loop_started = False
        self.zoom_label_var = zoom_label_var
        self.on_zoom_delta = on_zoom_delta
        self.on_zoom_reset = on_zoom_reset
        self._selected_cell = None  # (row_iid, col_id) of the clicked cell, for copying
        self._cell_highlight_frames = []  # 4 thin borders around the selected cell
        self._link_col_idxs = set()  # indices of columns that contain links
        self._link_labels = []  # pool of blue/underlined Labels overlaid on link cells
        self._pan_active = False
        self._pan_anchor = (0, 0)
        self._pan_after_id = None
        self._search_visible = False
        self._search_matches = []  # list of (row_iid, col_id)
        self._search_index = -1
        self._search_after_id = None

        self._build_toolbar()
        self._build_tree()
        self._build_statusbar()
        self._register_dnd()

        if filepath:
            self.load(filepath)

    def _register_dnd(self):
        if not HAS_DND or self.on_drop_files is None:
            return
        # register both the frame and the treeview, since the drop can
        # land on either one
        for widget in (self, self.tree):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._handle_drop)

    def _handle_drop(self, event):
        paths = self.tk.splitlist(event.data)
        if self.on_drop_files:
            self.on_drop_files(paths)

    # ---------- UI ----------
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side=tk.TOP, fill=tk.X, padx=4, pady=3)

        ttk.Label(bar, text="Delimiter:").pack(side=tk.LEFT, padx=(0, 4))

        self.delim_var = tk.StringVar(value=",")
        self.delim_combo = ttk.Combobox(
            bar, textvariable=self.delim_var, width=6,
            values=[label for label, _ in DELIMITER_PRESETS],
        )
        self.delim_combo.pack(side=tk.LEFT)
        self.delim_combo.bind("<<ComboboxSelected>>", lambda e: self._on_delimiter_change())

        ttk.Label(bar, text="  Custom:").pack(side=tk.LEFT)
        self.custom_delim_var = tk.StringVar(value="")
        custom_entry = ttk.Entry(bar, textvariable=self.custom_delim_var, width=4)
        custom_entry.pack(side=tk.LEFT, padx=(2, 6))
        custom_entry.bind("<Return>", lambda e: self._apply_custom_delimiter())

        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="Auto-detect", variable=self.auto_var,
            command=self._on_auto_toggle,
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(bar, text="Reload", command=self.reload).pack(side=tk.LEFT)

        self._build_search_bar(bar)

    def _build_search_bar(self, bar):
        """Search bar (Ctrl+F) -- stays hidden until triggered."""
        self._search_frame = ttk.Frame(bar)
        # not packed yet -- only appears when show_search() is called

        ttk.Label(self._search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 4))

        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(self._search_frame, textvariable=self._search_var, width=20)
        self._search_entry.pack(side=tk.LEFT)
        self._search_var.trace_add("write", lambda *a: self._on_search_text_changed())
        self._search_entry.bind("<Return>", lambda e: self._search_step(1))
        self._search_entry.bind("<Shift-Return>", lambda e: self._search_step(-1))
        self._search_entry.bind("<Down>", lambda e: self._search_step(1))
        self._search_entry.bind("<Up>", lambda e: self._search_step(-1))
        self._search_entry.bind("<Escape>", self.hide_search)

        self._search_status_var = tk.StringVar(value="")
        ttk.Label(self._search_frame, textvariable=self._search_status_var, width=9).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Button(self._search_frame, text="▲", width=2, command=lambda: self._search_step(-1)).pack(side=tk.LEFT)
        ttk.Button(self._search_frame, text="▼", width=2, command=lambda: self._search_step(1)).pack(side=tk.LEFT)
        ttk.Button(self._search_frame, text="✕", width=2, command=self.hide_search).pack(side=tk.LEFT, padx=(2, 0))

    @staticmethod
    def _make_autohide_scrollbar(scrollbar):
        """Wraps the scrollbar's 'set' so it hides itself automatically when the
        whole content already fits on screen (nothing to scroll), and reappears when needed."""
        def set_and_autohide(first, last):
            first, last = float(first), float(last)
            if first <= 0.0 and last >= 1.0:
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
            scrollbar.set(first, last)
        return set_and_autohide

    def _build_tree(self):
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(container, show="headings")
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(
            yscrollcommand=self._make_autohide_scrollbar(vsb),
            xscrollcommand=self._make_autohide_scrollbar(hsb),
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self._refresh_row_tags()

        # drag to reorder columns (also selects the clicked cell)
        self.tree.bind("<ButtonPress-1>", self._on_heading_press)
        self.tree.bind("<B1-Motion>", self._on_heading_drag)
        self.tree.bind("<ButtonRelease-1>", self._on_heading_release)
        # double-click on the border between columns -> auto-fits width to content
        self.tree.bind("<Double-Button-1>", self._on_heading_double_click)
        # ctrl+scroll also controls zoom, in addition to the buttons in the status bar
        self.tree.bind("<Control-MouseWheel>", self._on_ctrl_mousewheel)
        # copy selected cell
        self.tree.bind("<Control-c>", self._copy_selected_cell)
        self.tree.bind("<Button-3>", self._on_right_click)
        # links: ctrl+click opens in the browser; hand cursor on hover
        self.tree.bind("<Control-Button-1>", self._on_ctrl_click)
        # "pan" mode (middle-click, browser/PDF-reader style)
        self.tree.bind("<ButtonPress-2>", self._start_pan)
        self.tree.bind("<ButtonRelease-2>", lambda e: self._stop_pan())
        self.tree.bind("<Motion>", self._on_motion)

    def _on_motion(self, event):
        region = self.tree.identify_region(event.x, event.y)
        value = ""
        if region == "cell":
            row = self.tree.identify_row(event.y)
            col = self.tree.identify_column(event.x)
            if row and col:
                value = self.tree.set(row, col)
        self.tree.config(cursor="hand2" if looks_like_url(value) else "")

    def _on_ctrl_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row or not col:
            return
        value = self.tree.set(row, col)
        if looks_like_url(value):
            open_link(value)
            self._flash_status(f"Opening link: {value[:60]}")

    # ---------- select/copy cell ----------
    def _select_cell(self, x, y):
        row = self.tree.identify_row(y)
        col = self.tree.identify_column(x)
        if not row or not col:
            self._selected_cell = None
            self._hide_cell_highlight()
            return
        self._selected_cell = (row, col)
        self._update_cell_highlight()

    def _hide_cell_highlight(self):
        for f in self._cell_highlight_frames:
            f.place_forget()

    def _update_cell_highlight(self):
        if not self._selected_cell:
            self._hide_cell_highlight()
            return
        row, col = self._selected_cell
        bbox = self.tree.bbox(row, col)
        if not bbox:
            self._hide_cell_highlight()
            return
        x, y, w, h = bbox
        color = self.get_palette()["cell_highlight"]
        while len(self._cell_highlight_frames) < 4:
            self._cell_highlight_frames.append(tk.Frame(self.tree, bg=color))
        top, bottom, left, right = self._cell_highlight_frames
        for f in (top, bottom, left, right):
            f.configure(bg=color)
        thickness = 2
        top.place(x=x, y=y, width=w, height=thickness)
        bottom.place(x=x, y=y + h - thickness, width=w, height=thickness)
        left.place(x=x, y=y, width=thickness, height=h)
        right.place(x=x + w - thickness, y=y, width=thickness, height=h)

    def _copy_selected_cell(self, event=None):
        if not self._selected_cell:
            return
        row, col = self._selected_cell
        if not self.tree.exists(row):
            return
        value = self.tree.set(row, col)
        self.clipboard_clear()
        self.clipboard_append(value)
        preview = value if len(value) <= 60 else value[:60] + "..."
        self._flash_status(f"Copied: {preview}")
        return "break"

    def _flash_status(self, text, ms=1800):
        """Shows a temporary message in the status bar (e.g. copy confirmation)."""
        if self._flash_after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._flash_after_id)
        self._flash_var.set(text)
        self._flash_after_id = self.after(ms, lambda: self._flash_var.set(""))

    def _on_right_click(self, event):
        if self._pan_active:
            self._stop_pan()
            return
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        self._select_cell(event.x, event.y)
        menu = tk.Menu(self, tearoff=0)
        palette = self.get_palette()
        if "menu_bg" in palette:  # only dark mode defines these keys
            menu.configure(
                bg=palette["menu_bg"], fg=palette["menu_fg"],
                activebackground=palette["menu_active_bg"], activeforeground=palette["menu_active_fg"],
            )
        menu.add_command(label="Copy cell", command=self._copy_selected_cell)
        menu.tk_popup(event.x_root, event.y_root)

    def _on_ctrl_mousewheel(self, event):
        if self.on_zoom_delta:
            self.on_zoom_delta(10 if event.delta > 0 else -10)

    # ---------- "pan" mode (hold the middle button, browser/PDF-reader style) ----------
    def _start_pan(self, event):
        self._pan_active = True
        self._pan_anchor = (event.x_root, event.y_root)
        self.tree.config(cursor="fleur")
        self._pan_tick()

    def _stop_pan(self):
        self._pan_active = False
        self.tree.config(cursor="")
        if self._pan_after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._pan_after_id)
            self._pan_after_id = None

    def _pan_tick(self):
        if not self._pan_active:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        px, py = self.tree.winfo_pointerxy()
        ax, ay = self._pan_anchor
        dx, dy = px - ax, py - ay

        def scroll_units(d):
            if abs(d) < PAN_DEADZONE_PX:
                return 0
            excess = abs(d) - PAN_DEADZONE_PX
            units = 1 + excess // 17  # smaller divisor = accelerates faster with distance
            units = min(units, PAN_MAX_SPEED_UNITS)
            return units if d > 0 else -units

        sx, sy = scroll_units(dx), scroll_units(dy)
        if sx:
            self.tree.xview_scroll(sx, "units")
        if sy:
            self.tree.yview_scroll(sy, "units")

        with contextlib.suppress(tk.TclError):
            self._pan_after_id = self.after(PAN_TICK_MS, self._pan_tick)

    def _build_statusbar(self):
        bar = ttk.Frame(self)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 2))

        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        self._flash_var = tk.StringVar(value="")
        self._flash_after_id = None
        ttk.Label(bar, textvariable=self._flash_var, foreground="#2f6fed").pack(
            side=tk.LEFT, padx=(6, 6)
        )

        if self.on_zoom_delta is not None:
            zoom_frame = ttk.Frame(bar)
            zoom_frame.pack(side=tk.RIGHT)
            ttk.Label(zoom_frame, text="Zoom:").pack(side=tk.LEFT, padx=(0, 3))
            ttk.Button(
                zoom_frame, text="-", width=2, command=lambda: self.on_zoom_delta(-10)
            ).pack(side=tk.LEFT)
            ttk.Label(
                zoom_frame, textvariable=self.zoom_label_var, width=5, anchor="center"
            ).pack(side=tk.LEFT)
            ttk.Button(
                zoom_frame, text="+", width=2, command=lambda: self.on_zoom_delta(10)
            ).pack(side=tk.LEFT)
            ttk.Button(
                zoom_frame, text="Reset", command=self.on_zoom_reset
            ).pack(side=tk.LEFT, padx=(4, 0))

        if self.on_theme_toggle is not None:
            ttk.Checkbutton(
                bar, text="Dark mode", variable=self.dark_mode_var,
                command=self.on_theme_toggle,
            ).pack(side=tk.RIGHT, padx=(0, 10))

    # ---------- loading ----------
    def load(self, filepath, delimiter=None):
        try:
            header, rows, used_delim, used_enc = read_csv_file(filepath, delimiter=delimiter)
        except Exception as exc:
            messagebox.showerror("Error opening file", str(exc))
            return

        self.filepath = filepath
        self.header = header
        self.rows = rows
        self._set_delim_ui(used_delim)
        self._populate_tree()

        n_rows = len(rows)
        warn = "  (large file, may be slow)" if n_rows > MAX_ROWS_WARN else ""
        self.status_var.set(
            f"{os.path.basename(filepath)}  |  {n_rows} rows x {len(header)} columns  "
            f"|  delimiter: {used_delim!r}  |  encoding: {used_enc}{warn}"
        )

    def reload(self):
        if self.filepath:
            delim = None if self.auto_var.get() else self._current_manual_delimiter()
            self.load(self.filepath, delimiter=delim)

    def _current_manual_delimiter(self):
        custom = self.custom_delim_var.get()
        if custom:
            return custom
        label = self.delim_var.get()
        for lbl, val in DELIMITER_PRESETS:
            if lbl == label:
                return val
        return ","

    def _set_delim_ui(self, delimiter):
        for lbl, val in DELIMITER_PRESETS:
            if val == delimiter:
                self.delim_var.set(lbl)
                self.custom_delim_var.set("")
                return
        # delimiter isn't one of the presets -> show it in the custom field
        self.custom_delim_var.set(delimiter)

    def _on_delimiter_change(self):
        self.auto_var.set(False)
        self.custom_delim_var.set("")
        if self.filepath:
            self.load(self.filepath, delimiter=self._current_manual_delimiter())

    def _apply_custom_delimiter(self):
        if not self.custom_delim_var.get():
            return
        self.auto_var.set(False)
        if self.filepath:
            self.load(self.filepath, delimiter=self.custom_delim_var.get())

    def _on_auto_toggle(self):
        if self.auto_var.get() and self.filepath:
            self.load(self.filepath, delimiter=None)

    # ---------- search (Ctrl+F) ----------
    def show_search(self):
        if not self._search_visible:
            self._search_frame.pack(side=tk.RIGHT, padx=(10, 0))
            self._search_visible = True
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        if self._search_var.get():
            self._run_search()

    def hide_search(self, event=None):
        if self._search_visible:
            self._search_frame.pack_forget()
            self._search_visible = False
        self.tree.focus_set()

    def _on_search_text_changed(self):
        # small delay so we don't redo the whole search on every fast keystroke
        if self._search_after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(200, self._run_search)

    def _run_search(self):
        self._search_after_id = None
        query = self._search_var.get()
        self._search_matches = self._compute_matches(query) if query else []
        self._search_index = -1
        if self._search_matches:
            self._search_step(1)  # jump to the first result (index 0)
        else:
            self._selected_cell = None
            self._hide_cell_highlight()
        self._update_search_status()

    def _compute_matches(self, query):
        query = query.lower()
        cols = [f"c{i}" for i in range(len(self.header))]
        matches = []
        for iid in self.tree.get_children(""):
            for cid in cols:
                if query in self.tree.set(iid, cid).lower():
                    matches.append((iid, cid))
        return matches

    def _search_step(self, direction):
        if not self._search_matches:
            self._update_search_status()
            return
        self._search_index = (self._search_index + direction) % len(self._search_matches)
        row_iid, col_id = self._search_matches[self._search_index]
        if self.tree.exists(row_iid):
            self.tree.see(row_iid)
            self._ensure_column_visible(row_iid, col_id)
            self._selected_cell = (row_iid, col_id)
            self._update_cell_highlight()
        self._update_search_status()

    def _ensure_column_visible(self, row_iid, col_id):
        """Scrolls horizontally if the found column is outside the visible area."""
        if self.tree.bbox(row_iid, col_id):
            return  # already visible
        cols = list(self.tree["displaycolumns"])
        if tuple(cols) == ("#all",):
            cols = list(self.tree["columns"])
        if col_id not in cols:
            return
        widths = [self.tree.column(c, "width") for c in cols]
        total_w = sum(widths)
        if total_w <= 0:
            return
        target_idx = cols.index(col_id)
        acc = sum(widths[:target_idx])
        self.tree.xview_moveto(acc / total_w)

    def _update_search_status(self):
        if not self._search_var.get():
            self._search_status_var.set("")
        elif not self._search_matches:
            self._search_status_var.set("0 results")
        else:
            self._search_status_var.set(f"{self._search_index + 1}/{len(self._search_matches)}")

    # ---------- tree population ----------
    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        cols = [f"c{i}" for i in range(len(self.header))]
        self.tree["columns"] = cols
        self.tree["displaycolumns"] = cols
        self.sort_state = {}
        # old iids stop existing after reloading -> clear the selection
        self._selected_cell = None
        self._hide_cell_highlight()
        self._link_col_idxs = self._detect_link_columns()
        self._hide_link_labels()
        self._cancel_pending_sort()
        self._stop_pan()
        self._search_matches = []
        self._search_index = -1
        self._update_search_status()

        for cid, name in zip(cols, self.header):
            self.tree.heading(cid, text=name)
            self.tree.column(cid, width=120, minwidth=MIN_COLUMN_WIDTH, anchor="w", stretch=False)

        for row in self.rows:
            self.tree.insert("", tk.END, values=row)

        self._restripe()
        if not self._sep_loop_started:
            self._sep_loop_started = True
            self._reposition_separators()  # start the repositioning loop

        if self._search_visible and self._search_var.get():
            self._run_search()  # redo the search against the freshly loaded data

    def refresh_theme(self):
        """Called by the App when light/dark mode changes, to update whatever
        doesn't self-correct on the next tick of the repositioning loop."""
        self._refresh_row_tags()

    def _refresh_row_tags(self):
        """Reapplies the zebra striping colors from the current palette (light/dark)."""
        palette = self.get_palette()
        self.tree.tag_configure("evenrow", background=palette["stripe_even"])
        self.tree.tag_configure("oddrow", background=palette["stripe_odd"])

    def _restripe(self):
        """Reapplies the alternating row colors based on the current order."""
        for i, iid in enumerate(self.tree.get_children("")):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.tree.item(iid, tags=(tag,))

    def _detect_link_columns(self):
        """Samples the rows to find out which columns have URL-like values."""
        if not self.header:
            return set()
        found = set()
        for row in self.rows[:LINK_DETECT_SAMPLE_LIMIT]:
            for i, val in enumerate(row):
                if i not in found and looks_like_url(val):
                    found.add(i)
            if len(found) == len(self.header):
                break
        return found

    def _hide_link_labels(self):
        for lbl in self._link_labels:
            lbl.place_forget()

    def _update_link_overlays(self, cols, visible_item):
        """Overlays blue/underlined labels exactly on top of the link cells
        that are currently visible on screen (keeps the cost low even for large files)."""
        if not self._link_col_idxs or visible_item is None:
            self._hide_link_labels()
            return

        link_cols = [c for c in cols if int(c[1:]) in self._link_col_idxs]
        if not link_cols:
            self._hide_link_labels()
            return

        palette = self.get_palette()
        font_desc = ttk.Style(self).lookup("Treeview", "font") or "TkDefaultFont"
        base_font = tkfont.Font(font=font_desc)
        link_font = (base_font.actual("family"), base_font.actual("size"), "underline")

        tree_h = self.tree.winfo_height()
        cells = []  # (bbox, value, bg_color)
        iid = visible_item
        seen = 0
        while iid and seen < 500:
            row_bbox = self.tree.bbox(iid, cols[0])
            if not row_bbox:
                break
            if row_bbox[1] > tree_h:
                break
            tags = self.tree.item(iid, "tags")
            bg = palette["stripe_odd"] if "oddrow" in tags else palette["stripe_even"]
            for cid in link_cols:
                value = self.tree.set(iid, cid)
                if looks_like_url(value):
                    bbox = self.tree.bbox(iid, cid)
                    if bbox:
                        cells.append((bbox, value, bg))
            iid = self.tree.next(iid)
            seen += 1

        while len(self._link_labels) < len(cells):
            lbl = tk.Label(self.tree, cursor="hand2", anchor="w", padx=2)
            lbl.bind("<Control-Button-1>", self._on_link_label_click)
            lbl.bind("<ButtonPress-1>", self._on_link_label_select)
            self._link_labels.append(lbl)

        for lbl, (bbox, value, bg) in zip(self._link_labels, cells):
            x, y, w, h = bbox
            lbl.configure(text=value, bg=bg, fg=palette["link_fg"], font=link_font)
            lbl._link_value = value
            lbl.place(x=x, y=y, width=w, height=h)
        for extra in self._link_labels[len(cells):]:
            extra.place_forget()

    def _on_link_label_click(self, event):
        value = getattr(event.widget, "_link_value", "")
        if value:
            open_link(value)
            self._flash_status(f"Opening link: {value[:60]}")

    def _on_link_label_select(self, event):
        # a plain click (without ctrl) on the link label should still select
        # the cell underneath, just like clicking any other cell in the table
        x = self.tree.winfo_pointerx() - self.tree.winfo_rootx()
        y = self.tree.winfo_pointery() - self.tree.winfo_rooty()
        self._select_cell(x, y)

    def _reposition_separators(self):
        """Redraws the thin lines between columns and the selected-cell highlight;
        runs in a loop for as long as the tab exists (so it tracks scroll/resize/zoom)."""
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return

        self._update_cell_highlight()

        if not self.winfo_ismapped():
            # tab not visible right now: reschedule less often to save work
            with contextlib.suppress(tk.TclError):
                self.after(400, self._reposition_separators)
            return

        cols = list(self.tree["displaycolumns"])
        if tuple(cols) == ("#all",):
            cols = list(self.tree["columns"])

        boundaries = []
        children = self.tree.get_children("")
        visible_item = None
        if children and cols:
            # find the first currently visible row (scrolling may have hidden the ones above)
            for iid in children[:200]:
                if self.tree.bbox(iid, cols[0]):
                    visible_item = iid
                    break
            if visible_item is not None and len(cols) > 1:
                for cid in cols[:-1]:
                    bbox = self.tree.bbox(visible_item, cid)
                    if bbox:
                        x, _y, w, _h = bbox
                        boundaries.append(x + w)

        self._update_link_overlays(cols, visible_item)

        sep_color = self.get_palette()["separator"]
        total_h = self.tree.winfo_height()
        while len(self._sep_frames) < len(boundaries):
            self._sep_frames.append(tk.Frame(self.tree, bg=sep_color, width=1))
        for i, bx in enumerate(boundaries):
            self._sep_frames[i].configure(bg=sep_color)
            self._sep_frames[i].place(x=bx, y=0, width=1, height=total_h)
        for extra in self._sep_frames[len(boundaries):]:
            extra.place_forget()

        with contextlib.suppress(tk.TclError):
            self.after(150, self._reposition_separators)

    # ---------- sorting ----------
    def _sort_by(self, col_id):
        ascending = self.sort_state.get(col_id, True)
        items = [(self.tree.set(iid, col_id), iid) for iid in self.tree.get_children("")]

        def sort_key(pair):
            value = pair[0]
            try:
                return (0, float(value))
            except ValueError:
                return (1, value.lower())

        items.sort(key=sort_key, reverse=not ascending)
        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)
        self._restripe()

        self.sort_state[col_id] = not ascending
        # update the header text with a direction indicator
        idx = int(col_id[1:])
        base_name = self.header[idx]
        arrow = " ▲" if ascending else " ▼"
        for cid in self.tree["columns"]:
            i = int(cid[1:])
            self.tree.heading(cid, text=self.header[i])
        self.tree.heading(col_id, text=base_name + arrow)

    # ---------- reorder columns (drag on the header) ----------
    def _on_heading_press(self, event):
        if self._pan_active:
            self._stop_pan()
            return
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            self._drag_col = self.tree.identify_column(event.x)
            self._drag_start_x = event.x
        else:
            self._drag_col = None
        if region == "cell":
            self._select_cell(event.x, event.y)

    def _on_heading_drag(self, event):
        pass  # optional visual feedback; kept simple

    def _on_heading_release(self, event):
        if self._drag_col is None:
            return
        moved = abs(event.x - self._drag_start_x) > 15
        region = self.tree.identify_region(event.x, event.y)
        if moved and region == "heading":
            target_col = self.tree.identify_column(event.x)
            if target_col and target_col != self._drag_col:
                self._reorder_columns(self._drag_col, target_col)
        elif not moved and region == "heading":
            # plain click on the header -> sorts, but only after a small delay.
            # if it turns into a double-click (e.g. trying to hit the border to resize),
            # the double-click cancels this before it fires (see _on_heading_double_click)
            self._schedule_sort(self._drag_col)
        self._drag_col = None
        self._drag_start_x = None

    def _schedule_sort(self, col_id):
        self._cancel_pending_sort()
        self._pending_sort_after_id = self.after(SORT_CLICK_DELAY_MS, lambda: self._commit_sort(col_id))

    def _cancel_pending_sort(self):
        if self._pending_sort_after_id is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(self._pending_sort_after_id)
            self._pending_sort_after_id = None

    def _commit_sort(self, col_id):
        self._pending_sort_after_id = None
        self._sort_by(col_id)

    def _on_heading_double_click(self, event):
        # any double-click on the header cancels a pending sort from the
        # first click -- this is what avoids the bug of sorting together with the resize
        self._cancel_pending_sort()
        if event.y > self._header_height():
            return  # double-click in the table body, not the header
        col_id = self._column_at_border(event.x)
        if col_id:
            self._autosize_column(col_id)

    def _header_height(self):
        """Header height in pixels (where the first data row starts)."""
        children = self.tree.get_children("")
        if children:
            bbox = self.tree.bbox(children[0])
            if bbox:
                return bbox[1]
        return 26  # no rows yet -- reasonable estimate

    def _column_at_border(self, x, tolerance=4):
        """Finds the column whose right border is near x (uses bbox, so it
        already accounts for the current horizontal scroll -- including past the last column)."""
        cols = list(self.tree["displaycolumns"])
        if tuple(cols) == ("#all",):
            cols = list(self.tree["columns"])
        children = self.tree.get_children("")
        if not cols or not children:
            return None

        visible_item = None
        for iid in children[:200]:
            if self.tree.bbox(iid, cols[0]):
                visible_item = iid
                break
        if visible_item is None:
            return None

        for cid in cols:
            bbox = self.tree.bbox(visible_item, cid)
            if not bbox:
                continue
            cx, _cy, cw, _ch = bbox
            if abs(x - (cx + cw)) <= tolerance:
                return cid
        return None

    def _autosize_column(self, col_id):
        """Resizes the column to fit its widest content (like double-clicking in Sheets/Excel).
        Measures with the real header/body font (bold, current zoom, etc.),
        not a fixed default font -- otherwise the header might not fit properly."""
        try:
            idx = int(col_id[1:])
        except ValueError:
            return
        if idx >= len(self.header):
            return

        style = ttk.Style(self)
        body_font = tkfont.Font(font=style.lookup("Treeview", "font") or "TkDefaultFont")
        heading_font = tkfont.Font(font=style.lookup("Treeview.Heading", "font") or "TkDefaultFont")

        max_width = heading_font.measure(str(self.header[idx]))
        sample = self.rows[:AUTOSIZE_SAMPLE_LIMIT]
        for row in sample:
            w = body_font.measure(str(row[idx]))
            if w > max_width:
                max_width = w

        self.tree.column(col_id, width=max_width + 24)  # a bit of breathing room

    def _reorder_columns(self, src_col, target_col):
        cols = list(self.tree["displaycolumns"])
        if cols == ["#all"]:
            cols = list(self.tree["columns"])
        src_i = cols.index(src_col)
        tgt_i = cols.index(target_col)
        cols.pop(src_i)
        cols.insert(tgt_i, src_col)
        self.tree["displaycolumns"] = cols


_AppBase = TkinterDnD.Tk if HAS_DND else tk.Tk


class CSVViewerApp(_AppBase):
    def __init__(self, initial_files=None):
        super().__init__()
        self.title("CSV Viewer" + ("" if HAS_DND else "  (drag-and-drop unavailable: pip install tkinterdnd2)"))
        self.geometry("1000x600")
        self._set_window_icon()

        self._config = load_config()
        self._init_zoom()
        self._init_theme_state()
        self._init_recent_files()
        self._build_menu()
        self._apply_theme_style()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        # middle-click on a tab closes it, just like a browser
        self.notebook.bind("<Button-2>", self._on_notebook_middle_click)

        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_root_drop)

        self.bind_all("<Control-o>", lambda e: self.open_file_dialog())
        self.bind_all("<Control-w>", lambda e: self.close_current_tab())
        self.bind_all("<Control-f>", lambda e: self._dispatch_to_current_tab("show_search"))
        # zoom: Ctrl+/- (with or without shift/numpad)
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            self.bind_all(seq, lambda e: self.change_zoom(ZOOM_STEP))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind_all(seq, lambda e: self.change_zoom(-ZOOM_STEP))
        # recent files: Ctrl+1..9 open the 1st-9th, Ctrl+0 opens the 10th
        # (Ctrl+0 no longer resets the zoom -- you can still do that via the button/menu)
        for i in range(1, 10):
            self.bind_all(f"<Control-Key-{i}>", lambda e, idx=i - 1: self._open_recent(idx))
        self.bind_all("<Control-Key-0>", lambda e: self._open_recent(9))

        for f in (initial_files or []):
            self.open_file(f)

        if not self.notebook.tabs():
            self._show_empty_hint()

    def _set_window_icon(self):
        """Uses the bundled .ico when available (Windows); silently keeps the
        default Tk icon elsewhere or if the file is missing."""
        icon = resource_path("assets", "icon.ico")
        if os.path.isfile(icon):
            with contextlib.suppress(tk.TclError):
                self.iconbitmap(icon)

    # ---------- zoom (affects font/row height for all tabs) ----------
    def _init_zoom(self):
        self.style = ttk.Style(self)
        default_font = tkfont.nametofont("TkDefaultFont")
        self._zoom_font_family = default_font.actual("family")
        self._zoom_base_size = default_font.actual("size") or 9

        saved_zoom = self._config.get("zoom_pct", ZOOM_DEFAULT)
        try:
            saved_zoom = int(saved_zoom)
        except (TypeError, ValueError):
            saved_zoom = ZOOM_DEFAULT
        self.zoom_pct = max(ZOOM_MIN, min(ZOOM_MAX, saved_zoom))

        self.zoom_label_var = tk.StringVar(value=f"{self.zoom_pct}%")
        self._apply_zoom_style()

    def change_zoom(self, delta):
        self.apply_zoom(self.zoom_pct + delta)

    def reset_zoom(self):
        self.apply_zoom(ZOOM_DEFAULT)

    def apply_zoom(self, pct):
        self.zoom_pct = max(ZOOM_MIN, min(ZOOM_MAX, pct))
        self.zoom_label_var.set(f"{self.zoom_pct}%")
        self._apply_zoom_style()
        self._config["zoom_pct"] = self.zoom_pct
        save_config(self._config)

    def _apply_zoom_style(self):
        scale = self.zoom_pct / 100
        size = max(6, round(self._zoom_base_size * scale))
        row_h = max(14, round(BASE_ROW_HEIGHT * scale))
        self.style.configure("Treeview", font=(self._zoom_font_family, size), rowheight=row_h)
        self.style.configure("Treeview.Heading", font=(self._zoom_font_family, size, "bold"))

    # ---------- light/dark theme ----------
    def _init_theme_state(self):
        self._native_theme = self.style.theme_use()  # so we can switch back to light (native)
        self.dark_mode = bool(self._config.get("dark_mode", False))
        self.dark_mode_var = tk.BooleanVar(value=self.dark_mode)

    def get_palette(self):
        return PALETTES["dark" if self.dark_mode else "light"]

    def toggle_theme(self):
        self.dark_mode = self.dark_mode_var.get()
        self._apply_theme_style()
        self._config["dark_mode"] = self.dark_mode
        save_config(self._config)
        for tab_id in self.notebook.tabs():
            tab = self.nametowidget(tab_id)
            if isinstance(tab, CSVTab):
                tab.refresh_theme()

    def _apply_theme_style(self):
        if self.dark_mode:
            p = PALETTES["dark"]
            self.style.theme_use("clam")
            self.style.configure(".", background=p["app_bg"], foreground=p["fg"])
            self.style.configure("TFrame", background=p["app_bg"])
            self.style.configure("TLabel", background=p["app_bg"], foreground=p["fg"])
            self.style.configure("TButton", background=p["heading_bg"], foreground=p["fg"])
            self.style.configure("TCheckbutton", background=p["app_bg"], foreground=p["fg"])
            self.style.configure("TCombobox", fieldbackground=p["entry_bg"],
                                 background=p["heading_bg"], foreground=p["fg"])
            self.style.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["fg"])
            self.style.configure("TNotebook", background=p["app_bg"])
            self.style.configure("TNotebook.Tab", background=p["heading_bg"], foreground=p["fg"])
            self.style.map("TNotebook.Tab", background=[("selected", p["select_bg"])],
                            foreground=[("selected", p["select_fg"])])
            self.style.configure("Treeview", background=p["tree_bg"], fieldbackground=p["tree_bg"],
                                  foreground=p["tree_fg"])
            self.style.map("Treeview", background=[("selected", p["select_bg"])],
                            foreground=[("selected", p["select_fg"])])
            self.style.configure("Treeview.Heading", background=p["heading_bg"], foreground=p["heading_fg"])
            self.style.configure("TScrollbar", background=p["heading_bg"], troughcolor=p["app_bg"])
            self.configure(bg=p["app_bg"])
            menu_colors = {
                "bg": p["menu_bg"], "fg": p["menu_fg"],
                "activebackground": p["menu_active_bg"], "activeforeground": p["menu_active_fg"],
            }
        else:
            self.style.theme_use(self._native_theme)
            self.configure(bg="SystemButtonFace")
            menu_colors = {
                "bg": "SystemMenu", "fg": "SystemMenuText",
                "activebackground": "SystemHighlight", "activeforeground": "SystemHighlightText",
            }

        self._menu_colors = menu_colors
        for menu in (self._menubar, self._file_menu, self._view_menu, getattr(self, "_recent_menu", None)):
            if menu is None:
                continue
            with contextlib.suppress(tk.TclError):
                menu.configure(**menu_colors)
        # zoom affects the Treeview's font/height -- reapply it on top of the theme that just changed
        self._apply_zoom_style()

    # ---------- recent files (Ctrl+1..9, Ctrl+0) ----------
    def _init_recent_files(self):
        raw = self._config.get("recent_files", [])
        if not isinstance(raw, list):
            raw = []
        self.recent_files = [p for p in raw if isinstance(p, str)][:10]

    def _add_recent(self, path):
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]
        self._config["recent_files"] = self.recent_files
        save_config(self._config)
        self._rebuild_recent_menu()

    def _open_recent(self, index):
        if index < 0 or index >= len(self.recent_files):
            return
        path = self.recent_files[index]
        if not os.path.isfile(path):
            messagebox.showerror("File not found", path)
            self.recent_files.remove(path)
            self._config["recent_files"] = self.recent_files
            save_config(self._config)
            self._rebuild_recent_menu()
            return
        self.open_file(path)

    def _rebuild_recent_menu(self):
        self._recent_menu.delete(0, tk.END)
        if not self.recent_files:
            self._recent_menu.add_command(label="(empty)", state="disabled")
        else:
            for i, path in enumerate(self.recent_files):
                shortcut = f"Ctrl+{i + 1}" if i < 9 else "Ctrl+0"
                label = f"{i + 1}. {os.path.basename(path)}"
                self._recent_menu.add_command(
                    label=label, accelerator=shortcut, command=lambda p=path: self.open_file(p)
                )
        menu_colors = getattr(self, "_menu_colors", None)
        if menu_colors:
            with contextlib.suppress(tk.TclError):
                self._recent_menu.configure(**menu_colors)

    def _on_root_drop(self, event):
        paths = self.tk.splitlist(event.data)
        self._open_dropped(paths)

    def _open_dropped(self, paths):
        skipped = []
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext in (".csv", ".tsv") and os.path.isfile(p):
                self.open_file(p)
            else:
                skipped.append(p)
        if skipped:
            messagebox.showwarning(
                "File ignored",
                "Only .csv/.tsv files are opened automatically. Ignored:\n"
                + "\n".join(skipped),
            )

    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open...", accelerator="Ctrl+O", command=self.open_file_dialog)
        self._recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open Recent", menu=self._recent_menu)
        file_menu.add_command(label="Close Tab", accelerator="Ctrl+W", command=self.close_current_tab)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)
        self._rebuild_recent_menu()

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", accelerator="Ctrl++", command=lambda: self.change_zoom(ZOOM_STEP))
        view_menu.add_command(label="Zoom Out", accelerator="Ctrl+-", command=lambda: self.change_zoom(-ZOOM_STEP))
        view_menu.add_command(label="Reset Zoom (100%)", command=self.reset_zoom)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="Dark Mode", variable=self.dark_mode_var, command=self.toggle_theme
        )
        menubar.add_cascade(label="View", menu=view_menu)

        self.config(menu=menubar)
        self._menubar = menubar
        self._file_menu = file_menu
        self._view_menu = view_menu

    def _show_empty_hint(self):
        hint = ttk.Label(
            self.notebook,
            text="File > Open (Ctrl+O) to load a CSV/TSV",
            anchor="center",
        )
        self.notebook.add(hint, text="(empty)")

    def open_file_dialog(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("CSV/TSV", "*.csv *.tsv"), ("All files", "*.*")]
        )
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        if not os.path.isfile(path):
            messagebox.showerror("File not found", path)
            return
        # remove the empty-hint tab, if it's the only one
        tabs = self.notebook.tabs()
        if len(tabs) == 1 and self.notebook.tab(tabs[0], "text") == "(empty)":
            self.notebook.forget(tabs[0])

        tab = CSVTab(
            self.notebook, filepath=path, on_drop_files=self._open_dropped,
            zoom_label_var=self.zoom_label_var,
            on_zoom_delta=self.change_zoom, on_zoom_reset=self.reset_zoom,
            get_palette=self.get_palette,
            dark_mode_var=self.dark_mode_var, on_theme_toggle=self.toggle_theme,
        )
        self.notebook.add(tab, text=os.path.basename(path))
        self.notebook.select(tab)
        self._add_recent(path)

    def _dispatch_to_current_tab(self, method_name):
        tab_id = self.notebook.select()
        if not tab_id:
            return
        tab = self.nametowidget(tab_id)
        if isinstance(tab, CSVTab):
            getattr(tab, method_name)()

    def close_current_tab(self):
        tabs = self.notebook.tabs()
        if not tabs:
            return
        current = self.notebook.select()
        if current:
            self.notebook.forget(current)
        if not self.notebook.tabs():
            self._show_empty_hint()

    def _on_notebook_middle_click(self, event):
        element = self.notebook.identify(event.x, event.y)
        if not element:
            return  # click outside the tab strip (e.g. in the content)
        try:
            idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        tabs = self.notebook.tabs()
        if idx is None or idx >= len(tabs):
            return
        tab_id = tabs[idx]
        if not isinstance(self.nametowidget(tab_id), CSVTab):
            return  # don't close the "(empty)" hint tab
        self.notebook.forget(tab_id)
        if not self.notebook.tabs():
            self._show_empty_hint()


if __name__ == "__main__":
    files = sys.argv[1:]
    app = CSVViewerApp(initial_files=files)
    app.mainloop()
