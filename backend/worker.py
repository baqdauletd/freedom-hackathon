from __future__ import annotations

import argparse

from backend.core.config import get_settings
from backend.core.logging import configure_logging
from backend.services.worker import run_worker_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="FIRE background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available job and exit")
    parser.add_argument("--max-jobs", type=int, default=None, help="Process up to N jobs and exit")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    processed = run_worker_loop(once=args.once, max_jobs=args.max_jobs)
    print(f"Processed jobs: {processed}")


if __name__ == "__main__":
    main()
