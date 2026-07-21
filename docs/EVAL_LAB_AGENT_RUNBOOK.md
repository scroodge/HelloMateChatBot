# Eval Lab agent runbook

Use this runbook whenever a task can change the quality or safety of generated
HelloMate replies: prompt text, context assembly, privacy/openness rules,
reply sanitising, provider adapters, model configuration, or generation
parameters.

## Required offline gate

Run this before handoff. It uses checked-in synthetic fixtures only and never
calls a live model:

```bash
python scripts/run_eval.py \
  --dataset evals/datasets/regression.jsonl \
  --provider fixture \
  --output-json /tmp/hellomate-eval.json \
  --output-report /tmp/hellomate-eval.md
```

The process must exit `0`. Read the Markdown report and include the result in
the handoff. A failure means the proposed change is not ready. Do not remove,
relax, or rewrite a case merely to pass it; add a new case when it captures a
real missing behavior.

CI runs this exact gate for every push and pull request. It is therefore
automatic once the code is pushed.

## Production live evaluation (Contabo)

Run this only when the user has requested a model/provider/prompt comparison
or authorized live inference. It can use paid API credentials or local model
capacity.

From the Contabo host, enter the running container first:

```bash
cd /opt/hellomate
docker compose exec hellomate sh
```

Inside the container (normally `/app $`), run the following. Each `\` must be
the final character on its line; the `>` continuation prompt is expected.

```bash
python scripts/run_eval.py \
  --dataset evals/datasets/regression.jsonl \
  --provider "$LLM_PROVIDER" \
  --model "$LLM_MODEL" \
  --base-url "$LLM_BASE_URL" \
  --api-key "$LLM_API_KEY" \
  --prompt-version contabo-live \
  --output-json /tmp/hellomate-live.json \
  --output-report /tmp/hellomate-live.md
```

After the run completes, type `exit`. Back on the Contabo host, copy each
report with one complete command per line:

```bash
mkdir -p /opt/hellomate/evals/reports
docker cp hellomate-bot:/tmp/hellomate-live.md /opt/hellomate/evals/reports/contabo-live.md
docker cp hellomate-bot:/tmp/hellomate-live.json /opt/hellomate/evals/reports/contabo-live.json
sed -n '1,16p' /opt/hellomate/evals/reports/contabo-live.md
```

Do not split a `docker cp` destination across two terminal lines. Reports are
private and Git-ignored at `evals/reports/`.

## Interpreting results

- A fixture run validates the evaluator and the checked-in regression data. It
  has zero model latency and token usage; it is not a model-quality result.
- A live run must name a real provider/model and report non-zero latency and
  token usage. It measures that configured model against the same 50 cases.
- A non-zero runner exit means at least one hard safety failure or a pass rate
  below the configured threshold.
- Hard failures for language, excessive length, AI/meta leakage, missing
  clarification, private disclosure, and unsupported commitments always block
  the candidate; high style scores never cancel them out.
- JSON contains the per-case reply, scores, latency, and token usage. Markdown
  is the concise handoff report.

## Verified Contabo baseline — 2026-07-21

The first live baseline completed successfully against `ollama/qwen2.5:14b`:

| Cases | Pass rate | Hard failures | Mean latency | Tokens in/out |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 46% | 10 | 1233.6 ms | 13,423 / 1,599 |

The evaluator, report generation, and production container are working. This
model/prompt candidate does **not** pass the safety gate: failures include
mixed-language output, AI-assistant self-disclosure, missing clarification,
and excessive length. No production routing or model decision follows from
this baseline.

## Privacy rules

- Only synthetic data belongs in Git under `evals/datasets/`.
- Put owner-approved holdout data under `evals/owner_approved/`; it is ignored.
- Keep reports in ignored `evals/reports/` unless the owner explicitly approves
  a sanitized report for publication.
- Never paste raw owner-approved conversations into an issue, commit, CI log,
  or agent handoff.
