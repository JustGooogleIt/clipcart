# Hosted Gemma 12B on a Lambda A10: setup and results

Run on 2026-10-17 (US time), 2026-10-18 UTC, on a temporary Lambda Cloud instance that the owner terminates after the run. Instance-local data is gone after termination, so everything needed to reproduce the run is in this folder.

**Bottom line.** A 4-bit Gemma 3 12B fits on a 24 GB A10 with a 4,096-token context. It served ClipCart's style-note extraction at about 1 second median latency. Validated precision was 0.76 and recall 0.73 on 18 synthetic statements, against 0.94 and 0.68 for the rule parser. The model's main failure is confusing an avoid with a remove. That is unsafe without the existing guardrail that proposals are never saved automatically. Style memory does not depend on this model.

## What ran

| Item | Value |
|---|---|
| GPU | NVIDIA A10, 23,028 MiB, compute capability 8.6, driver 580.105.08 |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-1046-nvidia, Python 3.12.3 |
| Model | `gaunernst/gemma-3-12b-it-int4-awq`, AWQ int4, Gemma license, not gated |
| Revision | `3b0c67b98eee8fb90633ef1bfbf3d39f43b9cf9d` (see `model_files.txt` for shard SHA-256 hashes) |
| Server | vLLM 0.9.2, V1 engine, `awq_marlin` kernel, bfloat16 activations |
| Pins | torch 2.7.0, transformers 4.53.2, xformers 0.0.30; full list in `pip_freeze_vllm_env.txt` |
| Limits | `--max-model-len 4096`, `--max-num-seqs 1`, `--gpu-memory-utilization 0.90` |
| GPU memory in use | 20,690 MiB by the vLLM process; KV cache 9.89 GiB (26,992 tokens) |
| Weights on disk | 8.5 GB; weight load took 1.5 s once downloaded |

**Pin Transformers.** vLLM 0.9.2 pulls Transformers 5.x, which crashes at startup with `ValueError: 'aimv2' is already used by a Transformers config`. Pinning `transformers==4.53.2` fixes it.

## Reproduce

On a fresh Lambda A10 (Ubuntu 24.04 image with NVIDIA drivers):

```sh
python3 -m venv ~/vllm-env
~/vllm-env/bin/pip install --upgrade pip
~/vllm-env/bin/pip install vllm==0.9.2 transformers==4.53.2
# or, exactly: ~/vllm-env/bin/pip install -r pip_freeze_vllm_env.txt

umask 077; python3 -c "import secrets;print(secrets.token_urlsafe(32))" > ~/.vllm_key
cat > ~/start_vllm.sh <<'SH'
#!/bin/sh
exec ~/vllm-env/bin/vllm serve gaunernst/gemma-3-12b-it-int4-awq \
  --revision 3b0c67b98eee8fb90633ef1bfbf3d39f43b9cf9d \
  --max-model-len 4096 --max-num-seqs 1 \
  --host 127.0.0.1 --port 8000 --gpu-memory-utilization 0.90 \
  --api-key "$(cat ~/.vllm_key)"
SH
chmod 700 ~/start_vllm.sh
setsid nohup ~/start_vllm.sh > ~/vllm-serve.log 2>&1 < /dev/null &
# ready when the log shows "Application startup complete" (about 3 minutes, including download and graph capture)
```

vLLM's startup log echoes its arguments, including the API key. Don't copy that log anywhere. The server binds to the instance's loopback only.

From the laptop, open a localhost-only tunnel and point ClipCart at it. Set these in the process environment, never in a committed file:

```sh
ssh -i ~/.ssh/<key>.pem -N -L 127.0.0.1:8002:127.0.0.1:8000 ubuntu@<instance-ip>

FEATURE_STYLE_MEMORY=1 STYLE_MODEL_PROVIDER=openai_compatible \
STYLE_REMOTE_BASE_URL=http://127.0.0.1:8002/v1 STYLE_REMOTE_API_KEY=<key> \
STYLE_REMOTE_MODEL=gaunernst/gemma-3-12b-it-int4-awq \
uvicorn app.main:app --port 8011

# benchmark (each case is one real call; no warm-up)
STYLE_REMOTE_BASE_URL=... STYLE_REMOTE_API_KEY=... STYLE_REMOTE_MODEL=... \
  python scripts/experiments/style_model_bench.py --remote --max-calls 18 --out bench_cases.json
```

## Benchmark

The 18 synthetic statements are the original 10 plus 8 new ones. The new ones cover a correction, a conflict, an ambiguous size, two negations, two purchase-versus-interest cases, and an explicit take-back. Labels are (kind, value, action) and were written before any model call.

Scores are for validated output: what survives the vocabulary check and the verbatim-quote check. Whether the request merely succeeded is not scored. The settings were temperature 0, a 300-token output cap, and JSON requested in the prompt; guided decoding was not used.

| | Rule parser | Gemma 12B int4, hosted |
|---|---|---|
| Precision | 0.94 | 0.76 |
| Recall | 0.68 | 0.73 |
| False positives | 1 | 5 |
| Missed | 7 | 6 |
| Malformed responses | n/a | 0 of 18 |
| Proposals rejected by validation | n/a | 8 |
| Median latency | under 1 ms | 1,017 ms |
| p95 / max latency | | 3,910 / 5,191 ms |
| Tokens (prompt / completion, total) | | 6,366 / 1,012 |
| Largest completion | | 175 tokens; every call stopped naturally |

Server throughput was about 42 to 44 generated tokens per second with one request running.

**What went wrong:**
- **Avoid read as remove (3 cases).** "I never wear leather", "I hate orange" and "Not a fan of black" came back as removing an avoid. Applied blindly, that would delete the shopper's avoid. The fix is to reword the action guidance in the prompt and re-measure.
- **Prompt echo (1 case).** On "No orange please", the model also returned the size, fit and budget examples from the system prompt. All five were rejected because their quotes are not in the shopper's text.
- **Take-back missed or misread (2 cases).** "Actually leather is fine now" became a leather like, and "Please forget that I avoid orange" returned nothing.
- **Purchase read as a preference (1 case).** "I bought a Patagonia fleece for my dad" became a Patagonia like.
- **Unnormalized size (1 case).** "I'm a large" came back with a quote that isn't in the text, so it was rejected and missed.
- **Ambiguous size handled safely.** "Between a small and a medium" produced two invalid size proposals, and both were rejected.

**What went right:** names, body descriptions, negations like "don't mind wool", conflicts, multi-value lists, brands and budgets.

## ClipCart smoke test

This was one real call through the API, against an isolated ClipCart instance on its own port. It used the in-memory database, did not load the `.env` file, and set the provider environment only in the process. The demo server was not touched. See `smoke.json`.

- **Before the call:** health showed the style model as `unverified`, with hosting `remote` and the label "Gemma hosted on Lambda (not local)".
- **The call:** `POST /api/style/notes` returned 200 in 2,176 ms with 357 prompt and 95 completion tokens. It proposed size M, navy as a liked color and polyester as an avoided material, each with a verbatim quote, and none were rejected.
- **Memory:** 0 memories before and 0 after, because notes only propose.
- **After the call:** health showed the style model as `live`, with one successful call.

## Call budget

19 of the 20 authorized inference calls were used: 18 benchmark calls and 1 smoke call. The first benchmark call also served as GPU verification, with no separate warm-up.

## Files

- **`bench_summary.json` and `bench_cases.json`:** benchmark totals, plus per-case predictions, false positives, misses, raw model output, tokens and latency.
- **`smoke.json`:** health before and after, and the note response.
- **`remote_env.txt`, `pip_freeze_vllm_env.txt` and `model_files.txt`:** the OS, GPU and package pins, plus model file names and shard hashes.
