# dream-agent

Cross-session memory for Claude Code — the "dream agent" idea, engineered the safe way.

At session boundaries, a cheap model digests what the session actually did into three typed
channels: a **handoff** (replaceable, stamped with branch + commit, refused when stale), **lessons**,
and **long-term memory candidates**. Every candidate carries evidence anchors (session ID +
transcript line spans) or is rejected. Nothing is hidden, nothing writes your knowledge base by
itself — promotion into durable memory stays a human-reviewed step.

The design was fixed by a blind three-lineage review panel (Claude / GPT / Gemini) before a line
was written. What the panel killed, this plugin deliberately does **not** do: no continuous raw
transcript dump (Claude Code already persists transcripts), no hidden privileged agent (an
unauditable memory writer is a poisoning amplifier), no automatic long-term writes.

## Install

```
/plugin marketplace add matteolopreti/dream-agent
/plugin install dream-agent@dream-agent
```

Then wire the session hooks (the plugin never edits your settings itself): copy the block from
[`skills/dream-agent/references/install.md`](skills/dream-agent/references/install.md) into
`~/.claude/settings.json`.

## How it works

- **SessionEnd** → `dream.py enqueue`: appends one idempotent job (session, transcript path,
  branch, commit). Enqueue-only — fits the hook budget, never blocks termination.
- **SessionStart** → `dream.py hook recover`: finishes any abandoned job (the cheap-model digest
  runs here), then prints the handoff **only if** its branch/commit stamp matches — otherwise one
  `STALE:` line.
- **Digest**: secret-pattern lines are stripped *before* the model call; output is `handoff.md`
  (atomic replace) + `candidates.jsonl` (`status: proposed`, evidence anchors mandatory —
  `validate` rejects the rest).
- **Promotion**: you (or your review process) move worthy candidates into your knowledge base
  through whatever guard path it already has. The plugin stops at the proposal.

Offline test suite: `python3 tests/test_dream.py` (model stubbed; includes a planted-secret case).

## License

MIT
