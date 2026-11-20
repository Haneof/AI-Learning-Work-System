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
    paragraph_added: bool = False
    alignment_reviewed: bool = False
    links_formatting_verified: bool = False
    draft_saved: bool = False
    published: bool = False
    layout_variant: str = "standard"
    audit_log: list[dict[str, Any]] = field(default_factory=list)

    def perform(self, action: str, target: str, value: str | None = None) -> dict[str, Any]:
        before = self.snapshot()
        resolved = self._resolve_target(target)
        if action == "enable" and resolved == "beta_feature" and self.state == "settings":
            self.beta_enabled = True
        elif action == "open" and resolved == "dashboard" and self.state == "settings" and self.beta_enabled:
            self.state = "dashboard"
        elif (
            action == "select_source"
            and resolved == "source_language"
            and self.state == "dashboard"
            and value
        ):
            self.source_language = value
        elif (
            action == "select_target"
            and resolved == "target_language"
            and self.state == "dashboard"
            and value
        ):
            self.target_language = value
        elif (
            action == "select_article"
            and resolved == "article"
            and self.state == "dashboard"
            and value
        ):
            self.article = value
        elif (
            action == "open"
            and resolved == "editor"
            and self.state == "dashboard"
            and all([self.source_language, self.target_language, self.article])
        ):
            self.state = "editor"
        elif action == "add_paragraph" and resolved == "translation_pane" and self.state == "editor":
            self.paragraph_added = True
        elif (
            action == "inspect_alignment"
            and resolved == "sentence_alignment"
            and self.state == "editor"
            and self.paragraph_added
        ):
            self.alignment_reviewed = True
        elif (
            action == "verify_links_and_formatting"
            and resolved == "paragraph_content"
            and self.state == "editor"
            and self.paragraph_added
        ):
            self.links_formatting_verified = True
        elif (
            action == "wait_for_autosave"
            and resolved == "draft_status"
            and self.state == "editor"
            and self.paragraph_added
            and self.links_formatting_verified
        ):
            self.draft_saved = True
        elif (
            action == "navigate"
            and resolved == "dashboard"
            and self.state == "editor"
            and self.draft_saved
        ):
            self.state = "dashboard"
        elif (
            action == "resume"
            and resolved == "draft"
            and self.draft_saved
            and self.state == "dashboard"
        ):
            self.state = "editor"
        elif (
            action == "publish_mock"
            and resolved == "publish"
            and self.state == "editor"
            and self.draft_saved
            and self.alignment_reviewed
            and self.links_formatting_verified
        ):
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
            "central_translation_pane": "translation_pane",
            "sentence_highlights": "sentence_alignment",
            "links_and_formatting": "paragraph_content",
            "autosave_indicator": "draft_status",
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
            "paragraph_added": self.paragraph_added,
            "alignment_reviewed": self.alignment_reviewed,
            "links_formatting_verified": self.links_formatting_verified,
            "draft_saved": self.draft_saved,
            "published": self.published,
        }


def replay_normal_path(app: MockTranslationApp) -> dict[str, Any]:
    app.perform("enable", "beta_toggle")
    app.perform("open", "dashboard")
    app.perform("select_source", "source_language_dropdown", "es")
    app.perform("select_target", "target_language_dropdown", "ca")
    app.perform("select_article", "article_picker", "Garam masala")
    app.perform("open", "editor")
    app.perform("add_paragraph", "central_translation_pane")
    app.perform("inspect_alignment", "sentence_highlights")
    app.perform("verify_links_and_formatting", "links_and_formatting")
    app.perform("wait_for_autosave", "autosave_indicator")
    app.perform("navigate", "translation_dashboard")
    app.perform("resume", "draft_button")
    app.perform("publish_mock", "mock_publish_button")
    return {
        "task_completed": app.state == "published_mock",
        "publish_is_mock": True,
        "actions_recorded": len(app.audit_log),
        "final_state": app.snapshot(),
    }
