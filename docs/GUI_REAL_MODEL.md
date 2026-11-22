# Real multimodal GUI model adapter

The GUI agent can use an OpenAI-compatible chat completions endpoint through
OpenAICompatibleDecisionModel. The adapter sends a PNG screenshot as a data URL
alongside a bounded DOM summary, an accessibility-tree summary, the objective,
recent action history, and correction feedback. The returned JSON is validated by
the existing GuiAction contract before the browser agent can execute it.

## Configuration

Set these variables in the shell that will run the demo:

- AIOS_GUI_MODEL_BASE_URL: the provider's OpenAI-compatible API base URL. The
  adapter appends /chat/completions to this value.
- AIOS_GUI_MODEL_NAME: the model identifier accepted by that endpoint.
- AIOS_GUI_MODEL_API_KEY: the credential for that configured endpoint.

No endpoint address, model name, or credential is embedded in the source. The
adapter fails with ModelConfigurationError when any required variable is missing.
It does not substitute FakeModel. API responses and errors never print the key.
HTTP redirects from the configured endpoint are not followed.

## Run the local fixture demo

Install the GUI extra and its Chromium browser in the project environment. Then
set all three variables above and run:

    python scripts/run_gui_agent_demo.py

The demo serves only tests/fixtures/gui on an ephemeral 127.0.0.1 port, starts
Playwright against that fixture, runs the existing BrowserAgent loop, prints the
RunReport, and writes a gui-trace-v1 JSONL file under artifacts by default. Use
the --trace argument to choose another output path.

When configuration is absent, the script prints an explicit configuration error
and exits without starting the browser or making a model request. There is no
fake-model fallback. Browser-origin restrictions remain enforced by the existing
BrowserAgent and browser guard; non-fixture cross-origin requests are aborted.

## Offline tests

Run:

    pytest tests/test_gui_real_model.py

The adapter tests use only an ephemeral local fake HTTP server with fixed
chat-completions JSON. They do not call a hosted model, access the internet, or
require a real credential. Existing GUI tests continue to use their unchanged
FakeModel.
