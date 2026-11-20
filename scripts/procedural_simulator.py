"""Deterministic local mock app for safe procedural replay.

No network access, browser automation, or real publishing is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MockTranslationApp:
    state: str = "settings"
    beta_enabled: bool = False
    source_language: str | None = None
    target_language: str | None = None
    article: str | None = None
    draft_saved: bool = False
    published: bool = False
    layout_variant: str = "standard"
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def perform(self, action: str, target: str, value: str | None = None) -> dict[str, Any]:
        before = self.snapshot()
        resolved = self._resolve_target(target)
        if action == "enable" and resolved == "beta_feature" and self.state == "settings":
            self.beta_enabled = True
        elif action == "open" and resolved == "dashboard" and self.beta_enabled:
            self.state = "dashboard"
        elif (
            action == "select_source"
            and resolved == "source_language"
            and self.state == "dashboard"
        ):
            self.source_language = value
        elif (
            action == "select_target"
            and resolved == "target_language"
            and self.state == "dashboard"
        ):
            self.target_language = value
        elif action == "select_article" and resolved == "article" and self.state == "dashboard":
            self.article = value
        elif action == "open" and resolved == "editor" and self.state == "dashboard" and all(
            [self.source_language, self.target_language, self.article]
        ):
            self.state = "editor"
        elif action == "save" and resolved == "draft" and self.state == "editor":
            self.draft_saved = True
        elif (
            action == "resume"
            and resolved == "draft"
            and self.draft_saved
            and self.state == "dashboard"
        ):
            self.state = "editor"
        elif action == "publish_mock" and resolved == "publish" and self.state == "editor":
            self.published = True
            self.state = "published_mock"
        else:
            raise ValueError(f"Action not allowed in current state: {action} -> {target}")
        after = self.snapshot()
        self.audit_log.append({
            "action": action, "target": resolved, "before": before, "after": after
        })
        return after

    def _resolve_target(self, target: str) -> str:
        aliases = {
            "beta_toggle": "beta_feature",
            "beta_feature_switch": "beta_feature",
            "translation_dashboard": "dashboard",
            "source_language_dropdown": "source_language",
            "target_language_dropdown": "target_language",
            "article_picker": "article",
            "draft_button": "draft",
            "mock_publish_button": "publish",
        }
        if self.layout_variant == "shifted":
            aliases.update({"settings_beta_control": "beta_feature"})
        return aliases.get(target, target)

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "beta_enabled": self.beta_enabled,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "article": self.article,
            "draft_saved": self.draft_saved,
            "published": self.published,
        }


def replay_normal_path(app: MockTranslationApp) -> dict[str, Any]:
    app.perform("enable", "beta_toggle")
    app.perform("open", "dashboard")
    app.perform("select_source", "source_language_dropdown", "en")
    app.perform("select_target", "target_language_dropdown", "zh")
    app.perform("select_article", "article_picker", "Example article")
    app.perform("open", "editor")
    app.perform("save", "draft_button")
    app.perform("resume", "draft_button")
    app.perform("publish_mock", "mock_publish_button")
    return {
        "task_completed": app.state == "published_mock",
        "publish_is_mock": True,
        "actions_recorded": len(app.audit_log),
        "final_state": app.snapshot(),
    }
