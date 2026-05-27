import re

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Header, Input, DataTable, Button, Static, ProgressBar, ListView, ListItem, Label
from textual.containers import Horizontal, Vertical


class SearchInput(Input):
    def key_down(self) -> None:
        self.app.query_one("#results-table", DataTable).focus()


class NavButton(Button):
    def key_up(self) -> None:
        self.app.query_one("#results-table", DataTable).focus()


class SearchResults(DataTable):
    def action_cursor_up(self) -> None:
        if self.cursor_row == 0:
            self.app.query_one("#search-input", Input).focus()
        else:
            super().action_cursor_up()

    def action_cursor_down(self) -> None:
        if self.cursor_row == self.row_count - 1:
            self.app.query_one("#download-btn", Button).focus()
        else:
            super().action_cursor_down()

class ImportFileScreen(Screen[list[dict]]):
    CSS = """
    .import-actions {
        height: 3;
        align: center middle;
        margin: 1 2;
    }
    #file-list {
        margin: 0 2;
        height: 1fr;
    }
    #import-status {
        margin: 1 2 0 2;
        height: 1;
        text-align: center;
    }
    #import-progress {
        margin: 0 2 1 2;
        height: 1;
        background: $surface;
        color: $text;
    }
    """
    BINDINGS = [
        Binding("escape", "dismiss", "Cancelar", priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header("Importar archivo de URLs")
        with Horizontal(classes="import-actions"):
            yield Button("Refrescar", id="refresh-btn", variant="primary")
        yield Static("Seleccioná un archivo .txt de la carpeta urls/:", classes="help-line")
        yield ListView(id="file-list")
        yield Static(id="import-status")
        yield Static("", id="import-progress")

    def on_mount(self) -> None:
        self._import_active = False
        self._found = 0
        self._setup_file_list()

    def _setup_file_list(self) -> None:
        folder = Path("urls")
        folder.mkdir(exist_ok=True)
        self._files = sorted(folder.glob("*.txt"))
        lv = self.query_one("#file-list", ListView)
        lv.clear()
        if not self._files:
            lv.append(ListItem(Label("La carpeta urls/ está vacía. Poné tus archivos .txt ahí.")))
        else:
            for f in self._files:
                st = f.stat()
                size = st.st_size
                modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                lv.append(ListItem(Label(f"{f.name}  ({size:,} bytes, {modified})")))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-btn":
            self._setup_file_list()

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#import-status", Static).update(msg)
        except Exception:
            pass

    def _init_pb(self) -> None:
        self._found = 0
        self.query_one("#import-progress", Static).update("")

    def _advance_pb(self, count: int) -> None:
        self._found += count
        self.query_one("#import-progress", Static).update(f"Encontrados {self._found} videos...")
        self.query_one("#import-status", Static).update(f"Extrayendo... ({self._found} videos encontrados)")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and idx < len(self._files):
            path = str(self._files[idx])
            self._set_status("Leyendo archivo...")
            self.query_one("#file-list", ListView).display = False
            self.run_worker(lambda: self._do_import(path), thread=True)

    def _do_import(self, path: str) -> None:
        try:
            urls = self._read_urls_file(path)
        except Exception as e:
            self.app.call_from_thread(self._set_status, f"Error al leer archivo: {e}")
            return

        if not urls:
            self.app.call_from_thread(self._set_status, "No se encontraron URLs válidas de YouTube")
            return

        total = len(urls)
        self.app.call_from_thread(self._set_status, f"Extrayendo {total} URLs...")

        all_entries: list[list[dict]] = [None] * total

        def _extract_one(i_url):
            i, url = i_url
            try:
                flat = is_playlist_url(url)
                opts = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
                if flat:
                    opts["extract_flat"] = True
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    playlist_items = info.get("entries")
                    if playlist_items:
                        return [{
                            "title": it.get("title", url),
                            "webpage_url": it.get("webpage_url") or it.get("url", url),
                            "channel": it.get("channel") or it.get("uploader", ""),
                            "uploader": it.get("uploader", ""),
                            "duration": it.get("duration", 0) or 0,
                            "view_count": it.get("view_count"),
                            "url": it.get("url") or it.get("webpage_url", url),
                        } for it in playlist_items if it]
                    return [{
                        "title": info.get("title", url),
                        "webpage_url": url,
                        "channel": info.get("channel") or info.get("uploader", ""),
                        "uploader": info.get("uploader", ""),
                        "duration": info.get("duration", 0) or 0,
                        "view_count": info.get("view_count"),
                        "url": url,
                    }]
            except Exception:
                return [{
                    "title": url,
                    "webpage_url": url,
                    "channel": "",
                    "uploader": "",
                    "duration": 0,
                    "view_count": 0,
                    "url": url,
                }]

        self.app.call_from_thread(self._init_pb)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            fut_map = {ex.submit(_extract_one, (i, u)): i for i, u in enumerate(urls)}
            for fut in concurrent.futures.as_completed(fut_map):
                idx = fut_map[fut]
                items = fut.result()
                all_entries[idx] = items
                self.app.call_from_thread(self._advance_pb, len(items))

        flat = [e for batch in all_entries if batch for e in batch]
        self.app.call_from_thread(self.dismiss, flat)

    def _read_urls_file(self, path: str) -> list[str]:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        pattern = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/")
        return [u for u in lines if pattern.match(u)]

    def action_dismiss(self) -> None:
        self.dismiss([])


from datetime import date, datetime
from pathlib import Path

import concurrent.futures

import yt_dlp

from models import DownloadJob
from storage import load_downloads, register_search, register_download, flush_store
from utils import is_playlist_url, sanitize_filename
from downloader import descargar_mp3


class MusicApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #search-input {
        margin: 1 2 0 2;
    }
    #mode-row {
        height: 3;
        align: center middle;
        margin: 0 2;
    }
    #mode-row Button {
        margin: 0 1;
        min-width: 10;
    }
    .help-line {
        height: 1;
        text-align: center;
        color: $text-muted;
        padding: 0 1;
    }
    #results-table {
        height: 1fr;
        margin: 0 1;
    }
    #progress-area {
        height: 1fr;
        overflow-y: auto;
        display: none;
        padding: 1 2;
    }
    #main-content {
        height: 1fr;
    }
    #overall-bar {
        margin: 1 2 0 2;
    }
    #counter-label {
        height: 1;
        text-align: center;
        color: $text-muted;
        margin: 0 2 0 2;
    }
    #current-file {
        height: 1;
        margin: 0 2 1 2;
        text-align: center;
        color: $text;
    }
    #done-list {
        height: 1fr;
        overflow-y: auto;
        margin: 0 2;
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
        Binding("space", "toggle_selection", "Seleccionar", priority=True),
        Binding("a", "toggle_all", "Todo/Nada", priority=True),
        Binding("right", "next_page", "→ Pág", priority=True),
        Binding("left", "prev_page", "← Pág", priority=True),
    ]

    def __init__(self, salida: str = "", max_workers: int = 3):
        super().__init__()
        if not salida:
            salida = str(Path("downloads") / date.today().isoformat())
        self.base_salida: str = salida
        self.max_workers: int = max_workers
        self.page_num: int = 0
        self.page_size: int = 30
        self._mode: str = "normal"
        self.busqueda: str = ""
        self.entries: list[dict] = []
        self._all_entries: list[dict] = []
        self._fetched_total: int = 0
        self._fetching_more: bool = False
        self.selected: set[str] = set()
        self.descargadas: set[str] = {e["url"] for e in load_downloads() if e.get("url")}
        self._download_jobs: list[DownloadJob] = []
        self._job_by_url: dict[str, DownloadJob] = {}
        self._importing: bool = False
        self._downloading: bool = False
        self._playlist_url: str = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-content"):
            yield SearchInput(id="search-input", placeholder="Buscar canción, pegar URL de playlist...")
            with Horizontal(id="mode-row"):
                yield Button("Normal", id="mode-normal-btn", variant="primary")
                yield Button("Artista", id="mode-topic-btn")
                yield Button("Sin filtro", id="mode-raw-btn")
            yield Static(self.HELP_TEXT, id="help-text", classes="help-line")
            yield SearchResults(id="results-table")
            yield Vertical(id="progress-area")
        yield Static(id="status-bar")
        with Horizontal(id="action-bar"):
            yield NavButton("Descargar", id="download-btn", variant="primary")
            yield NavButton("Importar", id="import-btn")
            yield NavButton("Salir", id="quit-btn")

    def action_quit(self) -> None:
        self.exit()

    def on_mount(self) -> None:
        self.query_one("#results-table", DataTable).cursor_type = "row"
        self.set_timer(0, lambda: self.query_one("#search-input", Input).focus())

    def on_unmount(self) -> None:
        flush_store()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            return
        if self._importing:
            self._set_status("Importación en curso... espera")
            return
        self.selected.clear()
        self.busqueda = raw
        self.page_num = 0
        self._fetched_total = 0
        self._fetching_more = False

        if is_playlist_url(raw):
            self._playlist_url = raw
            self._set_status("Cargando playlist...")
            self._set_help("Cargando playlist...")
            self.run_worker(self._search_playlist, thread=True)
        else:
            self.page_size = 30
            self._set_status(f"Modo {self._mode_label()} · buscando...")
            self._set_status("Buscando...")
            self._set_help("Buscando...")
            self.run_worker(self._search_yt, thread=True)

    MAX_RESULTS = 100
    HELP_TEXT = "Esp=Sel  a=Todo/Nada  ↑/↓=Navegar  →←=Pág  Tab=Cambiar  Enter=Desc  Ctrl+Q=Salir"

    def _search_yt(self) -> None:
        try:
            self._fetched_total = max(self._fetched_total, self.MAX_RESULTS)
            query = f"ytsearch{self._fetched_total}:{self.busqueda}"
            if self._mode == "normal":
                query += " audio"
            elif self._mode == "topic":
                query += " topic"

            opts = {
                "quiet": True, "no_warnings": True, "ignoreerrors": True,
                "no_color": True, "extract_flat": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)

            self._all_entries = [e for e in (info.get("entries") if info else []) if e]
            for e in self._all_entries:
                if not e.get("webpage_url"):
                    e["webpage_url"] = e.get("url", f"https://www.youtube.com/watch?v={e.get('id', '')}")
            self._rerank_entries(self._all_entries)
            self.entries = self._all_entries
            if self._fetching_more:
                max_page = (len(self._all_entries) - 1) // self.page_size
                if self.page_num < max_page:
                    self.page_num += 1
                self._fetching_more = False
        except Exception as e:
            self.call_from_thread(self._set_status, f"Error al buscar: {e}")
            self.call_from_thread(self._set_help, f"Error: {e}")
            self._all_entries = []
            self.entries = []

        self.call_from_thread(self._update_table)

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

    # also show status in the help-text area for more visibility
    def _set_help(self, text: str) -> None:
        try:
            self.query_one("#help-text", Static).update(text)
        except Exception:
            pass

    @staticmethod
    def _normalize_title(title: str) -> str:
        t = title.lower()
        t = re.sub(
            r'\([^)]*(?:official|music\s*video|video|lyrics?|audio|hq|hd|4k|'
            r'remastered|live|cover|karaoke|tribute|instrumental|reaction|'
            r'mashup|feat\.?|ft\.?|explicit|edit|version)[^)]*\)',
            '', t, flags=re.I
        )
        t = re.sub(r'\[[^\]]*\]', '', t)
        t = re.sub(r'\s*\|\s*.*$', '', t)
        t = re.sub(r'\s*[-–—]\s*topic\s*$', '', t, flags=re.I)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    @staticmethod
    def _is_low_quality(e: dict) -> bool:
        title = e.get("title", "") or ""
        return bool(re.search(
            r'[(\[][^)\]]*(?:cover|remix|karaoke|tribute|reaction|mashup|instrumental)',
            title, re.I
        ))

    @staticmethod
    def _rerank_entries(entries: list[dict]) -> None:
        groups: dict[tuple, dict] = {}
        for e in entries:
            norm = MusicApp._normalize_title(e.get("title", "") or "")
            dur = e.get("duration", 0) or 0
            bucket = dur // 4
            key = (norm, bucket)
            existing = groups.get(key)
            if existing is None or (e.get("view_count", 0) or 0) > (existing.get("view_count", 0) or 0):
                groups[key] = e
        entries.clear()
        entries.extend(groups.values())
        entries.sort(key=lambda e: (
            1 if MusicApp._is_low_quality(e) else 0,
            -((e.get("view_count", 0) or 0))
        ))

    def _update_table(self, *, preserve_cursor: bool = False) -> None:
        table = self.query_one("#results-table", DataTable)
        cursor_row = table.cursor_row if preserve_cursor else None
        table.clear(columns=True)
        table.add_columns("", "#", "Título", "Artista", "Dur", "Estado")
        cols = table.ordered_columns
        if len(cols) >= 6:
            cols[5].width = 3

        inicio = self.page_num * self.page_size + 1
        for i, e in enumerate(self.entries[self.page_num * self.page_size:(self.page_num + 1) * self.page_size], inicio):
            url = e.get("webpage_url", "")
            checked = "✓" if url in self.selected else " "
            estado = "⤵" if url in self.descargadas else ""
            dur = int(e.get("duration", 0) or 0)
            m, s = divmod(dur, 60)
            tit = e.get("title", "?")[:60]
            chan = (e.get("channel") or e.get("uploader", "?"))[:25]
            table.add_row(checked, str(i), tit, chan, f"{m}:{s:02d}", estado)

        if cursor_row is not None and cursor_row < table.row_count:
            table.move_cursor(row=cursor_row)

        self._set_help(self.HELP_TEXT)
        self._set_status(f"{self._mode_label()} · Página {self.page_num + 1} — {len(self.entries)} resultados")
        self._update_action_bar()

    def _update_action_bar(self) -> None:
        btn = self.query_one("#download-btn", Button)
        n = len(self.selected)
        btn.label = f"Descargar ({n})" if n else "Descargar"

    def _toggle_row(self, cursor_row: int | None) -> None:
        if cursor_row is None:
            return
        idx = self.page_num * self.page_size + cursor_row
        if idx < len(self.entries):
            url = self.entries[idx].get("webpage_url")
            if not url:
                return
            if url in self.selected:
                self.selected.discard(url)
            else:
                self.selected.add(url)
            self._update_table(preserve_cursor=True)

    def action_toggle_selection(self) -> None:
        table = self.query_one("#results-table", DataTable)
        self._toggle_row(table.cursor_row)

    def action_toggle_all(self) -> None:
        start = self.page_num * self.page_size
        end = (self.page_num + 1) * self.page_size
        visible = self.entries[start:end]
        visible_urls = {e.get("webpage_url", "") for e in visible if e.get("webpage_url")}
        if visible_urls.issubset(self.selected):
            self.selected -= visible_urls
        else:
            self.selected |= visible_urls
        self._update_table(preserve_cursor=True)

    def action_next_page(self) -> None:
        max_page = (len(self._all_entries) - 1) // self.page_size
        if self.page_num < max_page:
            self.page_num += 1
            self._update_table()
        else:
            self._fetched_total += self.MAX_RESULTS
            self._fetching_more = True
            self._set_status("Cargando más resultados...")
            self._set_help("Cargando más resultados...")
            self.run_worker(self._search_yt, thread=True)

    def action_prev_page(self) -> None:
        if self.page_num > 0:
            self.page_num -= 1
            self._update_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._toggle_row(event.cursor_row)

    def _mode_label(self) -> str:
        return {"normal": "Normal", "topic": "Artista", "raw": "Sin filtro"}.get(self._mode, "Normal")

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        for mid, bid in [("normal", "mode-normal-btn"), ("topic", "mode-topic-btn"), ("raw", "mode-raw-btn")]:
            btn = self.query_one(f"#{bid}", Button)
            btn.variant = "primary" if mid == mode else "default"
        self.query_one("#search-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("quit-btn", "quit-summary-btn"):
            self.exit()
        elif event.button.id == "download-btn":
            self.action_start_download()
        elif event.button.id == "import-btn":
            self.action_import()
        elif event.button.id == "new-search-btn":
            self.action_new_search()
        elif event.button.id == "mode-normal-btn":
            self._set_mode("normal")
        elif event.button.id == "mode-topic-btn":
            self._set_mode("topic")
        elif event.button.id == "mode-raw-btn":
            self._set_mode("raw")

    def action_import(self) -> None:
        if self._importing:
            return
        self.push_screen(ImportFileScreen(), self._on_import_file)

    def _on_import_file(self, entries: list[dict]) -> None:
        if not entries:
            return
        self._set_imported_entries(entries)

    def _set_imported_entries(self, entries: list[dict]) -> None:
        self._importing = False
        self._fetched_total = 0
        self._fetching_more = False
        self.busqueda = ""
        self._all_entries = entries
        self.entries = entries
        self.selected.clear()
        self.selected.update(
            e.get("webpage_url", "") for e in entries
            if e.get("webpage_url") and e.get("webpage_url") not in self.descargadas
        )
        self.page_num = 0
        self.page_size = 30
        self._update_table()
        self._set_status(f"Importadas: {len(entries)} canciones  |  "
                         f"Modo {self._mode_label()} · Página 1 — {len(entries)} resultados")
        self._set_help(self.HELP_TEXT)

    def _build_jobs(self) -> list[DownloadJob]:
        jobs = []
        search_query = self.busqueda
        seen: set[str] = set()
        for entry in self.entries:
            url = entry.get("webpage_url")
            if url and url in self.selected and url not in seen:
                seen.add(url)
                salida = self.base_salida
                jobs.append(DownloadJob(
                    url=url,
                    salida=salida,
                    query=search_query,
                    titulo=entry.get("title", "?"),
                    channel=entry.get("channel") or entry.get("uploader", "?"),
                ))
        return jobs

    def action_start_download(self) -> None:
        if not self.selected or self._downloading:
            return
        jobs = self._build_jobs()
        if not jobs:
            return

        self.query_one("#search-input").display = False
        self.query_one("#mode-row").display = False
        self.query_one("#results-table").display = False
        self.query_one("#help-text").display = False
        self.query_one("#action-bar").display = False

        progress_area = self.query_one("#progress-area")
        progress_area.display = True
        progress_area.remove_children()

        self._download_jobs = jobs
        self._job_by_url = {job.url: job for job in jobs}
        self._done_count = 0
        self._total_count = len(jobs)

        self._overall_bar = ProgressBar(total=self._total_count, id="overall-bar")
        progress_area.mount(self._overall_bar)
        progress_area.mount(Static(f"0 / {self._total_count} completados", id="counter-label"))
        progress_area.mount(Static(id="current-file"))
        progress_area.mount(Vertical(id="done-list"))

        self._set_status(f"Descargando 0/{self._total_count}...")
        self._downloading = True
        self.run_worker(self._run_downloads, thread=True)

    def _run_downloads(self) -> None:
        def _cb(url):
            def _progress(d):
                self.call_from_thread(self._update_progress, url, d)
            return _progress

        done = err = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            fut_to_job = {}
            for job in self._download_jobs:
                fut = ex.submit(descargar_mp3, job.url, job.salida, _cb(job.url), job.titulo)
                fut_to_job[fut] = job

            for fut in concurrent.futures.as_completed(fut_to_job):
                job = fut_to_job[fut]
                try:
                    fut.result()
                    done += 1
                    self.call_from_thread(self._mark_done, job, True)
                except Exception as e:
                    err += 1
                    self.call_from_thread(self._mark_done, job, False, str(e))

        self.call_from_thread(self._finish_downloads, done, err)

    def _update_progress(self, url: str, d: dict) -> None:
        job = self._job_by_url.get(url)
        if not job:
            return
        if d["status"] == "downloading":
            try:
                self.query_one("#current-file", Static).update(f"Descargando: {job.titulo[:60]}")
            except Exception:
                pass

    def _mark_done(self, job: DownloadJob, success: bool, error: str = "") -> None:
        self._done_count += 1
        try:
            self._overall_bar.progress = self._done_count
            self.query_one("#counter-label", Static).update(
                f"{self._done_count} / {self._total_count} completados"
            )
            dl = self.query_one("#done-list", Vertical)
            label = f"✓ {job.titulo[:60]}" if success else f"✗ {job.titulo[:60]}: {error}"
            dl.mount(Static(label))
            if self._done_count < self._total_count:
                self.query_one("#current-file", Static).update("")
        except Exception:
            pass
        if success:
            if job.query:
                register_search(job.query)
            register_download(job.url, job.titulo, job.channel, job.query)
            self.descargadas.add(job.url)

    def _finish_downloads(self, done: int, err: int) -> None:
        if not self._downloading:
            return
        self._downloading = False
        total = done + err
        msg = f"✓ {done}/{total} completadas"
        if err:
            msg += f"  ✗ {err} errores"
        self._set_status(msg)
        flush_store()
        progress_area = self.query_one("#progress-area")
        if progress_area.query("Horizontal#summary-bar"):
            return
        progress_area.mount(
            Horizontal(
                Button("Nueva búsqueda", id="new-search-btn", variant="primary"),
                Button("Salir", id="quit-summary-btn"),
                id="summary-bar",
            )
        )

    def action_new_search(self) -> None:
        self.query_one("#progress-area").remove_children()
        self.query_one("#progress-area").display = False
        self.query_one("#search-input").display = True
        self.query_one("#mode-row").display = True
        self.query_one("#results-table").display = True
        self.query_one("#help-text").display = True
        self.query_one("#action-bar").display = True
        self.selected.clear()
        self.entries = []
        self._all_entries = []
        self._fetched_total = 0
        self._fetching_more = False
        self.page_num = 0
        self._update_table()
        self.query_one("#search-input", Input).focus()

    def _search_playlist(self) -> None:
        try:
            opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True, "no_color": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self._playlist_url, download=False)

            entries = [e for e in (info.get("entries") if info else []) if e]
            for e in entries:
                if not e.get("webpage_url"):
                    e["webpage_url"] = f"https://youtube.com/watch?v={e.get('id', '')}"
            self.page_num = 0
            self.page_size = len(entries) or 1
            self.entries = entries
        except Exception as e:
            self.call_from_thread(self._set_status, f"Error al cargar playlist: {e}")
            self.call_from_thread(self._set_help, f"Error: {e}")
            self.entries = []

        self.call_from_thread(self._update_table)


if __name__ == "__main__":
    app = MusicApp()
    app.run()
