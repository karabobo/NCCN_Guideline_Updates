from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

import httpx
import yaml
from bs4 import BeautifulSoup

from .config import Settings
from .models import Guideline
from .naming import slugify

LOGGER = logging.getLogger(__name__)
NCCN_ROOT = "https://www.nccn.org"

VARIANT_LABELS = {
    "primary": "nccn guidelines",
    "evidence_blocks": "nccn guidelines with evidence blocks",
    "basic_framework": "basic framework",
    "core_framework": "core framework",
    "enhanced_framework": "enhanced framework",
    "patient": "patient",
    "harmonized": "harmonized",
}


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def _variant_for_link(text: str, href: str) -> str | None:
    normalized = text.lower().strip()
    href_lower = href.lower()
    if normalized == VARIANT_LABELS["primary"]:
        return "primary"
    if normalized == VARIANT_LABELS["evidence_blocks"] or href_lower.endswith("_blocks.pdf"):
        return "evidence_blocks"
    if normalized.startswith(VARIANT_LABELS["basic_framework"]) or href_lower.endswith("_basic.pdf"):
        return "basic_framework"
    if normalized.startswith(VARIANT_LABELS["core_framework"]) or href_lower.endswith("_core.pdf"):
        return "core_framework"
    if normalized.startswith(VARIANT_LABELS["enhanced_framework"]) or href_lower.endswith("_enhanced.pdf"):
        return "enhanced_framework"
    if "patient" in href_lower:
        return "patient"
    if "harmonized" in href_lower:
        return "harmonized"
    return None


async def _find_guideline_links(
    client: httpx.AsyncClient,
    url: str,
    variants: set[str],
) -> tuple[str, list[tuple[str, str, str]]]:
    html = await _fetch_text(client, url)
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_detail_title(soup, url)
    links: list[tuple[str, str, str]] = []
    for element in soup.find_all("a"):
        text = element.get_text(" ", strip=True).lower()
        href = element.get("href")
        if not href or ".pdf" not in href.lower():
            continue
        variant = _variant_for_link(text, href)
        if not variant:
            continue
        if "all" not in variants and variant not in variants:
            continue
        links.append((variant, element.get_text(" ", strip=True), urljoin(url, href)))
    return title, links


def _extract_detail_title(soup: BeautifulSoup, url: str) -> str:
    for selector in ("h3", "meta[property='og:title']", "title"):
        element = soup.select_one(selector)
        if not element:
            continue
        text = element.get("content") if element.name == "meta" else element.get_text(" ", strip=True)
        if text and text.lower() not in {"guidelines detail", "nccn guidelines"}:
            return text.strip()
    return url


def _category_from_detail_url(url: str) -> str:
    if "category=1" in url:
        return "Treatment by Cancer Type"
    if "category=2" in url:
        return "Detection, Prevention, and Risk Reduction"
    if "category=3" in url:
        return "Supportive Care"
    if "category=4" in url:
        return "Specific Populations"
    return ""


async def _build_guidelines_from_detail(
    client: httpx.AsyncClient,
    detail_url: str,
    category: str,
    variants: set[str],
) -> list[Guideline]:
    title, guideline_links = await _find_guideline_links(client, detail_url, variants)
    guidelines: list[Guideline] = []
    for variant, label, guideline_url in guideline_links:
        base_slug = slugify(title)
        slug = base_slug if variant == "primary" else f"{base_slug}-{variant}"
        guidelines.append(
            Guideline(
                title=title,
                slug=slug,
                url=guideline_url,
                category=category,
                variant=variant,
                label=label,
                detail_url=detail_url,
            )
        )
    return guidelines


async def _scrape_category(
    client: httpx.AsyncClient,
    category_number: int,
    semaphore: asyncio.Semaphore,
    settings: Settings,
) -> list[Guideline]:
    category_url = f"{NCCN_ROOT}/guidelines/category_{category_number}"
    html = await _fetch_text(client, category_url)
    soup = BeautifulSoup(html, "html.parser")
    category_title = soup.find("title").get_text(" ", strip=True) if soup.find("title") else f"Category {category_number}"
    item_links: list[tuple[str, str]] = []

    for item in soup.find_all("div", class_="item-name"):
        anchor = item.find("a")
        if not anchor or not anchor.get("href"):
            continue
        title = anchor.get_text(" ", strip=True)
        item_links.append((title, urljoin(category_url, anchor["href"])))

    if settings.detail_limit:
        item_links = item_links[: settings.detail_limit]

    async def build_guideline(title: str, detail_url: str) -> list[Guideline]:
        async with semaphore:
            return await _build_guidelines_from_detail(
                client,
                detail_url,
                category_title,
                settings.pdf_variants,
            )

    results = await asyncio.gather(
        *(build_guideline(title, detail_url) for title, detail_url in item_links),
        return_exceptions=True,
    )
    guidelines: list[Guideline] = []
    for result in results:
        if isinstance(result, Exception):
            LOGGER.warning("Failed to read guideline detail page: %s", result)
        else:
            guidelines.extend(result)
    return guidelines


async def build_public_index(settings: Settings) -> list[Guideline]:
    headers = {
        "User-Agent": "NCCN-Archiver/0.1 (+local authorized archival use)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(30.0, connect=15.0)
    limits = httpx.Limits(max_connections=settings.max_concurrency + 2)
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
    ) as client:
        if settings.detail_urls:
            results = await asyncio.gather(
                *(
                    _build_guidelines_from_detail(
                        client,
                        detail_url,
                        _category_from_detail_url(detail_url),
                        settings.pdf_variants,
                    )
                    for detail_url in settings.detail_urls
                ),
                return_exceptions=True,
            )
        else:
            results = await asyncio.gather(
                *(_scrape_category(client, category, semaphore, settings) for category in settings.categories),
                return_exceptions=True,
            )
    guidelines: list[Guideline] = []
    for result in results:
        if isinstance(result, Exception):
            LOGGER.warning("Failed to scrape one category: %s", result)
        else:
            guidelines.extend(result)
    return guidelines


def filter_guidelines(settings: Settings, guidelines: list[Guideline]) -> list[Guideline]:
    filtered: list[Guideline] = []
    for guideline in guidelines:
        if settings.include_slugs and guideline.slug not in settings.include_slugs:
            continue
        if guideline.slug in settings.exclude_slugs:
            continue
        filtered.append(guideline)
    if settings.limit:
        return filtered[: settings.limit]
    return filtered


def save_index(path, guidelines: list[Guideline]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "nccn_guidelines": [
            {
                "title": guideline.title,
                "slug": guideline.slug,
                "url": guideline.url,
                "category": guideline.category,
                "variant": guideline.variant,
                "label": guideline.label,
                "detail_url": guideline.detail_url,
                "version": guideline.version,
                "updated_at": guideline.updated_at,
            }
            for guideline in guidelines
        ]
    }
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
