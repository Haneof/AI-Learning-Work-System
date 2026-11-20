from scripts.procedural_simulator import MockTranslationApp, replay_normal_path


def test_normal_path_completes_only_mock_publish():
    app = MockTranslationApp()
    report = replay_normal_path(app)
    assert report["task_completed"] is True
    assert report["publish_is_mock"] is True
    assert report["actions_recorded"] == 9
    assert app.published is True


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
    app.perform("select_source", "source_language", "en")
    app.perform("select_target", "target_language", "zh")
    app.perform("select_article", "article", "Example article")
    app.perform("open", "editor")
    app.perform("save", "draft")
    app.state = "dashboard"  # Simulated interruption / app restart.
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
