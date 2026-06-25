from __future__ import annotations

import argparse
import asyncio
import logging
import time

from dotenv import load_dotenv

from .config import Settings
from .notify import build_test_summary, notify_run
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
    parser.add_argument(
        "--notify-test",
        action="store_true",
        help="Send a test notification and exit.",
    )
    return parser


async def _run_once_and_notify(settings: Settings, dry_run: bool, index_only: bool):
    summary = await run_once(settings, dry_run=dry_run, index_only=index_only)
    if not dry_run and not index_only:
        await notify_run(settings, summary)
    return summary


async def _run_daemon(settings: Settings, dry_run: bool, index_only: bool) -> None:
    while True:
        await _run_once_and_notify(settings, dry_run=dry_run, index_only=index_only)
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

    if args.notify_test:
        asyncio.run(notify_run(settings, build_test_summary(settings)))
        return 0

    start = time.time()
    if args.daemon:
        asyncio.run(_run_daemon(settings, dry_run=args.dry_run, index_only=args.index_only))
    else:
        summary = asyncio.run(
            _run_once_and_notify(settings, dry_run=args.dry_run, index_only=args.index_only)
        )
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
