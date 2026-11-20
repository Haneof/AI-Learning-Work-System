from scripts.procedural_simulator import MockTranslationApp, replay_normal_path


def test_normal_path_covers_edit_review_save_resume_and_mock_publish():
    app = MockTranslationApp()
    report = replay_normal_path(app)
    assert report["task_completed"] is True
    assert report["publish_is_mock"] is True
    assert report["actions_recorded"] == 13
    assert app.published is True
    assert app.paragraph_added is True
    assert app.alignment_reviewed is True
    assert app.links_formatting_verified is True


def test_shifted_layout_alias_recovers_beta_control():
    app = MockTranslationApp(layout_variant="shifted")
    app.perform("enable", "settings_beta_control")
    assert app.beta_enabled is True


def test_cannot_publish_before_editor_or_real_publish_target():
    app = MockTranslationApp()
    try:
        app.perform("publish_mock", "publish")
    except ValueError:
        pass
    else:
        raise AssertionError("Publishing outside editor must be rejected")


def test_interrupted_draft_can_be_resumed():
    app = MockTranslationApp()
    app.perform("enable", "beta_toggle")
    app.perform("open", "dashboard")
    app.perform("select_source", "source_language", "es")
    app.perform("select_target", "target_language", "ca")
    app.perform("select_article", "article", "Garam masala")
    app.perform("open", "editor")
    app.perform("add_paragraph", "translation_pane")
    app.perform("verify_links_and_formatting", "paragraph_content")
    app.perform("wait_for_autosave", "draft_status")
    app.perform("navigate", "dashboard")
    app.perform("resume", "draft")
    assert app.state == "editor"
    assert app.draft_saved is True


def test_cannot_select_translation_job_before_dashboard():
    app = MockTranslationApp()
    try:
        app.perform("select_article", "article_picker", "Example article")
    except ValueError:
        pass
    else:
        raise AssertionError("Article selection outside dashboard must be rejected")


def test_cannot_open_editor_without_dashboard_state():
    app = MockTranslationApp(
        state="settings",
        source_language="en",
        target_language="zh",
        article="Example article",
    )
    try:
        app.perform("open", "editor")
    except ValueError:
        pass
    else:
        raise AssertionError("Editor must only open from the dashboard")


def test_cannot_resume_draft_outside_dashboard():
    app = MockTranslationApp(draft_saved=True, state="settings")
    try:
        app.perform("resume", "draft_button")
    except ValueError:
        pass
    else:
        raise AssertionError("Draft resume must require the dashboard state")


def test_dashboard_cannot_be_opened_from_editor_without_saved_draft():
    app = MockTranslationApp(state="editor", beta_enabled=True)
    try:
        app.perform("open", "dashboard")
    except ValueError:
        pass
    else:
        raise AssertionError("Dashboard navigation from editor must use saved-draft transition")


def test_cannot_add_paragraph_outside_editor():
    app = MockTranslationApp()
    try:
        app.perform("add_paragraph", "central_translation_pane")
    except ValueError:
        pass
    else:
        raise AssertionError("Paragraph editing outside editor must be rejected")


def test_cannot_autosave_before_content_review():
    app = MockTranslationApp(state="editor", paragraph_added=True)
    try:
        app.perform("wait_for_autosave", "autosave_indicator")
    except ValueError:
        pass
    else:
        raise AssertionError("Autosave acceptance requires links and formatting review")


def test_cannot_publish_without_reviewed_content_and_saved_draft():
    app = MockTranslationApp(state="editor", paragraph_added=True)
    try:
        app.perform("publish_mock", "mock_publish_button")
    except ValueError:
        pass
    else:
        raise AssertionError("Mock publish requires reviewed content and a saved draft")
