# Bilibili public video search adapter

## Endpoint and access boundary

The adapter uses the current WBI-signed public video-search GET endpoint:

https://api.bilibili.com/x/web-interface/wbi/search/type

It first opens the public Bilibili home page to establish an anonymous browser cookie jar, then reads the public WBI image keys from the unauthenticated navigation endpoint and signs the video-search request. This uses the platform's normal public request protocol; it does not provide SESSDATA, login cookies, access tokens, account credentials, or a logged-in session. It does not call login-only metadata endpoints or attempt to bypass anti-bot checks.

The request includes search_type=video, keyword, page, and order=totalrank, plus the required WBI signature. Bilibili may return HTTP 403/412, HTTP 429, or API codes such as -412, -352, -799, or -1200. The adapter raises AcquisitionPlatformError with an explicit risk-control or rate-limit message. It does not turn these failures into an empty result list or silently retry.

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

The public search response does not provide a reliable reuse license. The adapter therefore never infers one. A missing series is represented as None; VideoCandidate.series_folder displays it as 未分组. Fields that would require a separate authenticated or otherwise unavailable endpoint remain unset.

## Testing boundary

All adapter tests inject a fake HTTP opener. They do not contact Bilibili, request real cookies, or use account credentials. The tests cover WBI key lookup, signed search URL construction, metadata normalization, empty results, API/risk-control errors, HTTP 429, and direct use of RuleBasedVideoSelector.
