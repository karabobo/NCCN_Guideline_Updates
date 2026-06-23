from __future__ import annotations

import argparse
import asyncio
import logging
import time

from dotenv import load_dotenv

from .config import Settings
from .runner import run_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and archive the latest NCCN Guidelines PDFs."
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run forever, sleeping between archive checks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the index and report planned downloads without saving PDFs.",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help="Only build archive/index.yaml; do not download PDFs.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Log verbosity.",
    )
    return parser


async def _run_daemon(settings: Settings, dry_run: bool, index_only: bool) -> None:
    while True:
        await run_once(settings, dry_run=dry_run, index_only=index_only)
        logging.info("Sleeping for %s hours", settings.run_interval_hours)
        await asyncio.sleep(settings.run_interval_hours * 60 * 60)


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    settings = Settings.from_env()

    start = time.time()
    if args.daemon:
        asyncio.run(_run_daemon(settings, dry_run=args.dry_run, index_only=args.index_only))
    else:
        summary = asyncio.run(run_once(settings, dry_run=args.dry_run, index_only=args.index_only))
        logging.info(
            "Done in %.1fs: %s checked, %s new/updated, %s skipped, %s failed",
            time.time() - start,
            summary.checked,
            summary.updated,
            summary.skipped,
            summary.failed,
        )
        if summary.failed:
            return 1
    return 0
