# Devin Feature Eval Harness

Benchmarks the ACU-cost and accuracy impact of Devin features (Playbooks,
Skills, DeepWiki) via controlled A/B experiments of real Devin sessions.
Outputs graphs with 95% bootstrap confidence intervals.

Pipeline: `launch` → `collect` → `grade` → `analyze`.

```
pip install -r requirements.txt
export DEVIN_API_KEY=...       # API key from the org running the eval
export DEVIN_ORG_ID=org-...    # enables exact per-session ACU readings
cp config.example.yaml config.yaml   # fill in repos / playbook ids

python -m harness.launch  --config config.yaml --pilot 3   # small pilot first
python -m harness.collect --watch                          # poll until settled
python -m harness.grade   --config config.yaml
python -m harness.analyze                                  # graphs/ + summary.md
```

Everything is resumable: state lives in `results/runs.jsonl`,
`results/results.jsonl`, `results/graded.jsonl`. Re-running any stage skips
completed work.

---

## One-time setup (step by step, personal org)

### 0. Org & API key
1. In your personal org: Settings → API Keys → create a key. `export DEVIN_API_KEY=...`
2. Grab your org id (`org-...`) from the URL or org settings. `export DEVIN_ORG_ID=...`
3. Verify the org has no knowledge notes that mention the eval repo or tasks
   (Settings → Knowledge) — knowledge auto-injects into all sessions and would
   contaminate control arms.

### 1. Eval target repos (fork of Netflix/dispatch)
1. Fork `Netflix/dispatch` **twice** into your personal GitHub account:
   - `dispatch-eval`        (treatment repo — will get a wiki, skills branch)
   - `dispatch-eval-nowiki` (control repo for the DeepWiki experiment)
   (Two forks because DeepWiki wikis are per-repo; this is the cleanest on/off.)
2. In both forks create a frozen branch from the same commit:
   `git checkout -b eval-frozen <commit> && git push origin eval-frozen`
3. Connect both repos to Devin in your personal org (Settings → Repositories)
   and let the machine/snapshot setup complete so sessions don't burn ACUs on
   environment setup variance. Use the same blueprint for both.

### 2. DeepWiki arms
1. Generate the wiki for `dispatch-eval` only (repo page in Devin → DeepWiki /
   "Generate wiki", or the `generate_wiki` MCP tool). Confirm
   `dispatch-eval-nowiki` has **no** wiki.
2. The `askdevin-prompt` arm needs the harness to query DeepWiki itself: it
   calls the authenticated Devin DeepWiki MCP (`ask_question`) with a
   meta-prompt asking it to *write a grounded implementation prompt* for the
   task, then launches a session with that generated prompt
   (see `harness/deepwiki.py`). Set `private_wiki: true` in config. If you run
   against a public repo's wiki instead, set `private_wiki: false` (uses
   mcp.deepwiki.com, no auth).

### 3. Playbook arm
1. Create a playbook in your personal org from
   `playbooks/dispatch_change_playbook.md`.
2. Put its `playbook-...` id into `config.yaml`.

### 4. Skills arm
1. In `dispatch-eval`, create branch `eval-frozen-skills` from the SAME commit
   as `eval-frozen`, and commit the `skills/example-skills/*` directories to
   `.agents/skills/` on that branch only.
2. The two arms then point at the two branches (identical code, ± skills).

### 5. Seeded-bug task (optional but recommended)
1. Pick a small merged bugfix PR in dispatch history; create branch
   `eval-bug-1` from `eval-frozen` with the fix reverted
   (`git revert --no-edit <fix-commit>`), confirm `pytest` fails, push.
2. Point the `fix-seeded-bug` task at `branch: eval-bug-1` in
   `tasks/dispatch/coding_tasks.yaml`.

### 6. Answer keys / rubrics
- `tasks/dispatch/comprehension_qa.yaml` ships with a verified answer key for
  upstream `Netflix/dispatch` (June 2026). If your frozen commit differs
  significantly, re-verify before running. **Never edit keys after launching.**

### 7. Budget guardrails
- `max_acu_limit` caps every session (default 15 ACU). Full run at defaults
  (3 experiments × ~2-3 tasks × 2-3 arms × 8 reps) ≈ 130-180 sessions ≈
  400-900 ACUs. Pilot (`--pilot 3`) first: ~50-65 sessions.

## Methodology notes (defensibility)
- Arms are interleaved at launch (no time clustering); identical frozen commit,
  identical task wording, identical org/snapshot; sessions are fully
  autonomous (prompts forbid asking the user).
- Primary metrics: `acus_consumed` (exact, from the v3 org API), accuracy
  (pre-registered answer key / hidden test suite), success rate, and
  ACUs-per-successful-task (headline chart).
- Stats: 10k-resample bootstrap 95% CIs; Mann-Whitney U for ACU differences.
  Medians reported alongside means (ACUs are right-skewed).
- All sessions tagged `feature-eval` + experiment/arm/task/rep for audit.
