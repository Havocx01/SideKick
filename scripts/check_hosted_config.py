"""Refuse to start the private hosting image without its access boundary."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from app.config import get_settings


def main():
    settings = get_settings()
    if not settings.hosted or not settings.artifacts_dir.is_absolute() or not settings.data_dir.is_absolute():
        raise ValueError('The hosted image requires a configured owner, HTTPS origin, password hash and absolute storage directories')
    print('Private hosting configuration accepted. Mount persistent storage before starting the server.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
