"""Tests for platform discovery orchestration and Bilibili mapping."""

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from aios_work_system.acquisition import (
    AdapterRegistry,
    BilibiliSearchAdapter,
    PlatformCatalog,
    PlatformDescriptor,
    ResourceCandidate,
    SearchPage,
    SearchRequest,
    SearchService,
)


class FakeAdapter:
    def __init__(self, platform, *, candidates=(), error=None, delay=0):
        self.platform = platform
        self.name = "fake"
        self.version = "1"
        self.candidates = candidates
        self.error = error
        self.delay = delay

    async def search(self, request):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return SearchPage(
            platform=self.platform,
            keyword=request.keyword,
            page=request.page,
            candidates=tuple(self.candidates),
            provider_name=self.name,
            provider_version=self.version,
        )


def test_platform_catalog_lists_capabilities_and_rejects_duplicates():
    descriptor = PlatformDescriptor(
        platform="bilibili",
        display_name="B站",
        capabilities=("keyword_search", "pagination"),
        status="implemented_not_live_verified",
    )
    catalog = PlatformCatalog((descriptor,))

    assert catalog.get("BILIBILI") == descriptor
    assert catalog.list() == (descriptor,)
    with pytest.raises(ValueError, match="already cataloged"):
        catalog.register(descriptor)


@pytest.mark.asyncio
async def test_search_service_preserves_success_when_another_platform_fails():
    registry = AdapterRegistry()
    candidate = ResourceCandidate(
        platform="bilibili",
        url="https://www.bilibili.com/video/BV1xx",
        title="Python tutorial",
    )
    registry.register(FakeAdapter("bilibili", candidates=(candidate,)))
    registry.register(FakeAdapter("youtube", error=RuntimeError("provider unavailable")))

    result = await SearchService(registry).search_many(
        "python tutorial", ["bilibili", "youtube"]
    )

    assert result.succeeded_platforms == ("bilibili",)
    assert len(result.candidates) == 1
    assert result.failures[0].platform == "youtube"
    assert result.failures[0].message == "provider unavailable"


@pytest.mark.asyncio
async def test_search_service_deduplicates_platforms_and_rejects_unknown_before_work():
    registry = AdapterRegistry()
    registry.register(FakeAdapter("bilibili"))

    result = await SearchService(registry).search_many("python", ["BILIBILI", "bilibili"])
    assert result.succeeded_platforms == ("bilibili",)

    with pytest.raises(KeyError, match="not registered"):
        await SearchService(registry).search_many("python", ["bilibili", "unknown"])


@pytest.mark.asyncio
async def test_search_service_times_out_slow_adapter():
    registry = AdapterRegistry()
    registry.register(FakeAdapter("bilibili", delay=0.05))
    result = await SearchService(registry, timeout_seconds=0.001).search_many(
        "python", ["bilibili"]
    )

    assert result.succeeded_platforms == ()
    assert result.failures[0].error_type == "TimeoutError"


@pytest.mark.asyncio
async def test_bilibili_adapter_signs_search_and_maps_video_candidates():
    calls = []

    async def fake_transport(url, headers):
        calls.append((url, headers))
        if url.endswith("/x/web-interface/nav"):
            return {
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/abc123.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/def456.png",
                    }
                }
            }
        return {
            "code": 0,
            "data": {
                "numPages": 3,
                "result": [
                    {
                        "type": "video",
                        "bvid": "BV1xx",
                        "aid": 123,
                        "arcurl": "https://www.bilibili.com/video/BV1xx",
                        "title": "<em class='keyword'>Python</em>教程",
                        "author": "Teacher",
                        "mid": 88,
                        "description": "A course",
                        "pubdate": 1700000000,
                        "duration": "01:02:03",
                        "pic": "https://i0.hdslb.com/cover.jpg",
                        "play": 1000,
                        "favorites": 50,
                    },
                    {"type": "live_room", "title": "not a video"},
                ],
            },
        }

    adapter = BilibiliSearchAdapter(
        cookie="SESSDATA=test-cookie",
        transport=fake_transport,
        clock=lambda: 1710000000,
    )
    page = await adapter.search(
        SearchRequest(platform="bilibili", keyword="Python", page=2)
    )

    assert len(calls) == 2
    assert calls[0][1]["Cookie"] == "SESSDATA=test-cookie"
    query = parse_qs(urlparse(calls[1][0]).query)
    assert query["search_type"] == ["video"]
    assert query["keyword"] == ["Python"]
    assert query["page"] == ["2"]
    assert len(query["w_rid"][0]) == 32
    assert len(page.candidates) == 1
    candidate = page.candidates[0]
    assert candidate.title == "Python教程"
    assert candidate.author_name == "Teacher"
    assert candidate.duration_seconds == 3723
    assert candidate.metrics["play"] == 1000
    assert candidate.search_keyword == "Python"
    assert page.has_more is True
    assert page.provider_name == "bilibili-wbi-search"


@pytest.mark.asyncio
async def test_bilibili_adapter_surfaces_anti_bot_response_without_fake_results():
    async def fake_transport(url, headers):
        if url.endswith("/x/web-interface/nav"):
            return {
                "data": {
                    "wbi_img": {
                        "img_url": "https://i0.hdslb.com/bfs/wbi/abc123.png",
                        "sub_url": "https://i0.hdslb.com/bfs/wbi/def456.png",
                    }
                }
            }
        return {"code": -412, "message": "请求被拦截"}

    adapter = BilibiliSearchAdapter(transport=fake_transport, clock=lambda: 1710000000)
    with pytest.raises(RuntimeError, match="-412"):
        await adapter.search(SearchRequest(platform="bilibili", keyword="Python"))
