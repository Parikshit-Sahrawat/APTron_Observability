"""Local engine health: API plus an independently DB-checked worker heartbeat."""

import math
import json
import os
from pathlib import Path
import time
from urllib.request import urlopen
from urllib.error import HTTPError


def heartbeat_fresh(path, *, now=None, max_age=30):
    try:
        age = (time.time() if now is None else now) - float(Path(path).read_text())
        return math.isfinite(age) and 0 <= age <= max_age
    except (OSError, ValueError):
        return False


def api_ready(url="http://127.0.0.1:8000/health", *, production=True):
    # Production intentionally denies this untrusted plaintext loopback request.
    # Do not forge ingress headers or relax proxy trust to make health green.
    try:
        with urlopen(url, timeout=3) as response:
            return not production and response.status == 200
    except HTTPError as error:
        try:
            return (
                production
                and error.code == 403
                and json.load(error).get("detail") == "HTTPS required"
            )
        except (ValueError, AttributeError):
            return False
    except OSError:
        return False


def main():
    if not heartbeat_fresh(os.environ["OPSCONTROL_WORKER_HEARTBEAT"]):
        return 1
    return (
        0 if api_ready(production=os.environ.get("ENVIRONMENT") == "production") else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
