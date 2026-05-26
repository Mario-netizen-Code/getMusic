from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Input, DataTable, Button, Static
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
