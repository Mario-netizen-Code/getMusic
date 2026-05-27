import argparse
from datetime import date
from pathlib import Path

from tui_app import MusicApp


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
        type=int, default=3,
        help="Descargas concurrentes (default: 3)",
    )
    args = parser.parse_args()

    salida = str(Path(args.output) / date.today().isoformat())
    MusicApp(salida=salida, max_workers=args.jobs).run()


if __name__ == "__main__":
    main()
