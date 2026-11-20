"""Bilibili web video search adapter using WBI request signing."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from aios_work_system.acquisition.models import ResourceCandidate, SearchPage, SearchRequest

_WBI_MIXIN_KEY_ENC_TAB = (46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52, 1)
_API = "https://api.bilibili.com"


def _mixin_key(img_key: str, sub_key: str) -> str:
    source = img_key + sub_key
    return "".join(source[index] for index in _WBI_MIXIN_KEY_ENC_TAB)[:32]


def _key_from_url(value: str) -> str:
    return urlparse(value).path.rsplit("/", 1)[-1].split(".", 1)[0]


def _duration_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parts = [int(part) for part in value.split(":")]
    except ValueError:
        return None
    if not 1 <= len(parts) <= 3:
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return float(total)


def _clean_title(value: str) -> str:
    return html.unescape(re.sub(r"</?em[^>]*>", "", value)).strip()


async def _default_transport(url: str, headers: dict[str, str]) -> dict[str, Any]:
    def read() -> dict[str, Any]:
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Bilibili HTTP request failed: {exc}") from exc

    return await asyncio.to_thread(read)


class BilibiliSearchAdapter:
    """Search public Bilibili video results; cookie is optional and never logged."""

    platform = "bilibili"
    name = "bilibili-wbi-search"
    version = "1.0.0"

    def __init__(
        self,
        *,
        cookie: str | None = None,
        transport=_default_transport,
        clock=time.time,
    ) -> None:
        self._cookie = cookie
        self._transport = transport
        self._clock = clock
        self._cached_mixin_key: str | None = None
        self._cached_at = 0.0

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://search.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    async def _mixin_key(self) -> str:
        now = self._clock()
        if self._cached_mixin_key and now - self._cached_at < 3600:
            return self._cached_mixin_key
        nav = await self._transport(f"{_API}/x/web-interface/nav", self._headers())
        wbi = nav.get("data", {}).get("wbi_img", {})
        img_url = wbi.get("img_url")
        sub_url = wbi.get("sub_url")
        if not img_url or not sub_url:
            raise RuntimeError("Bilibili navigation response did not contain WBI keys")
        key = _mixin_key(_key_from_url(img_url), _key_from_url(sub_url))
        self._cached_mixin_key = key
        self._cached_at = now
        return key

    async def search(self, request: SearchRequest) -> SearchPage:
        if request.platform.strip().lower() != self.platform:
            raise ValueError("Bilibili adapter only accepts platform='bilibili'")
        mixin = await self._mixin_key()
        params: dict[str, str | int] = {
            "search_type": "video",
            "keyword": request.keyword,
            "page": request.page,
            "page_size": request.page_size,
            "order": str(request.filters.get("order", "totalrank")),
            "duration": int(request.filters.get("duration", 0)),
            "tids": int(request.filters.get("tids", 0)),
            "wts": int(self._clock()),
        }
        signed = dict(params)
        signed["w_rid"] = hashlib.md5(
            (urlencode(sorted(signed.items())) + mixin).encode("utf-8")
        ).hexdigest()
        url = f"{_API}/x/web-interface/wbi/search/type?{urlencode(signed)}"
        payload = await self._transport(url, self._headers())
        code = payload.get("code", -1)
        if code != 0:
            message = str(payload.get("message") or "unknown API error")
            if code == -412:
                raise RuntimeError("Bilibili search blocked (-412); check session/cookie or retry later")
            raise RuntimeError(f"Bilibili search API error {code}: {message}")
        data = payload.get("data") or {}
        raw_results = (data.get("result") or [])
        candidates: list[ResourceCandidate] = []
        for item in raw_results:
            if item.get("type") not in (None, "video"):
                continue
            bvid = item.get("bvid")
            aid = item.get("aid") or item.get("id")
            url_value = item.get("arcurl") or (
                f"https://www.bilibili.com/video/{bvid}" if bvid else
                f"https://www.bilibili.com/video/av{aid}" if aid else None
            )
            if not url_value:
                continue
            pubdate = item.get("pubdate")
            candidates.append(ResourceCandidate(
                platform=self.platform,
                url=url_value,
                title=_clean_title(str(item.get("title") or "")),
                author_name=item.get("author"),
                author_url=(
                    f"https://space.bilibili.com/{item['mid']}" if item.get("mid") else None
                ),
                description=item.get("description"),
                published_at=(
                    datetime.fromtimestamp(int(pubdate), UTC).isoformat() if pubdate else None
                ),
                duration_seconds=_duration_seconds(item.get("duration")),
                thumbnail_url=item.get("pic"),
                metrics={
                    key: item[key]
                    for key in ("play", "video_review", "favorites", "review")
                    if isinstance(item.get(key), (int, float))
                },
                search_keyword=request.keyword,
                raw_metadata={
                    key: item.get(key)
                    for key in ("bvid", "aid", "typeid", "typename", "tag", "hit_columns")
                    if key in item
                },
            ))
        page_count = int(data.get("numPages") or 0)
        return SearchPage(
            platform=self.platform,
            keyword=request.keyword,
            page=request.page,
            candidates=tuple(candidates),
            has_more=request.page < page_count if page_count else len(candidates) == request.page_size,
            next_page=request.page + 1 if page_count and request.page < page_count else None,
            warnings=(),
            provider_name=self.name,
            provider_version=self.version,
        )
