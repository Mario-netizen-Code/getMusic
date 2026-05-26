from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Input, DataTable, Button, Static, ProgressBar
from textual.containers import Horizontal, Vertical

from datetime import date
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
        dock: top;
        margin: 1 2;
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
    .prow {
        height: 3;
        margin-bottom: 1;
    }
    .prow > Static:first-child {
        width: 42;
    }
    .prow > ProgressBar {
        width: 1fr;
    }
    .prow > Static:last-child {
        width: 30;
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

    def __init__(self, archivo: str = "", salida: str = "", max_workers: int = 3):
        super().__init__()
        if not salida:
            salida = str(Path("downloads") / date.today().isoformat())
        self.archivo: str = archivo
        self.base_salida: str = salida
        self.max_workers: int = max_workers
        self.page_num: int = 0
        self.page_size: int = 5
        self.artist_mode: bool = False
        self.raw_mode: bool = False
        self.busqueda: str = ""
        self.entries: list[dict] = []
        self._all_entries: list[dict] = []
        self._fetched_total: int = 0
        self._fetching_more: bool = False
        self.selected: set[str] = set()
        self.descargadas: set[str] = {e["url"] for e in load_downloads() if e.get("url")}
        self._progress_widgets: dict[str, tuple[Static, ProgressBar, Static]] = {}
        self._download_jobs: list[DownloadJob] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-content"):
            yield Input(id="search-input", placeholder="Canción: Escribe y presiona Enter...")
            yield Static(self.HELP_TEXT, id="help-text", classes="help-line")
            yield DataTable(id="results-table")
            yield Vertical(id="progress-area")
        yield Static(id="status-bar")
        with Horizontal(id="action-bar"):
            yield Button("Descargar", id="download-btn", variant="primary")
            yield Button("Salir", id="quit-btn")

    def action_quit(self) -> None:
        self.exit()

    def on_mount(self) -> None:
        self.query_one("#results-table", DataTable).cursor_type = "row"

    def on_unmount(self) -> None:
        flush_store()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        if not raw:
            return
        self.selected.clear()
        self.artist_mode = raw.startswith("@")
        self.raw_mode = raw.startswith("!")
        self.busqueda = raw[1:] if (self.artist_mode or self.raw_mode) else raw

        playlist_str = raw[1:] if raw.startswith("/") else raw
        if is_playlist_url(playlist_str):
            self._playlist_url = playlist_str
            self._set_status("Cargando playlist...")
            self._set_help("Cargando playlist...")
            self.run_worker(self._search_playlist, thread=True)
        else:
            self.page_size = 50 if self.artist_mode else 5
            self.page_num = 0
            self._fetched_total = 0
            self._fetching_more = False
            self._set_status("Buscando...")
            self._set_help("Buscando...")
            self.run_worker(self._search_yt, thread=True)

    MAX_RESULTS = 100
    HELP_TEXT = "Esp=Sel  a=Todo/Nada  →=SigPag  ←=AntPag  Enter=Desc  Ctrl+Q=Salir"

    def _search_yt(self) -> None:
        try:
            self._fetched_total = max(self._fetched_total, self.MAX_RESULTS)
            query = f"ytsearch{self._fetched_total}:{self.busqueda}"
            if not self.raw_mode and not self.artist_mode:
                query += " audio"

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

    def _format_views(self, n: int | None) -> str:
        if n is None:
            return ""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        return str(n)

    def _update_table(self) -> None:
        table = self.query_one("#results-table", DataTable)
        cursor_row = table.cursor_row
        table.clear(columns=True)
        table.add_columns("", "#", "Título", "Artista", "Dur", "Vistas")

        inicio = self.page_num * self.page_size + 1
        for i, e in enumerate(self.entries[self.page_num * self.page_size:(self.page_num + 1) * self.page_size], inicio):
            url = e.get("webpage_url", "")
            if url in self.selected:
                checked = "✓"
            elif url in self.descargadas:
                checked = "⤵"
            else:
                checked = " "
            dur = int(e.get("duration", 0) or 0)
            m, s = divmod(dur, 60)
            tit = e.get("title", "?")[:60]
            chan = (e.get("channel") or e.get("uploader", "?"))[:25]
            views = self._format_views(e.get("view_count"))
            table.add_row(checked, str(i), tit, chan, f"{m}:{s:02d}", views)

        if cursor_row is not None and cursor_row < table.row_count:
            table.move_cursor(row=cursor_row)

        self._set_help(self.HELP_TEXT)
        self._set_status(f"Página {self.page_num + 1} — {len(self.entries)} resultados")
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
            self._update_table()

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
        self._update_table()

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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("quit-btn", "quit-summary-btn"):
            self.exit()
        elif event.button.id == "download-btn":
            self.action_start_download()
        elif event.button.id == "new-search-btn":
            self.action_new_search()

    def _build_jobs(self) -> list[DownloadJob]:
        jobs = []
        search_query = self.busqueda
        for entry in self.entries:
            url = entry.get("webpage_url")
            if url and url in self.selected:
                salida = self.base_salida
                if self.artist_mode:
                    salida = str(Path(self.base_salida).parent / sanitize_filename(search_query))
                    Path(salida).mkdir(parents=True, exist_ok=True)
                jobs.append(DownloadJob(
                    url=url,
                    salida=salida,
                    query=search_query,
                    titulo=entry.get("title", "?"),
                    channel=entry.get("channel") or entry.get("uploader", "?"),
                ))
        return jobs

    def action_start_download(self) -> None:
        if not self.selected:
            return
        jobs = self._build_jobs()
        if not jobs:
            return

        self.query_one("#search-input").display = False
        self.query_one("#results-table").display = False
        self.query_one("#help-text").display = False
        self.query_one("#action-bar").display = False

        progress_area = self.query_one("#progress-area")
        progress_area.display = True
        progress_area.remove_children()

        self._progress_widgets = {}
        self._download_jobs = jobs
        for i, job in enumerate(jobs):
            label = Static(job.titulo[:60])
            bar = ProgressBar(total=100)
            status = Static("")
            row = Horizontal(label, bar, status, classes="prow", id=f"prow-{i}")
            progress_area.mount(row)
            self._progress_widgets[job.url] = (label, bar, status)

        self._set_status("Descargando...")
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
        widgets = self._progress_widgets.get(url)
        if not widgets:
            return
        _, bar, status = widgets
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total and downloaded:
                bar.progress = downloaded / total * 100
        elif d["status"] == "finished":
            bar.progress = 100
        elif d["status"] == "error":
            status.update("✗ Error en descarga")

    def _mark_done(self, job: DownloadJob, success: bool, error: str = "") -> None:
        widgets = self._progress_widgets.get(job.url)
        if not widgets:
            return
        _, bar, status = widgets
        if success:
            bar.progress = 100
            status.update("✓ Listo")
            if job.query:
                register_search(job.query)
            register_download(job.url, job.titulo, job.channel, job.query)
            self.descargadas.add(job.url)
        else:
            status.update(f"✗ {error}")

    def _finish_downloads(self, done: int, err: int) -> None:
        total = done + err
        msg = f"✓ {done}/{total} completadas"
        if err:
            msg += f"  ✗ {err} errores"
        self._set_status(msg)
        flush_store()
        progress_area = self.query_one("#progress-area")
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
