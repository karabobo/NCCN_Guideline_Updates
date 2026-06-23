from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .models import DownloadedFile, Guideline

LOGGER = logging.getLogger(__name__)


class NCCNClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._logged_in = False
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "NCCN-Archiver/0.1 (+local authorized archival use)",
                "Accept-Language": "en-US,en;q=0.9",
                **({"Cookie": settings.cookie_header} if settings.cookie_header else {}),
            },
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=20.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "NCCNClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def login(self, target_url: str) -> bool:
        if self._logged_in:
            return True
        if not self.settings.has_login_config:
            return False

        response = await self._client.get(target_url)
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form", {"action": "/login/Index/"}) or soup.find("form")
        if not form:
            LOGGER.error("NCCN login form was not found")
            return False

        form_data: dict[str, str] = {}
        for field in form.find_all("input"):
            name = field.get("name")
            if not name:
                continue
            form_data[name] = field.get("value", "")
        form_data.update(
            {
                "Username": self.settings.username,
                "Password": self.settings.password,
                "RememberMe": "false",
            }
        )
        if "Email" in form_data:
            form_data["Email"] = self.settings.username
        if "UserName" in form_data:
            form_data["UserName"] = self.settings.username

        action = form.get("action") or "/login/Index/"
        login_url = urljoin("https://www.nccn.org", action)
        login_response = await self._client.post(
            login_url,
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": str(response.url),
                "Origin": "https://www.nccn.org",
            },
        )
        if "/login" in str(login_response.url).lower() or "log in" in login_response.text.lower():
            LOGGER.error("NCCN login failed")
            return False
        self._logged_in = True
        return True

    async def download(self, guideline: Guideline) -> DownloadedFile:
        await asyncio.sleep(self.settings.request_delay_seconds)
        url = self._resolve_download_url(guideline)
        response = await self._client.get(
            url,
            headers={
                "Accept": "application/pdf,*/*",
                "Referer": "https://www.nccn.org/",
            },
        )
        if self._looks_like_login(response):
            LOGGER.info("Login required for %s", guideline.title)
            if not await self.login(url):
                raise PermissionError(
                    "NCCN login is required. Set NCCN_USERNAME and NCCN_PASSWORD, "
                    "or provide NCCN_COOKIE from your own active browser session."
                )
            response = await self._client.get(url, headers={"Accept": "application/pdf,*/*"})

        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not self._is_pdf(response, content_type):
            raise ValueError(f"Expected PDF for {guideline.title}, got {content_type or 'unknown content type'}")
        if len(response.content) < self.settings.min_pdf_bytes:
            raise ValueError(
                f"PDF for {guideline.title} is unexpectedly small "
                f"({len(response.content)} bytes)"
            )
        return DownloadedFile(
            guideline=guideline,
            content=response.content,
            content_type=content_type,
            source_url=str(response.url),
        )

    def _resolve_download_url(self, guideline: Guideline) -> str:
        if guideline.url:
            return guideline.url
        raise ValueError(f"No download URL for {guideline.title}")

    @staticmethod
    def _looks_like_login(response: httpx.Response) -> bool:
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return False
        text = response.text.lower()
        return "/login" in str(response.url).lower() or "log in" in text or "login" in text

    @staticmethod
    def _is_pdf(response: httpx.Response, content_type: str) -> bool:
        return "application/pdf" in content_type.lower() or response.content.startswith(b"%PDF")
