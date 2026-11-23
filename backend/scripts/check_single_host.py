"""Local engine health: API plus an independently DB-checked worker heartbeat."""

import math
import os
from pathlib import Path
import time
from urllib.request import urlopen


def heartbeat_fresh(path, *, now=None, max_age=30):
    try:
        age = (time.time() if now is None else now) - float(Path(path).read_text())
        return math.isfinite(age) and 0 <= age <= max_age
    except (OSError, ValueError):
        return False


def main():
    if not heartbeat_fresh(os.environ["OPSCONTROL_WORKER_HEARTBEAT"]):
        return 1
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
            return 0 if response.status == 200 else 1
    except OSError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
