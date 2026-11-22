# Brain/Hands closed loop v0.1

## Runtime boundary

The Brain owns business reasoning: it reads the current WorkflowDefinition and observed business state, chooses a registered capability, supplies business arguments and expected postconditions, and decides what to do after Hands returns. The Brain protocol has no click, keypress, CSS-selector, mouse-coordinate, or screen-coordinate action. Its only execution message is a versioned operation_delegation.

Hands owns GUI operations. It returns an operation_result correlated by call_id and task_id, including status, a fresh observed state, action summary, per-postcondition results, and evidence references. A bare done, successful click, or successful model response is not business success.

## Implemented components

- Brain and Hands are replaceable Python protocols in aios_work_system.brain_hands.interfaces.
- WorkflowBrain is a deterministic workflow-driven stand-in for the future Brain LoRA. It chooses applicable primitive workflow capabilities from current state, conditions, hard dependencies, invariants, and postconditions. It does not replay coordinates or pretend a trained adapter exists.
- SimulatedHands applies registered capability handlers to an isolated business-state mapping and returns evidence-linked postcondition checks. shop_listing_handlers() supplies the repository's shop-list-product.workflow.json fixture.
- BrainHandsLoop refreshes state before the first decision and after every Hands result. It independently checks the result against the fresh observed state and requires every expected postcondition to be reported as passed with evidence. A failed/partial/uncertain result is passed back to the Brain with the latest state; the loop never automatically advances the workflow. The workflow goal is independently checked before accepting the Brain's finish decision.
- BrowserAgentHandsAdapter bridges the same Hands protocol to the existing BrowserAgent, DecisionModel, Playwright local-origin guard, and JSONL trace. It does not replace the current GUI operation machinery. It requires an application-specific state observer; DOM text or a BrowserAgent done alone is not a substitute for business postcondition verification.
- The existing DockerSandboxRunner remains the isolated, network-disabled executor for skill/code validation. It is not repurposed to host a live browser: its current no-network/read-only policy is intentionally retained.

The Brain loop is not coupled to a trained adapter. When a Brain LoRA is provisioned later, a serving adapter can implement the Brain.decide(BrainContext) protocol without changing Hands or the loop. There are currently zero real approved training samples; no real Brain adapter is present.

## Brain-only acceptance (CI)

The CI brain-only harness uses the real example WorkflowDefinition, WorkflowBrain, and SimulatedHands. It asserts the business outcome (title.status == verified and price.status == set), not a sequence of GUI clicks. Additional tests cover state continuity, delegation correlation, pre/postcondition enforcement, partial-result recovery, and non-idempotent retry refusal.

Run:

```bash
python -m pip install -e ".[dev,gui]"
pytest tests/test_brain_hands.py
ruff check src/aios_work_system/brain_hands tests/test_brain_hands.py
ruff format --check src/aios_work_system/brain_hands tests/test_brain_hands.py
```

## Manual Brain + real Hands harness (not CI)

This path is intentionally manual. It requires a controlled local application, Chromium/Playwright, a local UI-TARS-class operation model (or a local OpenAI-compatible server that emits the repository's constrained GuiAction contract), and a domain-specific state observer. No operation model is downloaded or run by CI.

1. Start the target application on loopback only (localhost, 127.0.0.1, or ::1). Do not point the adapter at a production account or an unrestricted external origin. The existing BrowserAgent request guard rejects cross-origin navigation and network requests.
2. Install the GUI extra and Chromium: python -m pip install -e ".[gui]" and playwright install chromium.
3. Configure the existing local GUI model endpoint variables: AIOS_GUI_MODEL_BASE_URL, AIOS_GUI_MODEL_NAME, and AIOS_GUI_MODEL_API_KEY. Point them to a local UI-TARS-class serving endpoint only after reviewing its model revision and action schema. The operation model must implement the existing DecisionModel.decide(request) response contract; if its native output differs, translate it at that adapter boundary, not in the Brain.
4. Implement an async state_observer(page) for the target application. It must return normalized business fields used by the WorkflowDefinition (for example, {"title.status": "verified", "price.status": "set"}) based on a fresh DOM/accessibility or application-state observation. Do not infer success from a model's text response.
5. Instantiate OpenAICompatibleDecisionModel.from_env(), BrowserAgentHandsAdapter(page, model, state_observer, trace_dir), and BrainHandsLoop(workflow, WorkflowBrain(workflow), hands). Replace WorkflowBrain with the real Brain adapter only when one exists and has passed its own evaluation.
6. Evaluate the final LoopReport.goal_satisfied and final business state against every workflow success condition. Also inspect each operation result, trace, evidence ref, recovery event, and any partial/failed result. The score is business-goal completion plus safe recovery on alternate states—not click count, selector accuracy, or the model's done token.

The manual path above is a harness specification and adapter implementation, not a claim of an executed real-model test. For this code change only the simulated Brain + simulated Hands path is run in CI. No real Brain LoRA adapter, no real Hands model, and no real operation-model request were run.
