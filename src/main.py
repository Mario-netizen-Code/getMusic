import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

from downloader import download_batch
from models import DownloadJob
from storage import load_downloads, flush_store
from tui_app import MusicApp
from utils import tqdm_write


def leer_urls(ruta: str) -> list[str]:
    urls: list[str] = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            stripped = linea.strip()
            if not stripped or stripped.startswith("#"):
                continue
            urls.append(stripped)
    return urls


def validar_urls(urls: list[str]) -> list[str]:
    patron = re.compile(
        r"^(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/"
    )
    return [u for u in urls if patron.match(u)]


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
        help="Omitir URLs ya descargadas (revisa data/store.dat)",
    )
    args = parser.parse_args()

    archivo = args.archivo
    salida = str(Path(args.output) / date.today().isoformat())
    max_workers = max(1, args.jobs)

    if args.add:
        MusicApp(archivo=archivo, salida=salida, max_workers=max_workers).run()
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
        previas = {e["url"] for e in load_downloads() if e.get("url")}
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

    jobs = [DownloadJob(url=u, salida=salida, query="", titulo="", channel="") for u in urls_validas]

    try:
        done, total, elapsed = download_batch(jobs, max_workers)
        flush_store()
    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.\n")
        sys.exit(130)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nuevo = f"{Path(archivo).stem}_{ts}{Path(archivo).suffix}"
    os.rename(archivo, nuevo)
    tqdm_write(f"  \u2713 {done}/{total} en {elapsed:.0f}s")
    tqdm_write(f"  Archivo renombrado a: {nuevo}")
    tqdm_write("\n\u00a1Proceso terminado!")


if __name__ == "__main__":
    main()
