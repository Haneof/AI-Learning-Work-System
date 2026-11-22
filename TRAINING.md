# Brain LoRA training

This stage consumes the compiler output from PR #40 and trains a **Brain** adapter for workflow decisions. It does not train the Hands GUI operator.

## Framework and base checkpoint

This setup uses **Axolotl**. Its Qwen3 support includes the Qwen3 chat template and OpenAI Messages dataset format, which matches the compiler's `{"messages":[...]}` rows without translating their role/content contract.

The default base is [`DreamFast/qwen3-4b-heretic`](https://huggingface.co/DreamFast/qwen3-4b-heretic). Use the repository's standard Transformers checkpoint (the `model-00001-of-00002.safetensors` and `model-00002-of-00002.safetensors` shards plus tokenizer/config files). Do **not** use a GGUF, the `comfyui/` text-encoder file, or a quantized derivative. The Axolotl config uses `AutoModelForCausalLM`, and explicitly disables 4-bit/8-bit loading. The repository currently points at Hub revision `main`; record and pin a reviewed commit SHA before a production training run.

### T4 precision correction

A Tesla T4 is compute capability 7.5. NVIDIA documents BF16 operations as unsupported for 7.x devices; therefore the T4 profile uses `fp16: true` and `bf16: false`. The checkpoint is still the full, unquantized Transformers model; casting its weights to FP16 for T4 compute does not turn it into GGUF or 4-bit quantization. For an Ampere-or-newer GPU, a separately validated profile may use BF16 instead.

The initial T4 settings are deliberately conservative: sequence length 512, micro-batch 1, gradient accumulation 16, LoRA rank 16 / alpha 32, all Qwen attention and MLP projection modules, activation checkpointing, three epochs, and learning rate 1e-4. GPU memory depends on the exact Axolotl/Transformers/PyTorch versions and runtime; if the 16 GB T4 still runs out of memory, lower `sequence_len` to 384 or 256 before changing the base model. Do not turn on quantized loading to make this profile pass.

## Compiler inputs and sidecar-aware weighting

Compile dual-approved episodes first:

```bash
python scripts/compile_training_samples.py \
  --input artifacts/reviewed-episodes.json \
  --output-dir artifacts/brain-training \
  --seed 42 --train-fraction 0.8
```

The preparation step requires all four compiler outputs:

- `train.jsonl` + `train.training_meta.jsonl`
- `test.jsonl` + `test.training_meta.jsonl`

It requires one sidecar row per model row, in the same order, a unique `sample_id`, and the expected train/test partition. A missing/misaligned sidecar is an error. Any sidecar row marked `excluded`, `is_excluded`, `do_not_train`, held/rejected, or explicitly not eligible is refused; it is never silently filtered into training.

Axolotl's standard SFT config does not consume this project's per-row sidecar values as per-example loss multipliers. To use those values rather than ignore them, the preparation step calculates a bounded sample priority from both `evidence_tier.observation_channel` and `evidence_tier.rationale_source`, per-evidence confidence, and `rationale_loss_weight`. It then deterministically repeats higher-priority train rows up to three times. Every original approved row appears at least once. Test rows are never repeated. The sidecar and evidence labels stay outside the model messages. This is **weighted row sampling**, not a claim of mathematically exact per-token loss weighting; the generated `weight_manifest.json` records each score and repeat count.

Prepare the Axolotl datasets and validate the config before downloading model weights:

```bash
python -m pip install -e ".[training-config]"
python scripts/prepare_brain_lora_dataset.py \
  --input-dir artifacts/brain-training \
  --output-dir artifacts/brain-training/axolotl \
  --config configs/brain_lora_t4.yml
```

The script writes `train.weighted.jsonl`, `test.jsonl`, and `weight_manifest.json` under `artifacts/brain-training/axolotl/`. The CLI refuses an empty test split. Because the compiler groups splits by source/course, at least two approved source groups are required to produce a held-out test set.

## Cloud T4 procedure (Colab or rented VM)

1. Provision a **single NVIDIA T4 16 GB** runtime/VM with a compatible CUDA PyTorch build. Use a persistent disk with enough space for the model shards, prepared datasets, checkpoints, and adapter output.
2. Clone this repository and install the training configuration dependency plus Axolotl using its current installation instructions:

   ```bash
   git clone https://github.com/Haneof/AI-Learning-Work-System.git
   cd AI-Learning-Work-System
   python -m pip install --upgrade pip
   python -m pip install -e ".[training-config]"
   python -m pip install --no-build-isolation axolotl
   ```

   On Colab, upload/copy the four compiler JSONL files into `artifacts/brain-training/` (for example from mounted Drive). On a rented VM, copy the directory to the same path.
3. Prepare and validate the datasets with the command above. Do not proceed if it fails, if the train/test sets are empty, or if any excluded row is reported.
4. Check the device and precision before training:

   ```bash
   nvidia-smi
   python -c "import torch; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
   ```

   The expected T4 capability is `(7, 5)`; keep the config at FP16/BF16-off.
5. Start training only after the data-readiness gate below has been cleared:

   ```bash
   axolotl train configs/brain_lora_t4.yml
   ```

The adapter/checkpoints are written to `artifacts/brain-lora/brain-heretic-qwen3-4b/`. The deployable LoRA artifact is the adapter directory (including `adapter_config.json` and `adapter_model.safetensors`); it must be loaded alongside the same base model revision. Keep the base checkpoint and adapter separate.

## Brain policy targeted

The adapter is intended to improve the Brain's general workflow policy: task decomposition, flow planning, conditional judgment, business decisions, exception recovery, and coordination with Hands. It is not intended to memorize a fixed click path. Runtime workflow facts and volatile business rules should continue to be supplied from the current state/HTN context, with Hands returning structured execution results to the Brain for the next decision.

## Readiness gate and this PR's smoke test

**A real training run is not authorized or possible in this task.** Before any real 4B training run, the project still needs:

- at least one real, independently approved training corpus, with enough distinct approved source groups to create train and held-out test splits; and
- a real 4B verifier run for the local model verification gate, followed by independent PM verification and approval of the produced episodes.

At the time of this PR there are **zero real approved training samples**, and no GPU is provisioned. The PR's CPU smoke test uses only synthetic fixtures shaped like the PR #40 compiler tests. It exercises config validation, sidecar loading/weight computation, weighted materialization, and a deterministic tokenizer stand-in. It does **not** download the Heretic checkpoint, run the real HF tokenizer, execute an Axolotl training step, or train/save an adapter. No real training run was started.
