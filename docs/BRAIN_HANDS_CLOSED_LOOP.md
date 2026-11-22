# Brain/Hands closed loop v0.1

## Runtime boundary

The Brain owns business reasoning: it reads the current WorkflowDefinition and observed business state, chooses a registered capability, supplies business arguments and expected postconditions, and decides what to do after Hands returns. The Brain protocol has no click, keypress, CSS-selector, mouse-coordinate, or screen-coordinate action. Its only execution message is a versioned operation_delegation.

Hands owns GUI operations. It returns an operation_result correlated by call_id and task_id, including status, a fresh observed state, action summary, per-postcondition results, and evidence references. A bare done, successful click, or successful model response is not business success.

## Implemented components

- Brain and Hands are replaceable Python protocols in aios_work_system.brain_hands.interfaces.
- WorkflowBrain is a deterministic workflow-driven stand-in for the future Brain LoRA. It chooses applicable primitive workflow capabilities from current state, conditions, hard dependencies, invariants, and postconditions. It does not replay coordinates or pretend a trained model exists.
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
python -m pytest tests/test_brain_hands.py
ruff check src/aios_work_system/brain_hands tests/test_brain_hands.py
ruff format --check src/aios_work_system/brain_hands tests/test_brain_hands.py
```

## CLI Brain + Hands runner

The closed loop is available through the existing `aios` console script. The command validates a WorkflowDefinition v0.1 with `contracts/validate.py` before execution, constructs `WorkflowBrain`, runs the selected Hands implementation, and writes `report.json` plus `history.jsonl` under the output directory.

### Simulated example

Create an inputs file for the repository's shop-list-product example. The handler contract reads `product_title` (also accepts `title`) and `price` from `workflow_inputs`:

```json
{
  "initial_state": {
    "photos.status": "complete",
    "title.status": "missing",
    "price.status": "not_set"
  },
  "workflow_inputs": {
    "product_title": "Portable Pet Water Fountain",
    "price": 39.99
  }
}
```

Save that object as `shop-list-product-inputs.json`, then run:

```bash
aios run-loop \
  --workflow contracts/examples/shop-list-product.workflow.json \
  --inputs shop-list-product-inputs.json \
  --hands simulated \
  --brain workflow \
  --output-dir artifacts/brain-hands/shop-list-product
```

The example should finish with `status=succeeded`, `goal_satisfied=true`, a verified title, and a set price. The simulated handler does not open a browser or publish a product.

### Browser Hands against a local WooCommerce sandbox

Install Playwright and Chromium:

```bash
python -m pip install -e ".[dev,gui]"
playwright install chromium
```

Configure the existing local OpenAI-compatible operation-model endpoint with `AIOS_GUI_MODEL_BASE_URL`, `AIOS_GUI_MODEL_NAME`, and `AIOS_GUI_MODEL_API_KEY`. There is no fake-model fallback: missing or invalid configuration exits with code 2. The endpoint's model must implement the existing constrained `DecisionModel.decide(request)` contract. Browser mode accepts loopback HTTP(S) URLs only; do not point it at a production store or an unrestricted external origin.

The following is a command template for a future local sandbox. The WooCommerce WorkflowDefinition JSON is a separate acceptance-test deliverable and is intentionally not included in this CLI change:

```bash
aios run-loop \
  --workflow path/to/woocommerce-product.workflow.json \
  --inputs path/to/woocommerce-product-inputs.json \
  --hands browser \
  --brain workflow \
  --url "http://localhost:8080/wp-admin/post-new.php?post_type=product" \
  --trace-dir artifacts/brain-hands/woocommerce/traces \
  --output-dir artifacts/brain-hands/woocommerce
```

Browser mode uses the read-only `woocommerce_product_state(page)` observer for title, product type, regular price, description fields, draft-update notice, and Publish-button visibility. The observer never clicks Publish or writes to the page. Actual operations remain limited to the workflow's registered capabilities; this CLI adds no publishing capability or approval bypass.

### Flags and exit codes

- `--workflow`: required path to a WorkflowDefinition v0.1 JSON file.
- `--inputs`: optional JSON file with top-level `initial_state` and `workflow_inputs` objects; either may be omitted and defaults to an empty object.
- `--hands`: `simulated` (default) or `browser`.
- `--brain`: only `workflow` is accepted; this is the deterministic WorkflowBrain stub, not a LoRA Brain.
- `--max-decisions`: positive decision limit (default 30).
- `--output-dir`: report directory (default `artifacts/brain-hands/run`).
- `--url`: required for browser Hands; must be a loopback HTTP(S) URL.
- `--trace-dir`: browser-only trace directory (default `<output-dir>/traces`).

Exit code 0 means the loop status is `succeeded` and the independently checked workflow goal is satisfied. Other loop outcomes return 1. Missing/invalid files, workflow validation failures, unsupported configuration, or a missing/unconfigured browser operation model return 2. The loop continues to block high-, critical-, and unknown-risk delegations pending human approval; no `--yes`, `--force`, or auto-approval option is provided.

No real Brain LoRA adapter is present. Browser operation still requires a separately provisioned, locally served GUI DecisionModel and a controlled local application. A successful BrowserAgent `done` action is not enough: the loop verifies business postconditions against a fresh observer state.
