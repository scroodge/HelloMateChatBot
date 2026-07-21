# HelloMate Eval Lab

Phase 19 makes prompt, context, and provider changes measurable before they reach production.

`datasets/regression.jsonl` is checked in and contains synthetic cases only. It follows the provider-neutral schema in `docs/PHASE_18_24_PLAN.md`; `fixture_reply` is a deliberately checked-in synthetic response used only by the offline CI provider. `expected_properties` supports `max_length:N`, `contains:text`, and `requires_clarification`; `forbidden_properties` supports `forbid:text`.

Owner-approved cases belong in `evals/owner_approved/`, which is ignored by Git. Keep a contact exclusively in either development/regression or holdout data; never move a real contact into a checked-in fixture.

Run the deterministic synthetic gate (the same command CI runs):

```bash
python scripts/run_eval.py \
  --dataset evals/datasets/regression.jsonl \
  --provider fixture \
  --output-json /tmp/hellomate-eval.json \
  --output-report /tmp/hellomate-eval.md
```

Run a model locally, optionally comparing a prompt file or another provider:

```bash
python scripts/run_eval.py \
  --dataset evals/datasets/regression.jsonl \
  --provider ollama --model llama3.2 --base-url http://localhost:11434 \
  --prompt-version candidate-a --prompt-file prompts/candidate-a.txt \
  --compare-provider openai --compare-model gpt-4o-mini --compare-base-url https://api.openai.com --compare-api-key "$LLM_API_KEY" \
  --judge-provider openai --judge-model gpt-4o-mini --judge-base-url https://api.openai.com --judge-api-key "$LLM_API_KEY" \
  --output-json evals/reports/candidate-a.json --output-report evals/reports/candidate-a.md
```

The JSON artifact contains every reply, per-case score, hard safety failures, latency, and token usage. A hard failure (language, AI/meta leakage, required clarification, reserved privacy, unsupported commitment, or length) always fails the run and is not averaged away. `--judge-provider` adds model-assisted scores and reasons for accuracy/helpfulness, groundedness, style/persona, privacy boundary, and comparison to the reference reply. Keep judge runs local and use owner-approved cases only with `--allow-owner-approved`.

For the verified Contabo procedure, live-result interpretation, and privacy
rules, see [`docs/EVAL_LAB_AGENT_RUNBOOK.md`](../docs/EVAL_LAB_AGENT_RUNBOOK.md).
