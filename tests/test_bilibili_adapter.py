"""Fake-HTTP tests for the public Bilibili search adapter."""

import json
from urllib.error import HTTPError

import pytest

from aios_work_system.acquisition import (
    AcquisitionPlatformError,
    BilibiliPlatformAdapter,
    RuleBasedVideoSelector,
    SelectionCriteria,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.body


def _payload(results):
    return {"code": 0, "message": "0", "data": {"result": results}}


def _nav_payload():
    return {
        "code": 0,
        "message": "0",
        "data": {
            "wbi_img": {
                "img_url": "https://i0.hdslb.com/bfs/wbi/test-img-key.jpg",
                "sub_url": "https://i0.hdslb.com/bfs/wbi/test-sub-key.png",
            }
        },
    }


def _fake_open(search_payload, seen=None):
    def fake_open(request, *, timeout):
        if seen is not None:
            seen.append((request, timeout))
        if request.full_url.startswith(BilibiliPlatformAdapter.NAV_URL):
            return FakeResponse(_nav_payload())
        return FakeResponse(search_payload)

    return fake_open


def _video(**overrides):
    item = {
        "bvid": "BV1ab411c7mD",
        "aid": 123,
        "mid": 456,
        "author": "示例 UP 主",
        "title": '<em class="keyword">Python</em> &amp; 自动化教程',
        "duration": "1:02:03",
        "season_title": "Python 入门系列",
        "typename": "科技",
        "pubdate": 1700000000,
    }
    item.update(overrides)
    return item


def test_search_maps_public_result_to_video_candidate_and_uses_browser_headers():
    seen = []

    adapter = BilibiliPlatformAdapter(
        http_open=_fake_open(_payload([_video()]), seen),
        timeout_seconds=4,
    )
    candidates = adapter.search("Python 自动化", max_results=5)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.video_id == "BV1ab411c7mD"
    assert candidate.video_url == "https://www.bilibili.com/video/BV1ab411c7mD"
    assert candidate.platform == "bilibili"
    assert candidate.uploader == "示例 UP 主"
    assert candidate.title == "Python & 自动化教程"
    assert candidate.duration_seconds == 3723
    assert candidate.series == "Python 入门系列"
    assert candidate.license_info == "unknown"
    assert candidate.license_source == "unknown"
    assert candidate.license_verification == "unknown"
    assert seen[0][1] == 4
    search_request = seen[-1][0]
    headers = {name.lower(): value for name, value in search_request.header_items()}
    assert headers["user-agent"].startswith("Mozilla/5.0")
    assert headers["referer"] == "https://www.bilibili.com/"
    assert "cookie" not in headers
    assert search_request.full_url.startswith(BilibiliPlatformAdapter.API_URL)
    assert "w_rid=" in search_request.full_url
    assert "SESSDATA" not in search_request.full_url


def test_search_returns_empty_list_for_a_valid_empty_result():
    adapter = BilibiliPlatformAdapter(http_open=_fake_open(_payload([])))

    assert adapter.search("no matching video") == []


def test_search_keeps_unavailable_series_unset_and_license_unknown():
    adapter = BilibiliPlatformAdapter(
        http_open=_fake_open(_payload([_video(season_title=None)]))
    )

    candidate = adapter.search("Python")[0]

    assert candidate.series is None
    assert candidate.series_folder == "未分组"
    assert candidate.license_info == "unknown"


def test_search_strips_html_highlights_and_converts_short_duration():
    adapter = BilibiliPlatformAdapter(
        http_open=_fake_open(
            _payload([_video(title='<em class="keyword">API</em> 指南', duration="2:05")])
        )
    )

    candidate = adapter.search("API")[0]

    assert candidate.title == "API 指南"
    assert candidate.duration_seconds == 125


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"code": -412, "message": "请求被拦截"}, "anti-bot/risk control"),
        ({"code": -509, "message": "请求过于频繁"}, "rate limited"),
    ],
)
def test_search_surfaces_api_risk_control_and_rate_limit_errors(payload, message):
    adapter = BilibiliPlatformAdapter(http_open=_fake_open(payload))

    with pytest.raises(AcquisitionPlatformError, match=message):
        adapter.search("Python")


def test_search_surfaces_http_429_instead_of_returning_empty_results():
    def reject_request(request, *, timeout):
        if request.full_url.startswith(BilibiliPlatformAdapter.NAV_URL):
            return FakeResponse(_nav_payload())
        raise HTTPError(request.full_url, 429, "Too Many Requests", None, None)

    adapter = BilibiliPlatformAdapter(http_open=reject_request)

    with pytest.raises(AcquisitionPlatformError, match="rate limited"):
        adapter.search("Python")


def test_rule_based_selector_accepts_bilibili_candidates_directly():
    adapter = BilibiliPlatformAdapter(
        http_open=_fake_open(
            _payload([_video(title="Python 自动化入门", duration="4:30")])
        )
    )
    candidates = adapter.search("Python")

    selected = RuleBasedVideoSelector().select(
        candidates,
        SelectionCriteria(
            title_keywords=("python", "自动化"),
            max_duration_seconds=600,
            allow_unknown_license=True,
            limit=1,
        ),
    )

    assert selected == candidates


def test_search_rejects_invalid_input_without_request():
    called = False

    def fake_open(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("request should not be made")

    adapter = BilibiliPlatformAdapter(http_open=fake_open)

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.search("   ")
    with pytest.raises(ValueError, match="at least 1"):
        adapter.search("Python", max_results=0)
    assert not called
