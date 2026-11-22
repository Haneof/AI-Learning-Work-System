# Existing GUI Hands Model Adapter

## Role in the Brain/Hands architecture

This adapter connects the GUI Agent's live observe/decide/act/verify loop to an OpenAI-compatible multimodal chat-completions endpoint. In the project architecture, it belongs to the **Hands / GUI execution layer**: the model receives the current live page observation and UI context, chooses a supported low-level GUI action, and the runtime verifies the resulting state.

The Brain LoRA is a separate component. It learns the business workflow, task order, conditions, reasons, capability choice, postcondition checks, and recovery decisions from tutorial event streams aligned with instructor narration. It delegates a high-level objective to Hands. This GUI adapter does not itself provide that business workflow learning.

The project reuses existing GUI operation capability; it does not intend to build another page-recognition or button-click model. A trained Brain may later be served alongside this or another supported Hands model, but the runtime mapping from a Brain capability ID to a Hands request must be supplied by a Hands adapter and capability registry.

This live GUI adapter is not a tutorial recorder. It does not retroactively recover rrweb or Windows UI Automation events from an MP4.

## Request and response

OpenAICompatibleDecisionModel sends a PNG screenshot as a data URL alongside a bounded DOM summary, accessibility-tree summary, objective, recent action history, and correction feedback. The returned JSON is validated by the existing GuiAction contract before the browser agent can execute it.

The GUI Agent operates on a live page. Its screenshots/DOM/accessibility observations are execution-time Hands context; they are not the primary tutorial-learning input and must not be confused with the semantic event stream captured during a tutorial recording.

## Configuration

Set these variables in the shell that will run the demo:

- AIOS_GUI_MODEL_BASE_URL: provider's OpenAI-compatible API base URL. The adapter appends /chat/completions.
- AIOS_GUI_MODEL_NAME: model identifier accepted by that endpoint.
- AIOS_GUI_MODEL_API_KEY: credential for the configured endpoint.

No endpoint address, model name, or credential is embedded in the source. The adapter fails with ModelConfigurationError when a required variable is missing. It does not substitute FakeModel. API responses and errors never print the key. HTTP redirects from the configured endpoint are not followed.

## Run the local fixture demo

Install the GUI extra and its Chromium browser. Then set all three variables above and run:

~~~bash
python scripts/run_gui_agent_demo.py
~~~

The demo serves only tests/fixtures/gui on an ephemeral 127.0.0.1 port, starts Playwright against that fixture, runs the existing BrowserAgent loop, prints the RunReport, and writes a gui-trace-v1 JSONL file under artifacts by default. Use --trace to choose another output path.

When configuration is absent, the script prints an explicit configuration error and exits without starting the browser or making a model request. There is no fake-model fallback. Browser-origin restrictions remain enforced by BrowserAgent and the browser guard.

## Offline tests

Run:

~~~bash
pytest tests/test_gui_real_model.py
~~~

The adapter tests use an ephemeral local fake HTTP server with fixed chat-completions JSON. They do not call a hosted model, access the internet, or require a real credential. Existing GUI tests continue to use their unchanged FakeModel.
