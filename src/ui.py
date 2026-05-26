import itertools
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from threading import Event, Thread

import yt_dlp
from prompt_toolkit import prompt as _pt_prompt
from prompt_toolkit.application import Application, get_app
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Button, CheckboxList, Dialog, Label

from downloader import download_batch
from models import DownloadJob
from storage import load_downloads, search_history_suggestions
from utils import is_playlist_url, sanitize_filename, tqdm_write


def _spinner(msg: str):
    stop = Event()
    start = time.time()

    def _spin():
        for c in itertools.cycle(r"-\|/"):
            if stop.is_set():
                break
            elapsed = time.time() - start
            display = f"{msg} (aún buscando...)" if elapsed > 5 else msg
            sys.stdout.write(f"\r  {display} {c}  ({elapsed:.0f}s)")
            sys.stdout.flush()
            time.sleep(0.1)

    Thread(target=_spin, daemon=True).start()

    def cleanup():
        stop.set()
        time.sleep(0.15)
        sys.stdout.write(f"\r{'':80}\r")
        sys.stdout.flush()
        print()

    return cleanup


def _sugerencias_youtube(query: str) -> list[str]:
    try:
        url = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data[1] if len(data) > 1 else []
    except Exception:
        return []


class _YTCompleter(Completer):
    def get_completions(self, document, complete_event):
        raw = document.text.strip()
        if len(raw) < 3:
            return

        prefix = ""
        query = raw
        if raw and raw[0] in ("@", "!"):
            prefix = raw[0]
            query = raw[1:]

        if len(query) < 2:
            return

        vistos = set()
        for s in search_history_suggestions(query):
            vistos.add(s.lower())
            yield Completion(prefix + s, start_position=-len(document.text), display=f"{s} (historial)")

        for s in _sugerencias_youtube(query):
            if s.lower() not in vistos:
                yield Completion(prefix + s, start_position=-len(document.text), display=s)


def _checkbox_seleccion(page, inicio, descargadas: set[str] | None = None):
    values = []
    for j, e in enumerate(page, inicio):
        tit = e.get("title", "?")
        chan = e.get("channel") or e.get("uploader", "?")
        dur = int(e.get("duration", 0) or 0)
        url = e.get("webpage_url", "")
        m, s = divmod(dur, 60)
        dur_str = f"{m}:{s:02d}"
        marca = " \u2713" if (descargadas and url in descargadas) else "  "
        display = f"{j:>2}.{marca} {tit[:52]}  {chan[:18]}  {dur_str}"
        values.append((str(j), display))

    todos_los_valores = [str(v[0]) for v in values]

    style = Style([
        ("dialog", "bg:#000000 fg:#ffffff"),
        ("dialog.body", "bg:#000000 fg:#ffffff"),
        ("dialog.title", "bg:#000000 fg:#ffffff bold"),
        ("checkbox", "fg:#00ff00"),
        ("checkbox.selected", "fg:#00ff00"),
        ("button", "bg:#000000 fg:#ffffff"),
        ("button.focused", "bg:#00aa00 fg:#000000 bold"),
        ("label", "bg:#000000 fg:#aaaaaa"),
        ("text-area", "bg:#000000 fg:#ffffff"),
    ])

    cb_list = CheckboxList(values=values, default_values=todos_los_valores)
    _all_selected = [todos_los_valores, []]

    def _cancel_handler():
        get_app().exit()

    dialog = Dialog(
        title="Seleccionar canciones",
        body=HSplit([
            Label("← pág ant  [Espacio] ✓  [a] todo/nada  [↑↓] navega  [Enter] OK  Cancel → más  → pág sig"),
            cb_list,
        ]),
        buttons=[
            Button("OK", handler=lambda: get_app().exit(result=list(cb_list.current_values))),
            Button("Cancel", handler=_cancel_handler),
        ],
        with_background=True,
    )

    bindings = KeyBindings()
    bindings.add("tab")(focus_next)
    bindings.add("s-tab")(focus_previous)

    @bindings.add("right")
    def _next(event):
        get_app().exit(result="__next__")

    @bindings.add("left")
    def _prev(event):
        get_app().exit(result="__prev__")

    @bindings.add("a")
    def _toggle_all(event):
        _all_selected.reverse()
        cb_list.current_values = _all_selected[0].copy()

    app = Application(
        layout=Layout(dialog),
        key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
        mouse_support=True,
        style=style,
        full_screen=True,
    )

    result = app.run()

    if result == "__next__":
        return [], "more"
    if result == "__prev__":
        return [], "prev"
    if result is None:
        return [], "none"
    return [int(v) for v in result], ("confirm" if result else "none")


def modo_agregar(archivo: str, salida: str = "", max_workers: int = 3) -> None:
    print("Modo interactivo — busca canciones y las descarga directamente")
    print("Usa ! al inicio para buscar sin 'audio' (ej: !nombre canción)")
    print("Usa @ al inicio para buscar por artista (ej: @Queen)")
    print("Pega una URL de playlist o usa /URL para descargar una playlist")
    print("Deja el nombre vacío y presiona Enter para salir.\n")

    if not salida:
        salida = str(Path("downloads") / date.today().isoformat())

    Path(salida).mkdir(parents=True, exist_ok=True)
    descargadas = {e["url"] for e in load_downloads() if e.get("url")}

    try:
        while True:
            query = _pt_prompt(
                HTML("<ansigreen>Canción:</ansigreen> "),
                completer=_YTCompleter(),
                complete_while_typing=True,
                complete_in_thread=True,
            ).strip()
            if not query:
                print("Saliendo.\n")
                break

            artist_mode = query.startswith("@")
            raw_mode = query.startswith("!")
            busqueda = query[1:] if (artist_mode or raw_mode) else query

            playlist_url_str = query[1:] if query.startswith("/") else query
            if is_playlist_url(playlist_url_str):
                stop_spinner = _spinner("Cargando playlist...")
                try:
                    opts = {"quiet": True, "extract_flat": True, "ignoreerrors": True}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(playlist_url_str, download=False)
                finally:
                    stop_spinner()

                entries = [e for e in (info.get("entries") if info else []) if e]
                if not entries:
                    print("  La playlist está vacía o no es accesible.\n")
                    continue

                playlist_title = info.get("title", "Playlist")
                print(f"  Playlist: {playlist_title} ({len(entries)} videos)")

                indices, action = _checkbox_seleccion(entries, 1, descargadas)
                if action in ("more", "prev"):
                    print("  Navegación no soportada en playlists.\n")
                    continue
                if action == "none" or not indices:
                    print("  Omitida\n")
                    continue

                lote = [
                    DownloadJob(
                        url=e.get("webpage_url") or f"https://youtube.com/watch?v={e.get('id', '')}",
                        salida=salida,
                        query=e.get("title", "?"),
                        titulo=e.get("title", "?"),
                        channel=e.get("channel") or e.get("uploader", "?"),
                    )
                    for idx in indices
                    for e in [entries[idx - 1]]
                ]
                for job in lote:
                    tqdm_write(f"  → {job.titulo}  |  {job.channel}")
                download_batch(lote, max_workers, descargadas)
                continue

            PAGE = 5
            page_num = 0
            entries: list = []
            artist_folder = ""

            if artist_mode:
                entries = []
                artist_name = sanitize_filename(busqueda)
                artist_folder = str(Path(salida).parent / artist_name)
                PAGE = 50

            try:
                while True:
                    total_wanted = (page_num + 1) * PAGE
                    inicio = page_num * PAGE + 1
                    fin = (page_num + 1) * PAGE
                    if artist_mode:
                        consulta = f"ytsearch{total_wanted}:{busqueda}"
                    else:
                        consulta = f"ytsearch{total_wanted}:{busqueda}" + ("" if raw_mode else " audio")

                    stop_spinner = _spinner("Buscando...")
                    try:
                        opts = {"quiet": True, "no_warnings": True, "ignoreerrors": True, "extract_flat": True, "playliststart": inicio, "playlistend": fin}
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(consulta, download=False)
                    finally:
                        stop_spinner()

                    page = [e for e in (info.get("entries") if info else []) if e]
                    for e in page:
                        if not e.get("webpage_url"):
                            e["webpage_url"] = e.get("url", f"https://www.youtube.com/watch?v={e.get('id', '')}")
                    if not page:
                        print("  Sin más resultados.\n")
                        break

                    cols = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
                    for j, e in enumerate(page, inicio):
                        titulo = e.get("title", "?")
                        channel = e.get("channel") or e.get("uploader", "?")
                        duration = int(e.get("duration", 0) or 0)
                        m, s = divmod(duration, 60)
                        dur_str = f"{m}:{s:02d}"
                        max_chan = 20
                        chan_show = channel[:max_chan - 1] + "\u2026" if len(channel) > max_chan else channel
                        max_tit = cols - len(f"  {j:>2}.   {chan_show}  {dur_str}") - 4
                        tit_show = titulo[:max_tit - 1] + "\u2026" if len(titulo) > max_tit else titulo
                        print(f"  {j:>2}. {tit_show:<{max_tit}}  {chan_show}  {dur_str}")

                    indices, action = _checkbox_seleccion(page, inicio, descargadas)

                    if action == "more":
                        page_num += 1
                        continue

                    if action == "prev":
                        if page_num > 0:
                            page_num -= 1
                        continue

                    if action == "none" or not indices:
                        print("  Omitida\n")
                        break

                    if artist_mode:
                        for idx in indices:
                            e = page[idx - inicio]
                            if e not in entries:
                                entries.append(e)
                        print(f"  {len(indices)} seleccionada(s).\n")
                        resp = input("  ¿Buscar más canciones? (s/N): ").strip().lower()
                        if resp in ("s", "si", "y", "yes"):
                            page_num += 1
                            continue
                        break

                    for idx in indices:
                        entries.append(page[idx - inicio])
                    break

                if not entries:
                    print("  Omitida\n")
                    continue

                if artist_mode:
                    Path(artist_folder).mkdir(parents=True, exist_ok=True)
                    lote = [
                        DownloadJob(
                            url=e.get("webpage_url", ""),
                            salida=artist_folder,
                            query=e.get("title", "?"),
                            titulo=e.get("title", "?"),
                            channel=e.get("channel") or e.get("uploader", "?"),
                        )
                        for e in entries
                    ]
                    for job in lote:
                        tqdm_write(f"  → {job.titulo}")
                    d, t, e = download_batch(lote, max_workers, descargadas)
                    tqdm_write(f"  \u2713 {d}/{t} canciones en {e:.0f}s\n")
                else:
                    lote = [
                        DownloadJob(
                            url=e.get("webpage_url", ""),
                            salida=salida,
                            query=e.get("title", "?"),
                            titulo=e.get("title", "?"),
                            channel=e.get("channel") or e.get("uploader", "?"),
                        )
                        for e in entries
                    ]
                    for job in lote:
                        tqdm_write(f"  → {job.titulo}  |  {job.channel}")
                    d, t, e = download_batch(lote, max_workers, descargadas)
                    tqdm_write(f"  \u2713 {d}/{t} canciones en {e:.0f}s\n")

            except Exception as e:
                print(f"  Error: {e}\n")

    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.\n")
