"""Entrypoint: python server/run.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from jarvis.config import config  # noqa: E402


def main():
    srv = config.settings["server"]
    uvicorn.run("jarvis.app:app", host=srv["host"], port=srv["port"], log_level="info")


if __name__ == "__main__":
    main()
