from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings
from .downloader import NCCNClient
from .fingerprint import PdfFingerprint, pdf_fingerprint
from .index import build_public_index, filter_guidelines, save_index
from .models import Guideline, RunSummary
from .naming import filename_from_url, slugify
from .state import load_state, save_state, utc_now_iso

LOGGER = logging.getLogger(__name__)


def _archive_paths(settings: Settings, guideline: Guideline, fingerprint: PdfFingerprint) -> tuple[Path, Path]:
    slug = slugify(guideline.slug or guideline.title)
    version_label = guideline.version or guideline.updated_at or fingerprint.content_sha256[:12]
    version_label = slugify(version_label, fingerprint.content_sha256[:12])
    filename = filename_from_url(guideline.url, slug)
    historical_path = settings.archive_dir / "guidelines" / slug / version_label / filename
    latest_path = settings.archive_dir / "latest" / f"{slug}.pdf"
    return historical_path, latest_path


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

                state["guidelines"][guideline.slug] = {
                    "title": guideline.title,
                    "slug": guideline.slug,
                    "category": guideline.category,
                    "variant": guideline.variant,
                    "label": guideline.label,
                    "detail_url": guideline.detail_url,
                    "version": guideline.version,
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
