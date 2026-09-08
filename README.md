# CSV Viewer

[![Tests](https://github.com/thalescd/csv-viewer/actions/workflows/tests.yml/badge.svg)](https://github.com/thalescd/csv-viewer/actions/workflows/tests.yml)

A lightweight, dependency-free CSV/TSV viewer built with Python's Tkinter.

No pandas, no Electron, no browser engine -- just the standard library, a
single script, and a UI that stays fast and simple even on very large files.

## Features

- **Tabs** -- open multiple files at once, one per tab (Notepad++ style).
- **Sort by column** -- click a header to sort, click again to reverse.
- **Reorder columns** -- drag a header left/right.
- **Resize columns** -- drag the border between headers, or double-click it
  to auto-fit the column to its widest content.
- **Switch delimiter on the fly** -- presets (`,` `;` Tab `|`) or a custom
  one, with auto-detection by default.
- **Zebra striping** and **thin column separators** for readability.
- **Copy a cell** -- click to select, `Ctrl+C` to copy, or right-click →
  *Copy cell*.
- **Clickable links** -- cells that look like a URL are underlined; hold
  `Ctrl` and click to open in the browser.
- **Find (`Ctrl+F`)** -- search across the whole table, `Enter`/`↓` for the
  next match, `Shift+Enter`/`↑` for the previous one.
- **Zoom (50%-200%)** -- buttons in the status bar, `Ctrl +`/`Ctrl -`/
  `Ctrl 0`, or `Ctrl+scroll`. Persisted across restarts.
- **Dark mode** -- toggle in the status bar or the View menu. Persisted
  across restarts.
- **Recent files** -- up to 10, listed under *File > Open Recent*, with
  `Ctrl+1`...`Ctrl+9`, `Ctrl+0` shortcuts.
- **Pan mode** -- hold the middle mouse button and move the pointer to
  scroll in that direction, browser/PDF-reader style.
- **Auto-hiding scrollbars** -- only shown when there's actually something
  to scroll.
- **Drag and drop** files onto the window to open them in a new tab
  (requires the optional `tkinterdnd2` dependency).
- **Middle-click a tab** to close it, browser style.

## Requirements

- Python 3.8+ (stdlib only -- no dependencies required to run the app).
- Optional: [`tkinterdnd2`](https://pypi.org/project/tkinterdnd2/) for
  drag-and-drop support. Without it, everything else still works normally.

```bash
pip install -r requirements.txt
```

## Usage

```bash
python viewer.py                     # opens empty
python viewer.py data.csv            # opens one file
python viewer.py a.csv b.tsv         # opens several, one tab each
```

Settings (zoom, dark mode, recent files) are stored in
`%APPDATA%\CSVViewer\config.json` on Windows (or `~/CSVViewer/config.json`
elsewhere).

## Building a standalone executable (Windows)

Produces a `CSVViewer.exe` that runs without Python installed:

```bash
pip install -r requirements-dev.txt
pyinstaller csv-viewer.spec
```

The result lands in `dist/CSVViewer/`. The spec bundles the app icon and the
Tcl/Tk extension that `tkinterdnd2` needs for drag-and-drop (PyInstaller does
not pick that one up on its own).

This is a **one-folder** build on purpose. A `--onefile` build produces a
single tidy `.exe`, but it unpacks itself into a temp folder on every launch:

| Build | Startup | Size on disk |
|---|---|---|
| one-folder (this spec) | ~0.2 s | 22 MB (folder) |
| `--onefile` | ~1.0 s | 9 MB (single file) |

For a program whose whole job is to open instantly when you double-click a
CSV, the 5x faster start is worth more than the tidier folder.

### Associate `.csv`/`.tsv` with the viewer (Windows)

With a built `.exe`, right-click any `.csv` → **Open with** → **Choose another
app** → **Browse** to `dist\CSVViewer\CSVViewer.exe`, and tick *Always use
this app*. No administrator rights needed.

To run it from source instead (no `.exe`), you have to register the
association by hand, from an **elevated** command prompt:

```cmd
assoc .csv=CSVViewer.File
assoc .tsv=CSVViewer.File
ftype CSVViewer.File="C:\Path\To\pythonw.exe" "C:\Path\To\viewer.py" "%1"
```

Using `pythonw.exe` (instead of `python.exe`) avoids a console window popping
up alongside the app.

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file |
| `Ctrl+W` | Close current tab |
| `Ctrl+F` | Find in current tab |
| `Ctrl+C` | Copy selected cell |
| `Ctrl+click` (cell) | Open link |
| `Ctrl +` / `Ctrl -` / `Ctrl 0` | Zoom in / out / reset |
| `Ctrl+scroll` | Zoom in / out |
| `Ctrl+1`...`Ctrl+9`, `Ctrl+0` | Open 1st-10th recent file |
| Hold middle mouse button | Pan mode |
| Middle-click a tab | Close that tab |
| Double-click a column border | Auto-fit column width |

## Project layout

```
viewer.py             # the whole app (single file, no packages)
csv-viewer.spec       # PyInstaller build recipe
assets/               # app icon (+ the script that generates it)
ruff.toml             # lint configuration
requirements.txt      # optional runtime dependency (tkinterdnd2)
requirements-dev.txt  # dev dependencies (pytest, ruff)
examples/sample.csv   # a small file to try the viewer with
tests/                # unit tests for the non-UI logic
```

## Development

The parsing/config/link-detection logic (everything outside the Tkinter
classes) is covered by unit tests -- they don't open any window, so they run
fine in a headless CI environment.

```bash
pip install -r requirements-dev.txt
pytest -v        # run the tests
ruff check .     # lint (config in ruff.toml)
ruff check . --fix
```

Linting and tests run automatically on every push via GitHub Actions
(`.github/workflows/tests.yml`).

## License

[MIT](LICENSE) -- do whatever you want with it, just keep the copyright notice.

## Design notes

Tkinter's `ttk.Treeview` doesn't natively support things like per-cell text
color, column separator lines, or auto-hiding scrollbars -- those are
implemented by overlaying small widgets (thin `Frame`s / `Label`s) on top
of the tree, repositioned on a lightweight periodic loop so they track
scrolling, resizing and zoom. This keeps the app dependency-free while still
looking closer to a spreadsheet than a bare native listview.
