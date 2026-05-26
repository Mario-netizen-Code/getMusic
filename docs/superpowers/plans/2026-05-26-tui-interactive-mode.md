# TUI Interactive Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace prompt_toolkit dialog-based `--add` mode with a full Textual TUI app.

**Architecture:** New `src/tui_app.py` contains `MusicApp(Textual.App)` — a single-screen app with Input, DataTable (search results), dynamic ProgressBar widgets (downloads), and action buttons. Existing modules (`downloader.py`, `storage.py`, `models.py`, `utils.py`) remain unchanged.

**Tech Stack:** Python 3.10+, Textual 0.52+, yt-dlp, tqdm, cryptography

---

### Task 1: Project setup and skeleton

**Files:**
- Modify: `requirements.txt` — add textual
- Create: `src/tui_app.py` — skeleton with `MusicApp` class

- [ ] **Step 1: Add textual to requirements.txt**

```txt
# Before
prompt_toolkit
cryptography

# After
textual
prompt_toolkit
cryptography
```

- [ ] **Step 2: Install dependencies**

```powershell
.\venv\Scripts\python -m pip install -r requirements.txt
```
Expected: textual and its deps install without errors.

- [ ] **Step 3: Create tui_app.py skeleton**

```python
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Input, DataTable, Button, Static
from textual.containers import Horizontal, Vertical

from datetime import date
from pathlib import Path


class MusicApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #search-input {
        dock: top;
        margin: 1 2;
    }
    #results-table {
        height: 1fr;
        margin: 0 1;
    }
    #progress-area {
        height: 1fr;
        overflow-y: auto;
        display: none;
    }
    #action-bar {
        dock: bottom;
        height: 3;
        align: center middle;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Salir", priority=True),
    ]

    def __init__(self, archivo: str = "", salida: str = "", max_workers: int = 3):
        super().__init__()
        if not salida:
            salida = str(Path("downloads") / date.today().isoformat())
        self.base_salida: str = salida
        self.max_workers: int = max_workers
        self.page_num: int = 0
        self.page_size: int = 5
        self.artist_mode: bool = False
        self.raw_mode: bool = False
        self.busqueda: str = ""
        self.entries: list[dict] = []
        self.selected: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-content"):
            yield Input(id="search-input", placeholder="Canción: Escribe y presiona Enter...")
            yield DataTable(id="results-table")
            yield Vertical(id="progress-area")
        with Horizontal(id="action-bar"):
            yield Button("Descargar", id="download-btn", variant="primary")
            yield Button("Salir", id="quit-btn")
        yield Static(id="status-bar")

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    app = MusicApp()
    app.run()
```

- [ ] **Step 4: Verify skeleton runs**

```powershell
.\venv\Scripts\python src\tui_app.py
```
Expected: Textual app opens with Header, Input, empty DataTable, action buttons, footer. Press Ctrl+Q to exit.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt src/tui_app.py
git commit -m "feat: add textual dep and tui_app skeleton"
```

---

### Task 2: Search and display results

**Files:**
- Modify: `src/tui_app.py`

**Goal:** Typing a query and pressing Enter triggers yt-dlp search → populates DataTable with results.

- [ ] **Step 1: Add import block and model fields**

After the existing imports, add:

```python
import yt_dlp

from models import DownloadJob
from storage import load_downloads, register_search
from utils import is_playlist_url, sanitize_filename
```

In `__init__`, add:

```python
self.descargadas: set[str] = {e["url"] for e in load_downloads() if e.get("url")}
```

- [ ] **Step 2: Wire Input.submitted to search**

```python
def on_input_submitted(self, event: Input.Submitted) -> None:
    raw = event.value.strip()
    if not raw:
        return
    self.artist_mode = raw.startswith("@")
    self.raw_mode = raw.startswith("!")
    self.busqueda = raw[1:] if (self.artist_mode or self.raw_mode) else raw

    playlist_str = raw[1:] if raw.startswith("/") else raw
    if is_playlist_url(playlist_str):
        self.run_worker(self._search_playlist(playlist_str), worker_type="thread")
    else:
        self.page_size = 50 if self.artist_mode else 5
        self.page_num = 0
        self.run_worker(self._search_yt(), worker_type="thread")
```

- [ ] **Step 3: Implement _search_yt worker**

```python
def _search_yt(self) -> None:
    self.call_from_thread(self._set_status, "Buscando...")
    total = (self.page_num + 1) * self.page_size
    query = f"ytsearch{total}:{self.busqueda}"
    if not self.raw_mode and not self.artist_mode:
        query += " audio"

    opts = {
        "quiet": True, "no_warnings": True, "ignoreerrors": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)

    page = [e for e in (info.get("entries") if info else []) if e]
    for e in page:
        if not e.get("webpage_url"):
            e["webpage_url"] = e.get("url", f"https://www.youtube.com/watch?v={e.get('id', '')}")
    self.entries = page

    self.call_from_thread(self._update_table)

def _set_status(self, text: str) -> None:
    self.query_one("#status-bar", Static).update(text)

def _format_views(self, n: int | None) -> str:
    if not n:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)

def _update_table(self) -> None:
    table = self.query_one("#results-table", DataTable)
    table.clear()
    table.add_columns("", "#", "Título", "Artista", "Dur", "Vistas")

    inicio = self.page_num * self.page_size + 1
    for i, e in enumerate(self.entries[self.page_num * self.page_size:(self.page_num + 1) * self.page_size], inicio):
        url = e.get("webpage_url", "")
        checked = "✓" if url in self.selected else " "
        dur = int(e.get("duration", 0) or 0)
        m, s = divmod(dur, 60)
        tit = e.get("title", "?")[:60]
        chan = (e.get("channel") or e.get("uploader", "?"))[:25]
        views = self._format_views(e.get("view_count"))
        table.add_row(checked, str(i), tit, chan, f"{m}:{s:02d}", views)

    self._set_status(f"Página {self.page_num + 1} — {len(self.entries)} resultados")
```

- [ ] **Step 4: Implement _search_playlist worker**

```python
def _search_playlist(self, url: str) -> None:
    self.call_from_thread(self._set_status, "Cargando playlist...")
    opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = [e for e in (info.get("entries") if info else []) if e]
    for e in entries:
        if not e.get("webpage_url"):
            e["webpage_url"] = f"https://youtube.com/watch?v={e.get('id', '')}"
    self.entries = entries
    self.call_from_thread(self._update_table)
```

- [ ] **Step 5: Verify search works**

```powershell
.\venv\Scripts\python src\tui_app.py
```
Type a song, press Enter. Expected: DataTable populates with results including title, artist, duration, views.

- [ ] **Step 6: Commit**

```bash
git add src/tui_app.py
git commit -m "feat: search and display YouTube results in DataTable"
```

---

### Task 3: Row selection and pagination

**Files:**
- Modify: `src/tui_app.py`

**Goal:** Space toggles row selection, A toggles all, →/← changes page, Enter starts download.

- [ ] **Step 1: Add TITLE column for URL lookup**

In `_update_table`, store URL per row key so we can toggle by key:

```python
def _update_table(self) -> None:
    table = self.query_one("#results-table", DataTable)
    table.clear()
    table.add_columns("", "#", "Título", "Artista", "Dur", "Vistas")
    self._row_key_to_url: dict[str, str] = {}

    inicio = self.page_num * self.page_size + 1
    page_entries = self.entries[self.page_num * self.page_size:(self.page_num + 1) * self.page_size]
    for i, e in enumerate(page_entries, inicio):
        url = e.get("webpage_url", "")
        checked = "✓" if url in self.selected else " "
        dur = int(e.get("duration", 0) or 0)
        m, s = divmod(dur, 60)
        tit = (e.get("title", "?") or "?")[:60]
        chan = (e.get("channel") or e.get("uploader", "?"))[:25]
        views = self._format_views(e.get("view_count"))
        key = table.add_row(checked, str(i), tit, chan, f"{m}:{s:02d}", views)
        self._row_key_to_url[key.value] = url
```

- [ ] **Step 2: Add selection bindings**

Add to BINDINGS:

```python
Binding("space", "toggle_selection", "Seleccionar"),
Binding("a", "toggle_all", "Todo/Nada"),
Binding("right", "next_page", "→ Pág sig"),
Binding("left", "prev_page", "← Pág ant"),
Binding("enter", "confirm_download", "Descargar"),
```

- [ ] **Step 3: Implement selection actions**

```python
def action_toggle_selection(self) -> None:
    table = self.query_one("#results-table", DataTable)
    if table.cursor_row is None:
        return
    row_key = table.get_row_at(table.cursor_row)
    if row_key is None:
        return
    url = self._row_key_to_url.get(row_key.value if hasattr(row_key, 'value') else str(row_key), "")
    if not url:
        return
    if url in self.selected:
        self.selected.remove(url)
    else:
        self.selected.add(url)
    self._update_table()

def action_toggle_all(self) -> None:
    all_urls = []
    inicio = self.page_num * self.page_size
    for e in self.entries[inicio:inicio + self.page_size]:
        url = e.get("webpage_url", "")
        if url:
            all_urls.append(url)
    has_all = all(u in self.selected for u in all_urls)
    for u in all_urls:
        if has_all:
            self.selected.discard(u)
        else:
            self.selected.add(u)
    self._update_table()

def action_next_page(self) -> None:
    max_page = (len(self.entries) - 1) // self.page_size
    if self.page_num < max_page:
        self.page_num += 1
        self._update_table()

def action_prev_page(self) -> None:
    if self.page_num > 0:
        self.page_num -= 1
        self._update_table()
```

- [ ] **Step 4: Verify selection and pagination**

```powershell
.\venv\Scripts\python src\tui_app.py
```
Search something, then verify:
- Space toggles ✓ on cursor row
- A toggles all ✓ on current page
- →/← navigates pages
- ✓ marks are remembered across pages

- [ ] **Step 5: Commit**

```bash
git add src/tui_app.py
git commit -m "feat: selection, toggle-all, and pagination"
```

---

### Task 4: Download phase with progress bars

**Files:**
- Modify: `src/tui_app.py`
- (Possibly) Minor: `src/downloader.py` — if progress_callback type needs adjustment

**Goal:** Pressing Enter (or Download button) switches to progress view, runs concurrent downloads with per-song ProgressBar.

- [ ] **Step 1: Add download button handler**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from textual.widgets import ProgressBar

from downloader import descargar_mp3
from storage import register_download, register_search
```

Add to BINDINGS:

```python
Binding("enter", "confirm_download", "Descargar", show=False),
```

- [ ] **Step 2: Build job list and start download**

```python
def action_confirm_download(self) -> None:
    if not self.selected:
        self._set_status("No hay canciones seleccionadas.")
        return

    register_search(self.busqueda)

    jobs: list[DownloadJob] = []
    for e in self.entries:
        url = e.get("webpage_url", "")
        if url in self.selected:
            artist_name = sanitize_filename(self.busqueda) if self.artist_mode else ""
            salida = str(Path(self.base_salida).parent / artist_name) if artist_name else self.base_salida
            jobs.append(DownloadJob(
                url=url,
                salida=salida,
                query=e.get("title", "?"),
                titulo=e.get("title", "?"),
                channel=e.get("channel") or e.get("uploader", "?"),
            ))

    # Switch view
    self.query_one("#results-table", DataTable).display = False
    self.query_one("#download-btn", Button).disabled = True
    progress_area = self.query_one("#progress-area", Vertical)
    progress_area.display = True
    progress_area.remove_children()

    self._progress_bars: dict[str, ProgressBar] = {}
    for job in jobs:
        row = Horizontal(id=f"dl-{id(job)}")
        label = Static(job.titulo[:60] + "  ")
        bar = ProgressBar(total=100, show_eta=True)
        row.mount(label, bar)
        progress_area.mount(row)
        self._progress_bars[job.url] = bar

    Path(salida).mkdir(parents=True, exist_ok=True)
    self.run_worker(self._run_downloads(jobs), worker_type="thread")
    self._set_status(f"Descargando {len(jobs)} canciones...")
```

- [ ] **Step 3: Implement download runner**

```python
def _run_downloads(self, jobs: list[DownloadJob]) -> None:
    done, errors = 0, 0
    with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
        fut_to_job = {}
        for job in jobs:
            bar = self._progress_bars.get(job.url)
            def make_cb(b):
                def cb(d: dict):
                    pct = d.get("_percent_str", "0%").strip().replace("%", "")
                    try:
                        self.call_from_thread(b.update, progress=float(pct))
                    except (ValueError, AttributeError):
                        pass
                return cb
            fut = pool.submit(descargar_mp3, job.url, job.salida, make_cb(bar))
            fut_to_job[fut] = job

        for fut in as_completed(fut_to_job):
            job = fut_to_job[fut]
            try:
                fut.result()
                done += 1
                self.call_from_thread(register_download, job.url, job.titulo, job.channel, job.query)
            except Exception as e:
                errors += 1
                bar = self._progress_bars.get(job.url)
                if bar:
                    self.call_from_thread(self._mark_error, bar, str(e))

    self.call_from_thread(self._on_downloads_done, done, errors, len(jobs))

def _mark_error(self, bar: ProgressBar, msg: str) -> None:
    bar.update(progress=100)
    bar.styles.background = "red"

def _on_downloads_done(self, done: int, errors: int, total: int) -> None:
    self._set_status(f"✓ {done}/{total} descargadas" + (f"  ✗ {errors} errores" if errors else ""))
    self.query_one("#download-btn", Button).disabled = False
```

- [ ] **Step 4: Add post-download navigation widgets**

Modify the action bar to include a "New search" button after downloads complete.

In `_on_downloads_done`, show the results table again and enable new search:

```python
def _on_downloads_done(self, done: int, errors: int, total: int) -> None:
    self._set_status(f"✓ {done}/{total} descargadas" + (f"  ✗ {errors} errores" if errors else ""))
    self.query_one("#download-btn", Button).disabled = False
    # Add "Nueva búsqueda" button if not already present
    action_bar = self.query_one("#action-bar", Horizontal)
    existing_new = action_bar.query("#new-search-btn")
    if not existing_new:
        new_btn = Button("Nueva búsqueda", id="new-search-btn")
        action_bar.mount(new_btn, before=1 if len(action_bar.children) > 1 else len(action_bar.children))

def on_button_pressed(self, event: Button.Pressed) -> None:
    if event.button.id == "new-search-btn":
        self._reset_view()

def _reset_view(self) -> None:
    self.selected.clear()
    self.entries = []
    self.page_num = 0
    self.query_one("#results-table", DataTable).display = True
    self.query_one("#results-table", DataTable).clear()
    self.query_one("#progress-area", Vertical).display = False
    self.query_one("#progress-area", Vertical).remove_children()
    self.query_one("#search-input", Input).value = ""
    self.query_one("#search-input", Input).focus()
    self.query_one("#download-btn", Button).disabled = False
    # Remove new-search-btn if exists
    existing = self.query_one("#action-bar", Horizontal).query("#new-search-btn")
    if existing:
        existing[0].remove()
    self._set_status("Listo")
```

- [ ] **Step 5: Verify download phase**

```powershell
.\venv\Scripts\python src\tui_app.py
```
Search, select a song, press Enter. Expected: progress bars appear, downloads complete, summary shown, "Nueva búsqueda" button appears.

- [ ] **Step 6: Commit**

```bash
git add src/tui_app.py
git commit -m "feat: download phase with concurrent progress bars"
```

---

### Task 5: Wire main.py and final polish

**Files:**
- Modify: `src/main.py`
- Verify: full end-to-end flow

**Goal:** `--add` flag launches the Textual app. Keep `modo_agregar` importable for fallback.

- [ ] **Step 1: Update main.py imports and --add handler**

```python
# In main.py, replace:
from ui import modo_agregar
# With:
from tui_app import MusicApp
```

Find the `--add` handling block (around line 50-60) and replace:

```python
if args.add:
    modo_agregar(args.archivo, args.output, args.jobs)
# With:
if args.add:
    app = MusicApp(archivo=args.archivo or "", salida=args.output, max_workers=args.jobs)
    app.run()
```

- [ ] **Step 2: Test --add mode end-to-end**

```powershell
.\venv\Scripts\python src\main.py --add
```
Expected: Textual app launches. Test:
- Normal search (enter query → Enter → results appear)
- Raw search (`!query`)
- Artist mode (`@Artist` → 50 results per page)
- Playlist URL pasted
- Selection toggling (Space, A)
- Pagination (→, ←)
- Download with progress bars
- Post-download: "Nueva búsqueda" works
- Ctrl+Q exits cleanly

- [ ] **Step 3: Test normal batch mode still works**

```powershell
.\venv\Scripts\python src\main.py -o "C:\temp\test_dl" tests\test_urls.txt
```
Expected: Batch download works as before (no regression).

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat: wire --add mode to Textual TUI app"
```
