# Bounded procedural model runner

`scripts/procedural_agent_runner.py` adds a provider-neutral orchestration loop. It
accepts a caller-supplied `model_call(prompt) -> raw_text`, asks for one action at a
time, parses strict JSON, passes the proposal through the existing action allowlist,
and stops after a bounded number of proposals or a mock task terminal state.

## Integration contract

```python
from scripts.procedural_agent_runner import run_agent
from scripts.procedural_simulator import MockTranslationApp

def model_call(prompt: str) -> str:
    # Connect a local model runtime here; return its raw text response.
    ...

report = run_agent(MockTranslationApp(), model_call, max_steps=20)
```

The runner intentionally does not bundle Ollama, llama.cpp, Transformers, or a remote
provider SDK. The local model/runtime choice must be tested on the user's actual
hardware before selecting a default. The model receives a state snapshot and the
allowlisted action/target vocabulary, but every response is independently parsed and
validated before simulator execution.

## Controls

- One proposal per model call; no multi-action batch execution.
- Strict JSON only; markdown fences and surrounding prose are rejected.
- At most `max_steps` proposals.
- Provider exceptions are captured as explicit events.
- Malformed or state-invalid proposals are rejected and logged; they do not mutate
  simulator state.
- The only terminal success state is `published_mock`.
- The explicit stop object is `{"action":"stop","target":"task"}`.

## Metrics and limitations

The returned episode record is compatible with the execution metrics evaluator.
The runner reports attempted proposals and successful simulator actions separately.
It does not infer recovery: recovery fields remain false/null until a controlled fault
injection and recovery protocol are implemented.

This is an integration seam, not evidence of an actual model run. Tests use scripted
responses, not an LLM. It controls only the in-memory simulator; it has no network,
browser, OS, or real publishing capability.
