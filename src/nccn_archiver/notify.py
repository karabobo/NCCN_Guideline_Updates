from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any

from .config import Settings
from .models import ArchivedUpdate, FailedGuideline, RunSummary

LOGGER = logging.getLogger(__name__)
MAX_FEISHU_LINE_CHARS = 360


def feishu_sign(secret: str, timestamp: int | str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(string_to_sign, b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def should_notify(settings: Settings, summary: RunSummary) -> bool:
    notify_on = settings.notify_on or "changes"
    if notify_on in {"never", "none", "off", "false", "0"}:
        return False
    if notify_on == "always":
        return True
    return summary.updated > 0 or summary.failed > 0


def display_archive_path(settings: Settings, saved_path: str) -> str:
    if not settings.archive_host_dir:
        return saved_path

    path = Path(saved_path)
    try:
        relative_path = path.relative_to(settings.archive_dir)
    except ValueError:
        return saved_path
    return str(settings.archive_host_dir / relative_path)


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}..."


def _version_change(update: ArchivedUpdate) -> str:
    previous = update.previous_version or "new"
    current = update.version or "unknown"
    return f"{previous} -> {current}"


def _update_lines(settings: Settings, updates: tuple[ArchivedUpdate, ...]) -> list[str]:
    lines: list[str] = []
    for index, update in enumerate(updates[: settings.notify_max_items], start=1):
        latest_path = display_archive_path(settings, update.latest_path)
        line = f"{index}. {update.title} | {_version_change(update)} | {latest_path}"
        lines.append(_truncate(line, MAX_FEISHU_LINE_CHARS))
    omitted = len(updates) - settings.notify_max_items
    if omitted > 0:
        lines.append(f"... {omitted} more updated guideline(s) not shown")
    return lines


def _failure_lines(settings: Settings, failures: tuple[FailedGuideline, ...]) -> list[str]:
    lines: list[str] = []
    for index, failure in enumerate(failures[: settings.notify_max_items], start=1):
        line = f"{index}. {failure.title} | {_truncate(failure.error, 240)}"
        lines.append(_truncate(line, MAX_FEISHU_LINE_CHARS))
    omitted = len(failures) - settings.notify_max_items
    if omitted > 0:
        lines.append(f"... {omitted} more failed guideline(s) not shown")
    return lines


def _card_template(summary: RunSummary) -> str:
    if summary.failed:
        return "red"
    if summary.updated:
        return "green"
    return "blue"


def build_feishu_payload(
    settings: Settings,
    summary: RunSummary,
    timestamp: int | None = None,
) -> dict[str, Any]:
    title = f"{settings.notify_title}: {summary.updated} updated, {summary.failed} failed"
    stats = (
        f"Checked: **{summary.checked}**  "
        f"Updated: **{summary.updated}**  "
        f"Skipped: **{summary.skipped}**  "
        f"Failed: **{summary.failed}**"
    )

    elements: list[dict[str, Any]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": stats}},
    ]

    if summary.updates:
        elements.append({"tag": "hr"})
        updates_md = "\n".join(_update_lines(settings, summary.updates))
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**New or updated guidelines**\n{updates_md}",
                },
            }
        )

    if summary.failures:
        elements.append({"tag": "hr"})
        failures_md = "\n".join(_failure_lines(settings, summary.failures))
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**Failures**\n{failures_md}",
                },
            }
        )

    if not summary.updates and not summary.failures:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "No guideline changes detected."},
            }
        )

    payload: dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": _card_template(summary),
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": elements,
        },
    }

    if settings.feishu_secret:
        signed_timestamp = timestamp or int(time.time())
        payload["timestamp"] = str(signed_timestamp)
        payload["sign"] = feishu_sign(settings.feishu_secret, signed_timestamp)

    return payload


def build_test_summary(settings: Settings) -> RunSummary:
    latest_root = settings.archive_host_dir or settings.archive_dir
    latest_path = latest_root / "latest" / "NCCN_Test_Guideline_Version_1.2026.pdf"
    update = ArchivedUpdate(
        title="Test Guideline",
        slug="test-guideline",
        category="1",
        variant="primary",
        version="Version 1.2026",
        previous_version="",
        source_url="https://www.nccn.org/",
        detail_url="https://www.nccn.org/",
        historical_path=str(latest_path),
        latest_path=str(latest_path),
        bytes=0,
        page_count=None,
        content_sha256="test",
        archived_at="test",
    )
    return RunSummary(checked=1, updated=1, skipped=0, failed=0, updates=(update,))


async def send_feishu_notification(settings: Settings, summary: RunSummary) -> None:
    import httpx

    payload = build_feishu_payload(settings, summary)
    payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    if payload_size > 20_000:
        LOGGER.warning("Feishu notification payload is %s bytes and may be rejected", payload_size)

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(settings.feishu_webhook_url, json=payload)
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            body = {}
        if body.get("code", body.get("StatusCode", 0)) != 0:
            raise RuntimeError(f"Feishu webhook returned {body}")


async def notify_run(settings: Settings, summary: RunSummary) -> None:
    if not should_notify(settings, summary):
        return

    if not settings.notify_provider:
        return
    if settings.notify_provider != "feishu":
        LOGGER.warning("Unsupported notification provider: %s", settings.notify_provider)
        return
    if not settings.feishu_webhook_url:
        LOGGER.warning("Feishu notifications are enabled, but NCCN_FEISHU_WEBHOOK_URL is empty")
        return

    try:
        await send_feishu_notification(settings, summary)
        LOGGER.info("Sent Feishu notification")
    except Exception as exc:
        LOGGER.warning("Feishu notification failed: %s", exc)
