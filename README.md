# GetMusic

Console tool to download YouTube audio as MP3, with interactive search mode.

## Requirements

- **Python 3.10+**
- **ffmpeg** in system PATH (for MP3 conversion)
- Internet connection

## Setup

```powershell
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

### Batch download from URLs file

```powershell
.\venv\Scripts\python src\main.py
.\venv\Scripts\python src\main.py -o "C:\salida" -j 5 urls.txt
.\venv\Scripts\python src\main.py --skip-downloaded urls.txt
```

### Interactive mode — search and download directly

```powershell
.\venv\Scripts\python src\main.py --add
.\venv\Scripts\python src\main.py --add -j 5
```

Full terminal UI (Textual) with DataTable, mode selector buttons (Normal / Artista / Crudo), inline help bar, keyboard-driven navigation, and live progress bars.

| Key        | Action                                           |
| ---------- | ------------------------------------------------ |
| `Space`    | Toggle selection on current row                  |
| `a`        | Select / deselect all                            |
| `↓`        | Move focus from search input to results table   |
| `↑`        | Move focus back to search input (at first row)  |
| `→` / `←`  | Next / previous page (fetches more if needed)   |
| `Enter`    | Download selected songs                          |
| `Ctrl+Q`   | Quit                                             |
| `Tab`      | Focus next widget                                |

Inline help bar below input shows active shortcuts.

Mode selector before searching:

| Mode | Button    | Behavior                                                                                                     |
| ---- | --------- | ------------------------------------------------------------------------------------------------------------ |
| Normal | `Normal` | (default) Adds " audio" suffix to search, 5 results per page                                                 |
| Artist | `Artista` | No suffix, up to 50 results per page, downloads to `downloads/ArtistName/` subfolder                         |
| Raw  | `Crudo`   | Raw search (no suffix), 5 results per page                                                                   |

Playlists are auto-detected — paste any playlist URL directly in the input.

### Arguments

| Arg                 | Default     | Description                                                     |
| ------------------- | ----------- | --------------------------------------------------------------- |
| `archivo`           | `urls.txt`  | Text file with one YouTube URL per line                         |
| `-o, --output`      | `downloads` | Base output directory                                           |
| `-j, --jobs`        | `3`         | Number of concurrent downloads (used for batch and artist mode) |
| `--add`             | —           | Interactive mode with Textual TUI (DataTable, progress bars)  |
| `--skip-downloaded` | —           | Skip URLs already present in download history                   |

### Input file format

```
https://www.youtube.com/watch?v=VIDEO_ID
# Lines starting with # are ignored
https://youtu.be/OTHER_ID
```

## Features

- **Concurrent downloads** — parallel downloads with `-j` (default 3)
- **Progress bars** — one bar per download with speed and ETA, stays visible after completion
- **320 kbps MP3** — extracts best audio with ffmpeg
- **Metadata** — title, artist, album, etc. embedded via FFmpegMetadata
- **Smart filenames** — truncated to 100 chars, invalid characters sanitized
- **Textual TUI** — `--add` mode with full terminal UI: `Input`, `DataTable`, keyboard navigation, selection toggle, inline help bar
- **Pagination** — `→`/`←` to browse result pages (5 per page in normal mode, 50 in artist mode); fetches more results automatically when reaching the end
- **Artist mode** — `@ArtistName` shows up to 50 results per page, concurrent download to `downloads/ArtistName/`
- **Playlist mode** — paste a playlist URL (auto-detected or with `/` prefix), extract videos, checkbox selection, concurrent download
- **Fast search** — uses `extract_flat=True` for near-instant results (no view counts in table); fetches 100 results initially, paginates in 100-result increments (fewer re-fetches)
- **Download memory** — shows `⤵` next to already-downloaded songs in results, skip with `--skip-downloaded`
- **Live progress bars** — per-download `ProgressBar` widgets with speed, ETA, and status
- **Post-download summary** — shows completion count and "Nueva búsqueda" button without leaving the TUI
- **Encrypted store** — single file (`data/store.dat`) for search history + download log. Auto-generated `data/.key` (Fernet), `store.dat.bak` before each overwrite, schema validation with automatic fallback to `.bak` on corruption, max 500 entries per list.
- **No double extraction** — skips pre-extraction HTTP request when title is already known (TUI mode), reducing per-download overhead
- **Batch storage writes** — dirty-flag pattern: all writes deferred until flush (once per batch or on exit), not per-call
- **Keyboard interrupt** — Ctrl+C handled gracefully in both batch and interactive modes
- **Organized output** — saved to `{output}/{YYYY-MM-DD}/`; artist downloads to `{output}/ArtistName/`; `urls.txt` renamed on completion
- **Summary stats** — `✓ X/Y canciones en Zs` after each batch

## Project structure

```
src/
├── main.py           CLI entry point (argparse, batch download)
├── downloader.py     Download logic (yt-dlp wrapper, concurrent batches)
├── ui.py             Legacy interactive mode (prompt_toolkit, fallback)
├── tui_app.py        Textual TUI for `--add` mode (DataTable, progress bars)
├── storage.py        Encrypted persistence (single store in data/)
├── models.py         Data types (DownloadJob)
└── utils.py          Shared helpers (tqdm_write, sanitize_filename, URL detection)
data/
├── .key             Fernet encryption key (auto-generated on first run)
├── store.dat        Encrypted search & download history
└── store.dat.bak    Automatic backup before each store overwrite
```

## Dependencies

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — download engine
- [tqdm](https://github.com/tqdm/tqdm) — progress bars (batch mode)
- [textual](https://github.com/Textualize/textual) — terminal UI framework for `--add` mode
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — interactive input (legacy `ui.py`)
- [cryptography](https://github.com/pyca/cryptography) — encrypted search/download history
