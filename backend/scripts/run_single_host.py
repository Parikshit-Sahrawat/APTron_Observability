"""Supervise existing API/monitoring processes in one candidate engine container.

No migration, enrollment, critical-event listener, receipt or reconciliation is
started here. Unexpected exit of either child stops the pair for Compose restart.
"""

import signal
import subprocess
import sys
import time


def supervise(commands, *, shutdown_timeout=20, poll_interval=0.1):
    stopping = False
    children = []
    previous = {}

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    def interrupt(child, signum):
        # Each child owns a session, so its subprocesses receive shutdown too.
        import os

        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, request_stop)
        for command in commands:
            if stopping:
                break
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("Engine child exited; stopping engine pair", file=sys.stderr)
                return 1
            time.sleep(poll_interval)
        return 0
    except OSError:
        # Do not print command arguments, environment or credentials.
        print("Unable to start engine child", file=sys.stderr)
        return 1
    finally:
        # asyncio.run handles SIGINT cancellation; uvicorn also handles SIGINT.
        for child in children:
            interrupt(child, signal.SIGINT)
        deadline = time.monotonic() + shutdown_timeout
        while any(child.poll() is None for child in children):
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_interval)
        for child in children:
            # Also clean remaining descendants of a child which already exited.
            interrupt(child, signal.SIGKILL)
            child.wait()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main():
    # The worker must not race API startup's production role check.
    from app.security.deployment import validate_runtime_database_role

    validate_runtime_database_role()
    return supervise(
        [
            [sys.executable, "-m", "scripts.run_api"],
            [sys.executable, "-m", "scripts.run_collector_worker"],
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
