"""Replaceable video selection interface and deterministic baseline."""

from __future__ import annotations

from typing import Protocol

from aios_work_system.acquisition.models import SelectionCriteria, VideoCandidate


class VideoSelector(Protocol):
    def select(
        self,
        candidates: list[VideoCandidate],
        criteria: SelectionCriteria,
    ) -> list[VideoCandidate]:
        """Select candidate videos using a supplied policy."""


class RuleBasedVideoSelector:
    """Deterministic selector used for tests and first-run acquisition."""

    def select(
        self,
        candidates: list[VideoCandidate],
        criteria: SelectionCriteria,
    ) -> list[VideoCandidate]:
        selected: list[VideoCandidate] = []
        title_terms = tuple(term.casefold() for term in criteria.title_keywords)
        series_terms = tuple(term.casefold() for term in criteria.series_keywords)
        allowed_licenses = tuple(term.casefold() for term in criteria.allowed_license_terms)

        for candidate in candidates:
            if candidate.duration_seconds is None:
                continue
            duration_matches = (
                criteria.min_duration_seconds
                <= candidate.duration_seconds
                <= criteria.max_duration_seconds
            )
            if not duration_matches:
                continue

            title = candidate.title.casefold()
            if title_terms and not all(term in title for term in title_terms):
                continue

            series = (candidate.series or "").casefold()
            if series_terms and not any(term in series for term in series_terms):
                continue

            license_text = (candidate.license_info or "unknown").casefold()
            license_is_unknown = license_text in {"", "unknown", "none", "null"}
            if license_is_unknown and not criteria.allow_unknown_license:
                continue
            if allowed_licenses:
                if license_is_unknown or not any(term in license_text for term in allowed_licenses):
                    continue

            selected.append(candidate)

        # Prefer explicitly Creative Commons-identified content, then shorter
        # videos, while preserving provider order as the stable final tie-breaker.
        selected.sort(
            key=lambda item: (
                not any(
                    term in (item.license_info or "").casefold()
                    for term in ("creative commons", "cc by")
                ),
                item.duration_seconds or float("inf"),
            )
        )
        return selected[: max(criteria.limit, 1)]
