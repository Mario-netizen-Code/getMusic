import argparse
import os
from datetime import date
from pathlib import Path

from tui_app import MusicApp


def _default_jobs() -> int:
    return (os.cpu_count() or 1) + 2


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descargar audio MP3 de YouTube"
    )
    parser.add_argument(
        "-o", "--output",
        default="downloads",
        help="Directorio de salida (default: downloads)",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int, default=_default_jobs(),
        help=f"Descargas concurrentes (default: CPUs+2 = {_default_jobs()})",
    )
    args = parser.parse_args()

    salida = str(Path(args.output) / date.today().isoformat())
    MusicApp(salida=salida, max_workers=args.jobs).run()


if __name__ == "__main__":
    main()
