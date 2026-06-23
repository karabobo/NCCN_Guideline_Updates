from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings
from .downloader import NCCNClient
from .fingerprint import PdfFingerprint, pdf_fingerprint
from .index import build_public_index, filter_guidelines, save_index
from .models import Guideline, RunSummary
from .naming import guideline_pdf_filename, slugify, version_token
from .state import load_state, save_state, utc_now_iso

LOGGER = logging.getLogger(__name__)


def _archive_paths(settings: Settings, guideline: Guideline, fingerprint: PdfFingerprint) -> tuple[Path, Path]:
    slug = slugify(guideline.slug or guideline.title)
    version = fingerprint.version or guideline.version or guideline.updated_at
    version_label = version_token(version, fingerprint.content_sha256)
    filename = guideline_pdf_filename(
        guideline.title,
        version,
        fingerprint.content_sha256,
        guideline.variant,
    )
    historical_path = settings.archive_dir / "guidelines" / slug / version_label / filename
    latest_path = settings.archive_dir / "latest" / filename
    return historical_path, latest_path


def _remove_previous_latest(previous: dict, latest_path: Path) -> None:
    previous_latest = previous.get("latest_path")
    if not previous_latest:
        return
    previous_path = Path(previous_latest)
    if previous_path == latest_path or not previous_path.exists():
        return
    try:
        previous_path.unlink()
    except OSError as exc:
        LOGGER.warning("Could not remove previous latest PDF %s: %s", previous_path, exc)


async def _get_index(settings: Settings) -> list[Guideline]:
    LOGGER.info("Building guideline index from public NCCN guideline pages")
    return await build_public_index(settings)


async def run_once(
    settings: Settings,
    dry_run: bool = False,
    index_only: bool = False,
) -> RunSummary:
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(settings.state_file)
    guidelines = filter_guidelines(settings, await _get_index(settings))
    save_index(settings.index_file, guidelines)
    LOGGER.info("Index contains %s guideline(s)", len(guidelines))
    if index_only:
        return RunSummary(checked=len(guidelines), updated=0, skipped=0, failed=0)

    checked = updated = skipped = failed = 0
    async with NCCNClient(settings) as client:
        for guideline in guidelines:
            checked += 1
            try:
                downloaded = await client.download(guideline)
                fingerprint = pdf_fingerprint(downloaded.content)
                previous = state["guidelines"].get(guideline.slug, {})
                if previous.get("content_sha256") == fingerprint.content_sha256:
                    skipped += 1
                    LOGGER.info("Unchanged: %s", guideline.title)
                    continue

                historical_path, latest_path = _archive_paths(settings, guideline, fingerprint)
                if dry_run:
                    updated += 1
                    LOGGER.info("Would archive update: %s", guideline.title)
                    continue

                historical_path.parent.mkdir(parents=True, exist_ok=True)
                latest_path.parent.mkdir(parents=True, exist_ok=True)
                historical_path.write_bytes(downloaded.content)
                latest_path.write_bytes(downloaded.content)
                _remove_previous_latest(previous, latest_path)

                version = fingerprint.version or guideline.version
                state["guidelines"][guideline.slug] = {
                    "title": guideline.title,
                    "slug": guideline.slug,
                    "category": guideline.category,
                    "variant": guideline.variant,
                    "label": guideline.label,
                    "detail_url": guideline.detail_url,
                    "version": version or "",
                    "pdf_version": fingerprint.version or "",
                    "updated_at": guideline.updated_at,
                    "source_url": downloaded.source_url,
                    "sha256": fingerprint.byte_sha256,
                    "byte_sha256": fingerprint.byte_sha256,
                    "content_sha256": fingerprint.content_sha256,
                    "fingerprint_method": fingerprint.method,
                    "page_count": fingerprint.page_count,
                    "bytes": len(downloaded.content),
                    "archived_at": utc_now_iso(),
                    "historical_path": str(historical_path),
                    "latest_path": str(latest_path),
                }
                save_state(settings.state_file, state)
                updated += 1
                LOGGER.info("Archived: %s", guideline.title)
            except Exception as exc:
                failed += 1
                LOGGER.error("Failed: %s - %s", guideline.title, exc)

    return RunSummary(checked=checked, updated=updated, skipped=skipped, failed=failed)
