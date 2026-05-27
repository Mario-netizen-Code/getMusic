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

```powershell
.\venv\Scripts\python src\main.py
.\venv\Scripts\python src\main.py -o "C:\salida"
.\venv\Scripts\python src\main.py -j 5
```

Full terminal UI (Textual) with DataTable, mode selector buttons (Normal / Artista / Sin filtro), inline help bar, full keyboard navigation (↑/↓ entre secciones), and live progress bar.

| Key        | Action                                           |
| ---------- | ------------------------------------------------ |
| `Space`    | Toggle selection on current row                  |
| `a`        | Select / deselect all                            |
| `↓`        | Move focus from search input → results → action bar |
| `↑`        | Move focus back (action bar → results → search)     |
| `→` / `←`  | Next / previous page (fetches more if needed)   |
| `Enter`    | Download selected songs                          |
| `Ctrl+Q`   | Quit                                             |
| `Tab`      | Focus next widget                                |

Inline help bar below input shows active shortcuts.

Mode selector before searching:

| Mode | Button       | Behavior                                                                                                     |
| ---- | ------------ | ------------------------------------------------------------------------------------------------------------ |
| Normal | `Normal`    | (default) Adds " audio" suffix to search                                                                     |
| Artist | `Artista`   | Adds " topic" suffix to prefer official auto-generated Topic channels                                        |
| Raw  | `Sin filtro` | Raw search, no suffix                                                                                        |

Playlists are auto-detected — paste any playlist URL directly in the input.

### Arguments

| Arg                 | Default     | Description                                                     |
| ------------------- | ----------- | --------------------------------------------------------------- |
| `-o, --output`      | `downloads` | Base output directory                                           |
| `-j, --jobs`        | `3`         | Number of concurrent downloads                                  |

### Import URLs from file (inside the TUI)

Click the **Importar** button to pick from `.txt` files in the current directory (one URL per line):

```
https://www.youtube.com/watch?v=VIDEO_ID
# Lines starting with # are ignored
https://youtu.be/OTHER_ID
```

The app will validate URLs, extract titles, and display them in the table for selection and download.

## Features

- **Concurrent downloads** — parallel downloads with `-j` (default 3)
- **Progress** — single overall ProgressBar with current filename + compact done-list
- **320 kbps MP3** — extracts best audio with ffmpeg
- **Metadata** — title, artist, album, etc. embedded via FFmpegMetadata
- **Smart filenames** — truncated to 100 chars, invalid characters sanitized
- **Textual TUI** — full terminal UI: `Input`, `DataTable`, keyboard navigation, selection toggle, inline help bar
- **Pagination** — `→`/`←` to browse result pages (30 per page); fetches more results automatically when reaching the end
- **Artist mode** — `Artista` button adds " topic" suffix to prefer official YouTube Topic channels
- **Playlist mode** — paste a playlist URL (auto-detected or with `/` prefix), extract videos, checkbox selection, concurrent download
- **Fast search** — uses `extract_flat=True` for near-instant results; fetches 100 results initially, paginates in 100-result increments (fewer re-fetches)
- **Smart dedup** — normaliza títulos (saca "(Official Video)", "(Lyrics)", etc.), agrupa por título + duración (±4s), conserva el de más visitas y baja covers/remixes al final
- **Import URLs from file** — import `.txt` file with YouTube URLs via the **Importar** button; validates URLs, extracts titles, and shows in table for selection/download
- **Downloaded indicator** — `⤵` en la columna Estado indica canciones ya descargadas (historial persistente); selección (`✓`) y estado descargado son columnas independientes
- **Import auto-select** — al importar, canciones ya descargadas no se seleccionan automáticamente
- **Full ↑/↓ navigation** — flechas navegan entre Input de búsqueda, tabla de resultados, y botones de acción
- **Post-download summary** — shows completion count and "Nueva búsqueda" button without leaving the TUI
- **Encrypted store** — single file (`data/store.dat`) for search history + download log. Auto-generated `data/.key` (Fernet), `store.dat.bak` before each overwrite, schema validation with automatic fallback to `.bak` on corruption, max 500 entries per list.
- **No double extraction** — skips pre-extraction HTTP request when title is already known (TUI mode), reducing per-download overhead
- **Batch storage writes** — dirty-flag pattern: all writes deferred until flush (once per batch or on exit), not per-call
- **Keyboard interrupt** — Ctrl+C handled gracefully during downloads
- **Organized output** — saved to `{output}/{YYYY-MM-DD}/`

## Project structure

```
src/
├── main.py           CLI entry point (argparse, launches TUI)
├── downloader.py     Download logic (yt-dlp wrapper, concurrent batches)
├── ui.py             Legacy interactive mode (prompt_toolkit, fallback)
├── tui_app.py        Textual TUI (DataTable, search, import, progress bars)
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
- [tqdm](https://github.com/tqdm/tqdm) — progress bars
- [textual](https://github.com/Textualize/textual) — terminal UI framework
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) — interactive input (legacy `ui.py`)
- [cryptography](https://github.com/pyca/cryptography) — encrypted search/download history
