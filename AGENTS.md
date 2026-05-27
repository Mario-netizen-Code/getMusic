# descargar_you2

Console tool to download YouTube audio as MP3 from a text file listing URLs.

## Commands

```powershell
# Run (TUI — default)
.\venv\Scripts\python src\main.py

# With options
.\venv\Scripts\python src\main.py -o "C:\path\to\output" -j 5

# Install deps (after cloning / new venv)
.\venv\Scripts\python -m pip install -r requirements.txt
```

## Key facts
- **Requires ffmpeg** on system PATH for MP3 conversion (already installed on this machine at a system location).
- **Virtual env** at `venv/`. Never committed (in `.gitignore`). Create with `python -m venv venv` if missing.
- **Entrypoint**: `src/main.py` (no package/module wrapper, called directly). No batch mode — always launches TUI.
- **Dependencies**: `yt-dlp`, `tqdm`, `textual`, `prompt_toolkit`, `cryptography`. Install via `requirements.txt`.
- **TUI mode**: full terminal UI (Textual) with DataTable, keyboard navigation (Space=toggle, a=all/none, ↑↓=navegar entre secciones, →/←=pages with auto-fetch, Enter=download), inline help bar, single overall ProgressBar + done-list, post-download summary with "Nueva búsqueda" button. Search uses `extract_flat=True` for speed.
- **Custom widget classes** (`tui_app.py`): `SearchInput(Input)` with `key_down()` to focus results table; `SearchResults(DataTable)` with `action_cursor_up()` (focus search at row 0) and `action_cursor_down()` (focus "Descargar" button at last row); `NavButton(Button)` with `key_up()` to focus results table. Enables full ↑/↓ navigation between search, results, and action bar.
- **Mode selection**: tres botones (Normal / Artista / Sin filtro) entre el Input y la tabla; Normal añade " audio", Artista busca " topic" (canales oficiales), Sin filtro sin sufijo. Playlist se auto-detecta al pegar URL.
- **Importar button**: botón en la action bar que abre `ImportFileScreen` — lista archivos `.txt` del directorio actual, al hacer click en uno valida URLs y extrae títulos para mostrar en la tabla.
- **Concurrent downloads** via `-j`/`--jobs` (default: 3), single overall ProgressBar with current file + done-list.
- **`extract_flat=True`** in search for near-instant results; no view counts in table.
- **Cursor preserved** when toggling selection (table clears and rebuilds but cursor stays on same row); cursor vuelve a fila 0 al cambiar de página.
- **Output**: `downloads/` directory by default, created if missing.
- **Quality**: extracts best audio → MP3 at **320 kbps** (`preferredquality: "0"` = best, `-ab 320k`).
- **Metadata**: embeds title/artist/album etc. via `FFmpegMetadata` postprocessor.
- **Filename**: truncated to 100 chars max stem, invalid chars sanitized.
- **Module structure** (`src/`): `main.py` (CLI entry), `downloader.py` (yt-dlp wrapper, batches), `ui.py` (interactive mode), `tui_app.py` (Textual TUI), `storage.py` (encrypted persistence), `models.py` (data types), `utils.py` (shared helpers).
- **Encrypted store**: single file `data/store.dat` (auto-generated) for search history + download log. `data/` is in `.gitignore`.
  - **Key**: `data/.key` generado con `Fernet.generate_key()` en el primer uso (no más derivación de USERNAME).
  - **Backup**: `store.dat.bak` creado automáticamente antes de cada sobrescritura.
  - **Validación**: verifica esquema al cargar; si `store.dat` está corrupto, carga desde `.bak`.
  - **Límite**: máximo 500 entradas por lista (las más viejas se descartan automáticamente).
- **Performance optimizations**:
  - `descargar_mp3` avoids double `extract_info` when `titulo` is provided (skips pre-extraction HTTP request).
  - `download_batch` pre-extracts titles sequentially before parallel download pool starts.
  - `storage.py` uses dirty-flag writes — `register_search`/`register_download` defer I/O until `flush_store()` is called (once per download batch or on app exit).
  - `tui_app.py` fetches 100 results initially (`MAX_RESULTS=100`), paginates in 100-result increments (fewer re-fetches), muestra 30 por página.
- **Search dedup** (`tui_app.py`): normaliza títulos con regex (saca "(Official Video)", "(Lyrics)", "(Cover)", etc.), agrupa por título + bucket de duración (±4s), conserva el de más visitas. Resultados de covers/remixes/karaokes se ordenan al final. Todo en `_rerank_entries()`.
- **Estado column**: 6th column shows `⤵` for previously downloaded songs (from persistent store). Selection (`✓`) and download status are independent columns.
- **Import auto-select**: al importar `.txt`, canciones ya en `self.descargadas` no se seleccionan automáticamente.
- **No tests, linters, or typecheckers** configured. No CI.
- `.opencode/` directory is OpenCode internal tooling; not part of project code.
