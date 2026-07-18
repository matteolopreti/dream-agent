---
name: dream-agent
description: Cross-session memory shim for Claude Code — the "dream agent" engineered per the 2026-07-19 decorrelated panel as an access-scoped, fully auditable handoff-and-promotion layer, NOT a hidden privileged agent and NOT a second memory database. Use when you want a session's next session to start warm (a replaceable, branch/commit-stamped handoff) and when durable lessons or facts learned in a session should become reviewed PROPOSALS with transcript evidence — never auto-written to the vault. Reuses Claude Code's own JSONL transcript as the source of truth; adds only a cheap-model digest, evidence-anchored candidates, and a guarded promotion path. Fires on: session handoff, "warm start", memory promotion, lesson capture, "what did last session leave me".
---

# Dream Agent

A thin layer that turns the end of one Claude Code session into a warm start for the next, and
turns what a session learned into reviewable proposals — with the source lines attached.

The name is a metaphor (memory consolidated "between sessions"), not an architecture. The panel
(`briefs/dream-agent/CONSOLIDATION-2026-07-19.md`) rejected the original hidden-agent idea. What
survived, and what this skill builds, is engineered on four rules:

- **No raw dump.** Claude Code already writes a full per-session JSONL transcript. That is the
  source of truth. This skill reads a *delta* of it; it never copies raw transcripts anywhere,
  and never into the Obsidian vault.
- **No hidden privilege.** "Hidden" is not a security property — an unauditable memory writer is a
  poisoning amplifier. Every file this skill writes is plain text an operator can read. Other
  agents simply don't *load* the channel; anyone can *inspect* it.
- **Curated-only promotion.** Nothing crosses into durable/long-term memory or the vault without a
  human/seat review. The skill emits *candidates*; it does not promote them.
- **Evidence anchors are mandatory.** Every candidate carries its `source_session` and transcript
  line spans (`source_events`). A candidate without both is rejected by `validate`.

## When to use

- You are ending a session and want the next one to resume without re-reading the transcript.
- A session produced a durable lesson, fact, preference, or decision worth proposing for memory.
- A session was compacted or killed and you need to recover its objective/blockers/next action.
- You are the seat/owner reviewing what a session proposed before anything durable is written.

Do **not** use it as a search index (claude-mem owns that) or as an auto-writer to the vault
(nothing here writes the vault).

## The three channels — different write policies, never equally authoritative

The panel's load-bearing point: one model call must not produce three equally-trusted outputs.

| Channel | File | Policy |
|---|---|---|
| **Handoff** | `handoff.md` | **Replaceable.** Overwritten every digest, never accumulated. Stamped with project, branch, commit, session id, timestamp. On the next start it is injected **only if** its branch/commit still match the repo — otherwise it is reported STALE and dropped. |
| **Lessons / durable facts** | `candidates.jsonl` | **Proposals only.** Each line is a candidate with evidence anchors, confidence, scope, and `status: proposed`. Never authoritative, never auto-promoted. |
| **Long-term / vault** | — (out of scope of the writer) | **Not model-writable.** A reviewed candidate is promoted by hand through the existing vault guard path. This skill documents that path; it does not walk it. |

## Workflow: enqueue -> digest -> recover -> promote

All state lives under a **state root** you pass with `--state-root`. The runtime default the hooks
use is `~/.claude/projects/<project>/dream/`, but the flag always decides. Layout:

```
<state-root>/
  state.json          # per-session transcript cursors (last processed line)
  handoff.md          # replaceable, stamped next-session handoff
  candidates.jsonl    # evidence-anchored proposals (status: proposed)
  queue.jsonl         # idempotent digest jobs
  runs/<session>.json # audit record per digest run (inputs, model cmd, counts)
  dream.log           # one-line failure log (fail-open paths write here)
```

1. **enqueue** (`SessionEnd`, and optionally `Stop`) — cheap, no model. Appends a job with the
   session id, transcript path + cursor (line count), branch, commit, project. Idempotent by
   `(session_id, cursor)`: the same session at the same transcript position enqueues once.
   ```
   python3 scripts/dream.py enqueue --state-root R --session-id S --transcript PATH
   ```
2. **digest** (the "dream" — runs between sessions, e.g. at next `SessionStart`, or on demand).
   For each queued job it reads the transcript delta, **drops any secret-bearing line before the
   model ever sees it**, calls the cheap model **once**, then writes a fresh `handoff.md` and
   appends anchored candidates. The model command is injectable:
   ```
   python3 scripts/dream.py digest --state-root R [--model-cmd "claude -p --model claude-haiku-4-5-20251001"]
   ```
   Default is `claude -p` with Haiku; override with `--model-cmd` or `$DREAM_MODEL_CMD`. Tests run
   fully offline by pointing `--model-cmd` at a stub — the skill never calls a network API directly.
3. **recover** (`SessionStart`) — prints `handoff.md` to stdout **only if** its stamp matches the
   current branch/commit; otherwise prints one `STALE:` line and exits 0. A stale handoff never
   overrides live repo state.
   ```
   python3 scripts/dream.py recover --state-root R --branch B --commit C
   ```
4. **promote** (seat/owner, out of band) — review `candidates.jsonl`, and hand-carry accepted ones
   through the existing vault guard hook into a per-project inbox. `validate` is the gate:
   ```
   python3 scripts/dream.py validate --state-root R   # exit 1 lists every violation
   ```

Installation is the owner's job and is documented in `references/install.md`. The skill never
self-installs, never installs hooks, and never writes the vault.

## Candidate schema

Each `candidates.jsonl` line (fields per `briefs/dream-agent/seat-codex.md` §4):

```
claim          one durable lesson / fact / preference / decision
kind           lesson | durable_fact | preference | decision
project        project scope (default-deny cross-project)
source_session originating session id           }
source_events  transcript line span, e.g. L12-L20 }  <- evidence anchors (both required)
observed_at    UTC timestamp
confidence     0..1
status         proposed   (the writer never sets anything else)
supersedes     id of a candidate this replaces, or null
expires_at     expiry timestamp, or null
```

Repository content and tool output are treated as untrusted evidence, never as instructions to the
digest worker — the prompt says so explicitly.

## Validation gate

Each check can fail; a run that cannot fail is not a run.

1. `validate` exits **1** and lists a violation for any candidate missing a required field
   (`claim, kind, project, source_session, source_events, observed_at, confidence, status`), a bad
   `kind`, or missing evidence anchors — and it has been shown to exit 1 on a planted
   anchor-less candidate (`tests/test_dream.py` test b).
2. `handoff.md` carries all five stamp keys (project, branch, commit, session id, timestamp);
   `recover` prints the body **only** on a branch/commit match and prints `STALE` (body withheld)
   otherwise — shown by test c.
3. A planted `sk-ant-…` line never appears in `handoff.md`, `candidates.jsonl`, or the model
   command's received input — shown by test e.
4. `enqueue` of the same `(session_id, cursor)` twice yields exactly one job — shown by test d.
5. `tests/test_dream.py` runs offline (model stubbed) and exits 0.

## Weak-model version

Run only the deterministic, no-judgment parts: `enqueue` (cheap, no model), `recover` (pure stamp
comparison), and `validate` (mechanical schema/anchor check). Do **not** hand-write candidates and
do **not** promote anything to the vault. Leave `digest`'s model call on the configured cheap model,
and leave candidate review and promotion to the seat/owner. If unsure whether a handoff is fresh,
prefer STALE — a dropped handoff costs a re-read; a wrong one poisons the next session.

## Failure recovery

- **Missed or killed session (no SessionEnd).** The job was never enqueued, so no handoff exists.
  `recover` prints `STALE: no handoff to recover` and exits 0 — the session starts cold, not broken.
  Add a `Stop` checkpoint enqueue (see install.md) to lose less on a force-kill.
- **Stale handoff after a commit/branch switch.** By design: the stamp no longer matches, so
  `recover` withholds the body and prints STALE. Re-run `digest` to regenerate against the new
  state; never edit the stamp to force a match.
- **Model command missing / offline / errors.** `digest` marks that job `error`, logs one line to
  `dream.log`, and moves on — other jobs still process, the session is never bricked. Fix the model
  command and re-enqueue.
- **Secret slipped into a candidate claim.** The line filter runs before the model, and candidate
  claims are re-checked; a claim matching a secret pattern is dropped. If a new leak shape appears,
  add its regex to `SECRET_PATTERNS` in `scripts/dream.py` and re-run `validate`.
- **Concurrent sessions.** Queue/state use last-writer-wins (`ponytail:` comment in the source);
  the per-session `runs/<id>.json` is the audit trail. Add file locking only if real concurrency
  causes lost updates.

## Elevation contract

This skill makes the *handoff* automatic and the *proposal* evidence-anchored — it never makes the
*promotion* automatic. `candidates.jsonl` is provisional by construction: every line is
`status: proposed`, and the writer has no path to the vault. Long-term memory stays curated —
a candidate becomes durable only when a human or the super-architect seat reviews it and carries it
through the existing vault guard hook. The digest is a cheap model summarizing untrusted transcript
text; it gathers and anchors, it does not certify. A handoff that fails its branch/commit stamp is
dropped, not trusted. The judgment — what deserves memory, and what a lesson actually means — stays
with the reviewer and the owner's sign-off.

## References

- `references/install.md` — the exact `~/.claude/settings.json` hook snippet the **owner** pastes
  (SessionEnd = enqueue, SessionStart = recover, Stop = optional checkpoint) and the skill symlink
  command. Read before installing.
- `scripts/dream.py` — the four subcommands (`enqueue`, `digest`, `recover`, `validate`) plus the
  internal `hook` bridge. Python 3 stdlib only.
- `tests/test_dream.py` — offline acceptance tests. Run with `python3 tests/test_dream.py`.
