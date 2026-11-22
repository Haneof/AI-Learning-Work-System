# Real Multimodal GUI Decision Model Adapter

## Role in the system

This adapter connects the GUI Agent's live observe/decide/act/verify loop to an OpenAI-compatible multimodal chat-completions endpoint. Its purpose is downstream **trained-expert evaluation**: the configured model receives the current screenshot and UI context, chooses one allowed action, and the GUI runtime verifies the resulting state.

It is not the tutorial-video extraction engine. It does not replace Qwen3-VL or Mage-VL as video-understanding candidates, and it does not replace Magma's separate action-grounding evaluation. It also does not infer historical mouse clicks from a prerecorded video.

When a trained 4B+LoRA expert is served through a compatible endpoint, this adapter is a possible integration boundary, but actual LoRA loading/serving and model compatibility must be verified separately.

## Request and response

OpenAICompatibleDecisionModel sends a PNG screenshot as a data URL alongside a bounded DOM summary, accessibility-tree summary, objective, recent action history, and correction feedback. The returned JSON is validated by the existing GuiAction contract before the browser agent can execute it.

## Configuration

Set these variables in the shell that will run the demo:

- AIOS_GUI_MODEL_BASE_URL: provider's OpenAI-compatible API base URL. The adapter appends /chat/completions.
- AIOS_GUI_MODEL_NAME: model identifier accepted by that endpoint.
- AIOS_GUI_MODEL_API_KEY: credential for the configured endpoint.

No endpoint address, model name, or credential is embedded in the source. The adapter fails with ModelConfigurationError when a required variable is missing. It does not substitute FakeModel. API responses and errors never print the key. HTTP redirects from the configured endpoint are not followed.

## Run the local fixture demo

Install the GUI extra and its Chromium browser. Then set all three variables above and run:

```bash
python scripts/run_gui_agent_demo.py
```

The demo serves only tests/fixtures/gui on an ephemeral 127.0.0.1 port, starts Playwright against that fixture, runs the existing BrowserAgent loop, prints the RunReport, and writes a gui-trace-v1 JSONL file under artifacts by default. Use --trace to choose another output path.

When configuration is absent, the script prints an explicit configuration error and exits without starting the browser or making a model request. There is no fake-model fallback. Browser-origin restrictions remain enforced by BrowserAgent and the browser guard.

## Offline tests

Run:

```bash
pytest tests/test_gui_real_model.py
```

The adapter tests use an ephemeral local fake HTTP server with fixed chat-completions JSON. They do not call a hosted model, access the internet, or require a real credential. Existing GUI tests continue to use their unchanged FakeModel.
