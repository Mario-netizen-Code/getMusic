from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Input, DataTable, Button, Static
from textual.containers import Horizontal, Vertical

from datetime import date
from pathlib import Path

import yt_dlp

from models import DownloadJob
from storage import load_downloads, register_search
from utils import is_playlist_url, sanitize_filename


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
        self.selected: set[str] = set()
        self.descargadas: set[str] = {e["url"] for e in load_downloads() if e.get("url")}

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

    def on_mount(self) -> None:
        self.query_one("#results-table", DataTable).cursor_type = "row"

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
            self.run_worker(self._search_playlist(playlist_str), worker_type="thread")
        else:
            self.page_size = 50 if self.artist_mode else 5
            self.page_num = 0
            self.run_worker(self._search_yt(), worker_type="thread")

    def _search_yt(self) -> None:
        self.call_from_thread(self._set_status, "Buscando...")
        try:
            total = (self.page_num + 1) * self.page_size
            query = f"ytsearch{total}:{self.busqueda}"
            if not self.raw_mode and not self.artist_mode:
                query += " audio"

            opts = {
                "quiet": True, "no_warnings": True, "ignoreerrors": True,
                "no_color": True, "extract_flat": False,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)

            page = [e for e in (info.get("entries") if info else []) if e]
            for e in page:
                if not e.get("webpage_url"):
                    e["webpage_url"] = e.get("url", f"https://www.youtube.com/watch?v={e.get('id', '')}")
            self.entries = page
        except Exception as e:
            self.call_from_thread(self._set_status, f"Error al buscar: {e}")
            self.entries = []

        self.call_from_thread(self._update_table)

    def _set_status(self, text: str) -> None:
        self.query_one("#status-bar", Static).update(text)

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
        max_page = (len(self.entries) - 1) // self.page_size
        if self.page_num < max_page:
            self.page_num += 1
            self._update_table()

    def action_prev_page(self) -> None:
        if self.page_num > 0:
            self.page_num -= 1
            self._update_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._toggle_row(event.cursor_row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-btn":
            self.exit()
        elif event.button.id == "download-btn":
            self.action_start_download()

    def action_start_download(self) -> None:
        self._set_status("Descargando...")

    def _search_playlist(self, url: str) -> None:
        self.call_from_thread(self._set_status, "Cargando playlist...")
        try:
            opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True, "no_color": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            entries = [e for e in (info.get("entries") if info else []) if e]
            for e in entries:
                if not e.get("webpage_url"):
                    e["webpage_url"] = f"https://youtube.com/watch?v={e.get('id', '')}"
            self.page_num = 0
            self.page_size = len(entries) or 1
            self.entries = entries
        except Exception as e:
            self.call_from_thread(self._set_status, f"Error al cargar playlist: {e}")
            self.entries = []

        self.call_from_thread(self._update_table)


if __name__ == "__main__":
    app = MusicApp()
    app.run()
