# Bilibili public video search adapter

## Endpoint and access boundary

The adapter uses the public web video-search GET endpoint:

https://api.bilibili.com/x/web-interface/search/type

It sends search_type=video, the keyword, page number, and the default total-rank order with a normal desktop-browser User-Agent and the Bilibili site as Referer. It does not send SESSDATA, login cookies, access tokens, or credentials. It does not call login-only metadata endpoints or attempt to bypass WBI or anti-bot checks.

Bilibili may return HTTP 403/412, HTTP 429, or API codes such as -412, -352, or -509. The adapter raises AcquisitionPlatformError with an explicit risk-control or rate-limit message. It does not turn these failures into an empty result list and does not silently retry.

## Field mapping

| VideoCandidate field | Public search data |
|---|---|
| video_id | bvid |
| video_url | https://www.bilibili.com/video/{bvid} |
| platform | bilibili |
| uploader | author (or public result owner name when supplied) |
| title | title, with HTML highlight tags removed and entities decoded |
| duration_seconds | duration, parsed from MM:SS or HH:MM:SS |
| series | A series, season, or playlist title only when a public result field supplies one; otherwise None |
| license_info | unknown |
| license_source / license_verification | unknown |

The public search result does not provide a reliable reuse license. The adapter therefore never infers one. A missing series is represented as None; VideoCandidate.series_folder displays it as 未分组. Fields that would require a separate authenticated or otherwise unavailable endpoint remain unset.
