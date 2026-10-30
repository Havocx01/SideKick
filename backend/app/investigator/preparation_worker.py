import os
from pathlib import Path
import sys
import threading
import time

PARENT_TIMEOUT = 5
MAX_SECONDS = 120
STAGES = ("generating", "training", "calibrating", "checking")


def watchParent(directory, *, timeout=PARENT_TIMEOUT, lifetime=MAX_SECONDS):
    started = time.monotonic()
    while True:
        time.sleep(.2)
        try:
            alive = time.time() - (directory / "heartbeat").stat().st_mtime < timeout
        except OSError:
            alive = False
        if not alive or time.monotonic() - started > lifetime:
            os._exit(2)


def main():
    directory = Path(sys.argv[1])
    threading.Thread(target=watchParent, args=(directory,), daemon=True).start()
    from app.faults.preparation import prepareSynthetic
    def progress(stage):
        (directory / f"stage-{stage}").touch()
    prepareSynthetic(directory / "context", profile="synthetic-rotating-v1", progress=progress)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
