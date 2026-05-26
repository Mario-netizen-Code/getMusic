import argparse
import base64
import hashlib
import itertools
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import date, datetime
from pathlib import Path
from threading import Event, Thread
from typing import NamedTuple

import yt_dlp
from cryptography.fernet import Fernet, InvalidToken
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
from tqdm import tqdm


class _DownloadJob(NamedTuple):
    url: str
    salida: str
    query: str
    titulo: str
    channel: str


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

def _write(*args, **kwargs):
    kwargs.setdefault("file", sys.stdout)
    tqdm.write(*args, **kwargs)


def _nombre_archivo_valido(nombre: str) -> str:
    nombre = re.sub(r'[<>:"/\\|?*]', "_", nombre)
    nombre = nombre.replace("\0", "")
    nombre = nombre.strip(". ")
    return nombre


_HISTORIAL_PATH = Path(__file__).parent / "search_history.dat"


def _clave_fernet() -> bytes:
    material = f"{os.environ.get('USERNAME','')}-{os.environ.get('COMPUTERNAME','')}"
    return base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())


def _cargar_historial() -> list[dict]:
    if not _HISTORIAL_PATH.is_file():
        return []
    try:
        raw = _HISTORIAL_PATH.read_bytes()
        if not raw:
            return []
        clave = _clave_fernet()
        descifrado = Fernet(clave).decrypt(raw)
        data = json.loads(descifrado.decode("utf-8"))
        return data if isinstance(data, list) else []
    except (InvalidToken, Exception):
        return []


def _guardar_historial(entries: list[dict]) -> None:
    clave = _clave_fernet()
    cifrado = Fernet(clave).encrypt(json.dumps(entries).encode("utf-8"))
    _HISTORIAL_PATH.write_bytes(cifrado)


def _historial_sugerencias(query: str) -> list[str]:
    query_lower = query.lower()
    result = []
    for e in _cargar_historial():
        q = e.get("query", "")
        if query_lower in q.lower():
            result.append(q)
    return result


def _registrar_busqueda(query: str) -> None:
    if not query.strip():
        return
    entries = _cargar_historial()
    now = date.today().isoformat()
    for e in entries:
        if e["query"].lower() == query.lower():
            e["count"] = e.get("count", 0) + 1
            e["last_download"] = now
            break
    else:
        entries.append({"query": query, "count": 1, "last_download": now})
    _guardar_historial(entries)


_DOWNLOAD_HISTORY_PATH = Path(__file__).parent / "download_history.dat"


_descargas_cache: list[dict] | None = None


def _cargar_descargas() -> list[dict]:
    global _descargas_cache
    if _descargas_cache is not None:
        return _descargas_cache
    if not _DOWNLOAD_HISTORY_PATH.is_file():
        _descargas_cache = []
        return _descargas_cache
    try:
        raw = _DOWNLOAD_HISTORY_PATH.read_bytes()
        if not raw:
            _descargas_cache = []
            return _descargas_cache
        clave = _clave_fernet()
        descifrado = Fernet(clave).decrypt(raw)
        data = json.loads(descifrado.decode("utf-8"))
        _descargas_cache = data if isinstance(data, list) else []
        return _descargas_cache
    except (InvalidToken, Exception):
        _descargas_cache = []
        return _descargas_cache


def _guardar_descargas(entries: list[dict]) -> None:
    global _descargas_cache
    _descargas_cache = entries
    clave = _clave_fernet()
    cifrado = Fernet(clave).encrypt(json.dumps(entries).encode("utf-8"))
    _DOWNLOAD_HISTORY_PATH.write_bytes(cifrado)


def _registrar_descarga(url: str, titulo: str, channel: str, query: str) -> None:
    if not url:
        return
    entries = _cargar_descargas()
    now = datetime.now().isoformat()
    for e in entries:
        if e["url"] == url:
            e["count"] = e.get("count", 0) + 1
            e["last_download"] = now
            break
    else:
        entries.append({
            "url": url,
            "title": titulo,
            "channel": channel,
            "query": query,
            "downloaded_at": now,
            "count": 1,
        })
    _guardar_descargas(entries)


def leer_urls(ruta: str) -> list[str]:
    urls: list[str] = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            stripped = linea.strip()
            if not stripped or stripped.startswith("#"):
                continue
            urls.append(stripped)
    return urls


def descargar_mp3(url: str, salida: str, progress_callback=None) -> str:
    salida_path = Path(salida)

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        raw_title = info.get("title", url)

    max_stem = 100
    stem = _nombre_archivo_valido(raw_title)
    if len(stem) > max_stem:
        stem = stem[:max_stem].rstrip(". ")

    safe_stem = stem.replace("%", "%%")
    nombre_base = f"{safe_stem}.%(ext)s"

    hooks = [progress_callback] if progress_callback else []

    opciones = {
        "format": "bestaudio/best",
        "outtmpl": str(salida_path / nombre_base),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            },
            {"key": "FFmpegMetadata"},
        ],
        "postprocessor_args": ["-ab", "320k"],
        "prefer_ffmpeg": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": hooks,
    }

    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url])

    return url


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
        for s in _historial_sugerencias(query):
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


def _descargar_lote(jobs: list[_DownloadJob], max_workers: int = 3, descargadas: set[str] | None = None) -> tuple[int, int, float]:
    total = len(jobs)
    done = 0
    start_time = time.time()
    ncols = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
    _write("")
    with tqdm(total=total, desc="Progreso", unit="archivo", ncols=ncols, file=sys.stdout) as pbar:
        def _hook(job):
            def _progreso(d):
                if d["status"] == "downloading":
                    pct = d.get("_percent_str", "").strip()
                    pbar.set_postfix_str(f"{job.titulo[:40]} {pct}")
                elif d["status"] == "finished":
                    pbar.set_postfix_str(f"{job.titulo[:40]} - convirtiendo...")
            return _progreso

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futuros = {}
            for job in jobs:
                futuros[executor.submit(descargar_mp3, job.url, job.salida, _hook(job))] = job
            pending = set(futuros.keys())
            try:
                while pending:
                    done_set, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for futuro in done_set:
                        job = futuros[futuro]
                        done += 1
                        try:
                            futuro.result()
                            _registrar_busqueda(job.query)
                            _registrar_descarga(job.url, job.titulo, job.channel, job.query)
                            if descargadas is not None:
                                descargadas.add(job.url)
                            pbar.set_postfix_str(job.titulo[:40])
                        except Exception as e:
                            pbar.set_postfix_str(f"Error: {job.titulo[:30]}")
                        pbar.update(1)
            except KeyboardInterrupt:
                _write("\n  Interrumpiendo descargas restantes...")
                for f in pending:
                    f.cancel()
                raise
    elapsed = time.time() - start_time
    return done, total, elapsed


def modo_agregar(archivo: str, salida: str = "", max_workers: int = 3) -> None:
    print("Modo interactivo — busca canciones y las descarga directamente")
    print("Usa ! al inicio para buscar sin 'audio' (ej: !nombre canción)")
    print("Usa @ al inicio para buscar por artista (ej: @Queen)")
    print("Pega una URL de playlist o usa /URL para descargar una playlist")
    print("Deja el nombre vacío y presiona Enter para salir.\n")

    if not salida:
        salida = str(Path("downloads") / date.today().isoformat())

    Path(salida).mkdir(parents=True, exist_ok=True)
    descargadas = {e["url"] for e in _cargar_descargas() if e.get("url")}

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
            if _es_url_playlist(playlist_url_str):
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
                    _DownloadJob(
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
                    _write(f"  → {job.titulo}  |  {job.channel}")
                _descargar_lote(lote, max_workers, descargadas)
                continue

            PAGE = 5
            page_num = 0
            entries: list = []
            artist_folder = ""

            if artist_mode:
                entries = []
                artist_name = _nombre_archivo_valido(busqueda)
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
                        _DownloadJob(
                            url=e.get("webpage_url", ""),
                            salida=artist_folder,
                            query=e.get("title", "?"),
                            titulo=e.get("title", "?"),
                            channel=e.get("channel") or e.get("uploader", "?"),
                        )
                        for e in entries
                    ]
                    for job in lote:
                        _write(f"  → {job.titulo}")
                    d, t, e = _descargar_lote(lote, max_workers, descargadas)
                    _write(f"  \u2713 {d}/{t} canciones en {e:.0f}s\n")
                else:
                    lote = [
                        _DownloadJob(
                            url=e.get("webpage_url", ""),
                            salida=salida,
                            query=e.get("title", "?"),
                            titulo=e.get("title", "?"),
                            channel=e.get("channel") or e.get("uploader", "?"),
                        )
                        for e in entries
                    ]
                    for job in lote:
                        _write(f"  → {job.titulo}  |  {job.channel}")
                    d, t, e = _descargar_lote(lote, max_workers, descargadas)
                    _write(f"  \u2713 {d}/{t} canciones en {e:.0f}s\n")

            except Exception as e:
                print(f"  Error: {e}\n")

    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.\n")


def validar_urls(urls: list[str]) -> list[str]:
    patron = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/"
    )
    return [u for u in urls if patron.match(u)]


def _es_url_playlist(text: str) -> bool:
    return bool(re.match(
        r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.*(\?|&)list=",
        text,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descargar audio MP3 de YouTube desde un archivo de URLs"
    )
    parser.add_argument(
        "archivo",
        nargs="?",
        default="urls.txt",
        help="Ruta al archivo con URLs (default: urls.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="downloads",
        help="Directorio de salida (default: downloads)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=3,
        help="Descargas concurrentes (default: 3)",
    )
    parser.add_argument(
        "--add",
        action="store_true",
        help="Modo interactivo para buscar canciones y descargarlas directamente",
    )
    parser.add_argument(
        "--skip-downloaded",
        action="store_true",
        help="Omitir URLs ya descargadas (revisa download_history.dat)",
    )
    args = parser.parse_args()

    archivo = args.archivo
    salida = str(Path(args.output) / date.today().isoformat())
    max_workers = max(1, args.jobs)

    if args.add:
        modo_agregar(archivo, salida, max_workers)
        return

    if not os.path.isfile(archivo):
        print(f"Error: No se encuentra el archivo '{archivo}'")
        sys.exit(1)

    urls = leer_urls(archivo)
    if not urls:
        print("No se encontraron URLs en el archivo.")
        sys.exit(1)

    urls_validas = validar_urls(urls)
    invalidas = len(urls) - len(urls_validas)
    if invalidas:
        print(
            f"Advertencia: {invalidas} l\u00ednea(s) omitida(s) "
            f"por no ser URL v\u00e1lida de YouTube."
        )

    if not urls_validas:
        print("No hay URLs v\u00e1lidas de YouTube para procesar.")
        sys.exit(1)

    if args.skip_downloaded:
        previas = {e["url"] for e in _cargar_descargas() if e.get("url")}
        nuevas = [u for u in urls_validas if u not in previas]
        omitidas = len(urls_validas) - len(nuevas)
        if omitidas:
            print(f"  Omitidas {omitidas} URL(s) ya descargada(s).")
        urls_validas = nuevas
        if not urls_validas:
            print("  Todas las URLs ya fueron descargadas.\n\u00a1Proceso terminado!")
            return

    Path(salida).mkdir(parents=True, exist_ok=True)

    total = len(urls_validas)
    print(f"Procesando {total} video(s) con {max_workers} hilo(s)...\n")

    completados = 0
    start_time = time.time()
    ncols = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
    _write("")
    with tqdm(total=total, desc="Progreso", unit="archivo", ncols=ncols, file=sys.stdout) as pbar:
        def _batch_hook(url):
            def _progreso(d):
                if d["status"] == "downloading":
                    pct = d.get("_percent_str", "").strip()
                    pbar.set_postfix_str(f"{url.rsplit('/', 1)[-1][:35]} {pct}")
                elif d["status"] == "finished":
                    pbar.set_postfix_str(f"{url.rsplit('/', 1)[-1][:35]} - convirtiendo...")
            return _progreso

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futuros = {}
                for url in urls_validas:
                    futuros[executor.submit(descargar_mp3, url, salida, _batch_hook(url))] = url

                pending = set(futuros.keys())
                while pending:
                    done_set, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                    for futuro in done_set:
                        url = futuros[futuro]
                        completados += 1
                        try:
                            futuro.result()
                            _registrar_descarga(url, url, "", "")
                            pbar.set_postfix_str(url.rsplit("/", 1)[-1][:45])
                        except Exception as e:
                            pbar.set_postfix_str(f"Error: {url.rsplit('/', 1)[-1][:35]}")
                        pbar.update(1)
        except KeyboardInterrupt:
            print("\n  Interrumpido por el usuario.\n")
            sys.exit(130)

    elapsed = time.time() - start_time
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nuevo = f"{Path(archivo).stem}_{ts}{Path(archivo).suffix}"
    os.rename(archivo, nuevo)
    _write(f"  \u2713 {completados}/{total} en {elapsed:.0f}s")
    _write(f"  Archivo renombrado a: {nuevo}")
    _write("\n\u00a1Proceso terminado!")


if __name__ == "__main__":
    main()
