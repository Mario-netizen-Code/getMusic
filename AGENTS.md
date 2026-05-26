# descargar_you2

Console tool to download YouTube audio as MP3 from a text file listing URLs.

## Commands

```powershell
# Run
.\venv\Scripts\python src\main.py
.\venv\Scripts\python src\main.py -o "C:\path\to\output" urls.txt

# Interactive mode — busca canciones y descarga directamente
.\venv\Scripts\python src\main.py --add

# Interactive mode with concurrency (default: 3 jobs)
.\venv\Scripts\python src\main.py --add -j 5

# Batch mode: skip already-downloaded URLs
.\venv\Scripts\python src\main.py --skip-downloaded urls.txt

# Install deps (after cloning / new venv)
.\venv\Scripts\python -m pip install -r requirements.txt
```

## Key facts
- **Requires ffmpeg** on system PATH for MP3 conversion (already installed on this machine at a system location).
- **Virtual env** at `venv/`. Never committed (in `.gitignore`). Create with `python -m venv venv` if missing.
- **Entrypoint**: `src/main.py` (no package/module wrapper, called directly).
- **Input format**: `urls.txt` — one URL per line, `#` for comments, lines stripped.
- **Dependencies**: `yt-dlp`, `tqdm`, `textual`, `prompt_toolkit`, `cryptography`. Install via `requirements.txt`.
- **`--add` mode**: full terminal UI (Textual) with DataTable, keyboard navigation (Space=toggle, a=all/none, →/←=pages with auto-fetch, Enter=download), inline help bar, live progress bars, post-download summary with "Nueva búsqueda" button. Search uses `extract_flat=True` for speed (no view counts).
- **`--add` prefixes**: `@` = artist mode (50 results/page, download to artist subfolder); `!` = raw search (no " audio" suffix); `/` o URL de playlist = descarga playlist con checkbox.
- **Concurrent downloads** via `-j`/`--jobs` (default: 3), per-download ProgressBar widgets with speed/ETA.
- **`extract_flat=True`** in search for near-instant results; no view counts in table.
- **Cursor preserved** when toggling selection (table clears and rebuilds but cursor stays on same row).
- **Output**: `downloads/` directory by default, created if missing.
- **Quality**: extracts best audio → MP3 at **320 kbps** (`preferredquality: "0"` = best, `-ab 320k`).
- **Metadata**: embeds title/artist/album etc. via `FFmpegMetadata` postprocessor.
- **Filename**: truncated to 100 chars max stem, invalid chars sanitized.
- **Module structure** (`src/`): `main.py` (CLI entry), `downloader.py` (yt-dlp wrapper, batches), `ui.py` (interactive mode), `tui_app.py` (Textual TUI for `--add`), `storage.py` (encrypted persistence), `models.py` (data types), `utils.py` (shared helpers).
- **Encrypted store**: single file `data/store.dat` (auto-generated) for search history + download log. `data/` is in `.gitignore`.
- **No tests, linters, or typecheckers** configured. No CI.
- **Fresh repo** — zero commits.
- `.opencode/` directory is OpenCode internal tooling; not part of project code.
