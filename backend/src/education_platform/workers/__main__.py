"""Run the Postgres ingest worker: ``python -m education_platform.workers``."""

from __future__ import annotations

from education_platform.workers.runner import run_forever


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
