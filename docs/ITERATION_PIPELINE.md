# HelloMate iteration pipeline

Use this workflow for each feature iteration. It keeps the local worktree,
production host, documentation, and agent memory aligned.

## 1. Recover context

Before changing code, search agent memory for the project topic, deployment
host, recent rollout, and known production caveats.

```text
memory_smart_search("HelloMate <feature>, Contabo deployment, production")
```

Inspect the current worktree and recent commit:

```bash
git status --short
git log -3 --oneline
```

## 2. Implement and verify locally

Keep unrelated user changes untouched. Run focused tests first, then the full
suite and static checks used by CI:

```bash
pytest -q
ruff check app tests scripts
python -m compileall -q app scripts
```

For Mini App changes, also run the repository JavaScript syntax check when
available. Add or update tests for each new state and failure path.

## 3. Commit and push

The owner pushes the verified commit to `origin/main`. Record the commit SHA
before deployment:

```bash
git log -1 --oneline
```

## 4. Deploy to Contabo

Production lives at `/opt/hellomate` on the `contabo` SSH host. First inspect
the remote state. Do not reset or overwrite local production-only files.

```bash
ssh -o BatchMode=yes contabo 'cd /opt/hellomate && git status --short && git log -1 --oneline && docker compose ps'
```

Deploy with a fast-forward-only pull and rebuild:

```bash
ssh -o BatchMode=yes contabo 'cd /opt/hellomate && git pull --ff-only && docker compose up -d --build'
```

If the pull is not fast-forwardable or local changes conflict, stop and inspect
the diff. Never use `git reset --hard` in production without explicit approval.

## 5. Verify production

Confirm the expected commit, running container, Mini App HTTP response, auth
boundary, and recent startup errors:

```bash
ssh -o BatchMode=yes contabo 'cd /opt/hellomate && git log -1 --oneline && docker compose ps && curl -fsS -o /dev/null -w "%{http_code}\\n" http://127.0.0.1:8080/ && curl -sS -o /dev/null -w "%{http_code}\\n" http://127.0.0.1:8080/api/admin/suggestions && docker compose logs --since=2m --tail=120 hellomate'
```

Expected results are: the deployed commit SHA, an `Up` container, HTTP `200`
for `/`, and HTTP `401` for the admin endpoint without Telegram init data.

## 6. Close the iteration

Update the relevant phase document with the feature, tests, deployment SHA,
and verification results. Save the durable operational lesson to agent memory:

```text
memory_save(
  "HelloMate: <feature> deployed to Contabo /opt/hellomate at commit <sha>; verification: <results>. Next iterations use this pipeline and preserve remote production-only changes.",
  concepts="hellomate-deployment,contabo-production,iteration-pipeline,production-verification"
)
```

## Current rollout: processing status

The Mini App now exposes transient contact-reply states `queued`, `generating`,
and `failed`. The status is shared between the Telegram handler and API
in-process, while completed suggestions remain durable in the existing
database. The deployed implementation is commit `7c632b5` (2026-07-21).
