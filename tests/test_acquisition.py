"""Tests for normalized platform discovery contracts."""

import pytest

from aios_work_system.acquisition import (
    AdapterRegistry,
    ResourceCandidate,
    SearchPage,
    SearchRequest,
    canonicalize_url,
    deduplicate_candidates,
)


def test_search_request_validates_required_fields_and_paging():
    with pytest.raises(ValueError, match="keyword"):
        SearchRequest(platform="bili", keyword=" ")
    with pytest.raises(ValueError, match="page"):
        SearchRequest(platform="bili", keyword="python", page=0)
    with pytest.raises(ValueError, match="page_size"):
        SearchRequest(platform="bili", keyword="python", page_size=101)


def test_canonicalize_url_removes_tracking_but_keeps_platform_tokens():
    result = canonicalize_url(
        "HTTPS://Example.COM/video?id=123&fbclid=tracking&xsec_token=required#section"
    )

    assert result == "https://example.com/video?id=123&xsec_token=required"


def test_canonicalize_url_rejects_non_http_and_relative_urls():
    with pytest.raises(ValueError, match="HTTP"):
        canonicalize_url("file:///tmp/video.mp4")
    with pytest.raises(ValueError, match="absolute"):
        canonicalize_url("/video/123")


def test_candidate_deduplication_is_platform_scoped_and_stable():
    candidates = [
        ResourceCandidate(platform="bili", url="https://bilibili.com/video/BV1?a=1", title="first"),
        ResourceCandidate(platform="bili", url="https://bilibili.com/video/BV1?a=1&fbclid=x", title="duplicate"),
        ResourceCandidate(platform="xhs", url="https://bilibili.com/video/BV1?a=1", title="other platform"),
    ]

    unique = deduplicate_candidates(candidates)

    assert [item.title for item in unique] == ["first", "other platform"]


def test_candidate_preserves_platform_specific_query_parameters():
    candidate = ResourceCandidate(
        platform="xhs",
        url="https://www.xiaohongshu.com/explore/abc?xsec_token=secret",
        title="Tutorial",
    )

    assert "xsec_token=secret" in candidate.canonical_url


class FakeAdapter:
    platform = "bili"
    name = "fake"
    version = "1"

    async def search(self, request):
        return SearchPage(
            platform=request.platform,
            keyword=request.keyword,
            page=request.page,
            candidates=(),
            provider_name=self.name,
            provider_version=self.version,
        )


def test_adapter_registry_registers_and_resolves_platforms():
    registry = AdapterRegistry()
    adapter = FakeAdapter()
    registry.register(adapter)

    assert registry.get("BILI") is adapter
    assert registry.platforms() == ("bili",)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(adapter)
    with pytest.raises(KeyError, match="not registered"):
        registry.get("douyin")
