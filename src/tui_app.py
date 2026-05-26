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
