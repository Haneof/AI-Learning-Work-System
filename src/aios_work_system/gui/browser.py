"""Playwright browser observation, local-origin enforcement, and action execution."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from urllib.parse import urlsplit

from aios_work_system.gui.contracts import (
    BrowserObservation,
    ExpectedResult,
    GuiAction,
)


class LocalBrowserOnlyError(ValueError):
    """Raised whenever a browser is not confined to its approved local origin."""


def local_origin(url: str) -> str:
    """Return a normalized HTTP(S) loopback origin or reject the URL."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise LocalBrowserOnlyError(f"only loopback HTTP(S) URLs are allowed: {url}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise LocalBrowserOnlyError(f"invalid local URL port: {url}") from exc
    default_port = 443 if parsed.scheme == "https" else 80
    port_part = f":{port}" if port is not None and port != default_port else ""
    return f"{parsed.scheme}://{host}{port_part}"


def ensure_same_origin(url: str, allowed_origin: str) -> None:
    current_origin = local_origin(url)
    if current_origin != allowed_origin:
        raise LocalBrowserOnlyError(
            f"browser origin changed: expected {allowed_origin}, observed {current_origin}"
        )


async def install_local_only_guard(page: object, allowed_origin: str) -> None:
    """Abort every browser request that leaves the one approved local origin."""

    async def guard(route: object) -> None:
        request_url = route.request.url  # type: ignore[attr-defined]
        try:
            ensure_same_origin(request_url, allowed_origin)
        except LocalBrowserOnlyError:
            await route.abort()  # type: ignore[attr-defined]
            return
        await route.continue_()  # type: ignore[attr-defined]

    await page.context.route("**/*", guard)  # type: ignore[attr-defined]


async def observe_page(page: object) -> BrowserObservation:
    """Capture the full visual and semantic state required for one training frame."""
    url = page.url  # type: ignore[attr-defined]
    origin = local_origin(url)
    screenshot = await page.screenshot(type="png", full_page=True, animations="disabled")  # type: ignore[attr-defined]
    dom_snapshot = await page.content()  # type: ignore[attr-defined]
    accessibility_snapshot = await page.locator("body").aria_snapshot(timeout=3000)  # type: ignore[attr-defined]
    return BrowserObservation(
        timestamp=datetime.now(UTC).isoformat(),
        url=url,
        origin=origin,
        title=await page.title(),  # type: ignore[attr-defined]
        screenshot_b64=base64.b64encode(screenshot).decode("ascii"),
        dom_snapshot=dom_snapshot,
        accessibility_snapshot=accessibility_snapshot,
    )


async def execute_action(page: object, action: GuiAction) -> None:
    """Execute only the five-action protocol; arbitrary code and navigation are absent."""
    timeout_ms = action.timeout_ms
    if action.action == "click":
        await page.locator(action.selector).click(timeout=timeout_ms)  # type: ignore[attr-defined,arg-type]
    elif action.action == "type":
        await page.locator(action.selector).fill(action.value, timeout=timeout_ms)  # type: ignore[attr-defined,arg-type]
    elif action.action == "scroll":
        delta = action.amount if action.direction == "down" else -action.amount
        if action.selector is None:
            await page.mouse.wheel(0, delta)  # type: ignore[attr-defined]
        else:
            locator = page.locator(action.selector)  # type: ignore[attr-defined]
            await locator.scroll_into_view_if_needed(timeout=timeout_ms)
            await locator.evaluate(
                "(element, distance) => element.scrollBy(0, distance)",
                delta,
            )
    elif action.action == "wait":
        await page.wait_for_timeout(timeout_ms)  # type: ignore[attr-defined]
    elif action.action == "done":
        return


async def verify_expectation(
    page: object,
    expected: ExpectedResult,
    timeout_ms: int = 3000,
) -> dict[str, object]:
    """Evaluate an explicit assertion and return both observed value and pass/fail."""
    observed: object = None
    try:
        if expected.kind == "url_contains":
            observed = page.url  # type: ignore[attr-defined]
            passed = expected.value in observed
        elif expected.kind == "title_contains":
            observed = await page.title()  # type: ignore[attr-defined]
            passed = expected.value in observed
        else:
            locator = page.locator(expected.selector)  # type: ignore[attr-defined,arg-type]
            if expected.kind in {"text_contains", "text_equals"}:
                observed = await locator.inner_text(timeout=timeout_ms)
                passed = (
                    expected.value in observed
                    if expected.kind == "text_contains"
                    else observed == expected.value
                )
            elif expected.kind == "value_equals":
                observed = await locator.input_value(timeout=timeout_ms)
                passed = observed == expected.value
            elif expected.kind == "visible":
                await locator.wait_for(state="visible", timeout=timeout_ms)
                observed = await locator.is_visible()
                passed = observed is True
            elif expected.kind == "hidden":
                await locator.wait_for(state="hidden", timeout=timeout_ms)
                observed = await locator.is_visible()
                passed = observed is False
            elif expected.kind == "attribute_equals":
                observed = await locator.get_attribute(expected.attribute, timeout=timeout_ms)
                passed = observed == expected.value
            else:
                raise ValueError(f"unsupported expectation kind: {expected.kind}")
        return {
            "passed": bool(passed),
            "kind": expected.kind,
            "selector": expected.selector,
            "expected": expected.value,
            "observed": observed,
        }
    except Exception as exc:
        return {
            "passed": False,
            "kind": expected.kind,
            "selector": expected.selector,
            "expected": expected.value,
            "observed": observed,
            "error": f"{type(exc).__name__}: {exc}",
        }
