# descargar_you2

Console tool to download YouTube audio as MP3 from a text file listing URLs.

## Commands

```powershell
# Run
.\venv\Scripts\python main.py
.\venv\Scripts\python main.py -o "C:\path\to\output" urls.txt

# Interactive mode — busca canciones y descarga directamente
.\venv\Scripts\python main.py --add

# Interactive mode with concurrency (default: 3 jobs)
.\venv\Scripts\python main.py --add -j 5

# Batch mode: skip already-downloaded URLs
.\venv\Scripts\python main.py --skip-downloaded urls.txt

# Install deps (after cloning / new venv)
.\venv\Scripts\python -m pip install -r requirements.txt
```

## Key facts
- **Requires ffmpeg** on system PATH for MP3 conversion (already installed on this machine at a system location).
- **Virtual env** at `venv/`. Never committed (in `.gitignore`). Create with `python -m venv venv` if missing.
- **Entrypoint**: `main.py` (no package/module wrapper, called directly).
- **Input format**: `urls.txt` — one URL per line, `#` for comments, lines stripped.
- **Dependencies**: `yt-dlp`, `tqdm`, `prompt_toolkit`, `cryptography`. Install via `requirements.txt`.
- **`--add` prefixes**: `!` = raw search (no " audio" suffix); `@` = artist mode (checkbox multi-select, concurrent download to artist subfolder); `/` o URL de playlist = descarga playlist con checkbox.
- **Playlist mode**: pegar URL de playlist en `--add`, o anteponer `/` a la URL. Extrae videos con checkbox (todo seleccionado por defecto) y descarga concurrente.
- **Artist mode** (`@` prefix): checkbox selection, browse pages with `→`/`←`, concurrent downloads with `-j`.
- **Concurrent downloads** in artist mode via `-j`/`--jobs` (default: 3).
- **Output**: `downloads/` directory by default, created if missing.
- **Quality**: extracts best audio → MP3 at **320 kbps** (`preferredquality: "0"` = best, `-ab 320k`).
- **Metadata**: embeds title/artist/album etc. via `FFmpegMetadata` postprocessor.
- **Filename**: truncated to 100 chars max stem, invalid chars sanitized.
- **No tests, linters, or typecheckers** configured. No CI.
- **Fresh repo** — zero commits.
- `.opencode/` directory is OpenCode internal tooling; not part of project code.
