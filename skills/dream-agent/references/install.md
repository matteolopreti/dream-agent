# Installing dream-agent (owner-only)

**The skill never self-installs.** It installs no hooks, edits no settings, and writes nothing to
`~/.claude` or the vault on its own. You — the owner — do the two steps below by hand. Fail-open by
design: every hook command below exits 0 even on error, so a broken script can never brick a session.

Assumes the repo lives at `~/Claude/Skills/dream-agent`. Adjust paths if not.

## Step 1 — Symlink the skill so Claude Code can discover it

```sh
ln -s ~/Claude/Skills/dream-agent ~/.claude/skills/dream-agent
```

That is the only thing that touches `~/.claude/skills`. (Directory must exist; `mkdir -p ~/.claude/skills` first if needed.)

## Step 2 — Add the hooks to `~/.claude/settings.json`

Merge this `hooks` block into your existing `settings.json` (don't clobber other hooks). The
commands call the internal `hook` bridge, which reads Claude Code's hook JSON from stdin
(`session_id`, `transcript_path`, `cwd`), derives the per-project state root
`~/.claude/projects/<project>/dream/`, and dispatches — all fail-open.

```json
{
  "hooks": {
    "SessionEnd": [
      { "hooks": [
        { "type": "command",
          "command": "python3 ~/.claude/skills/dream-agent/skills/dream-agent/scripts/dream.py hook enqueue" }
      ] }
    ],
    "SessionStart": [
      { "hooks": [
        { "type": "command",
          "command": "python3 ~/.claude/skills/dream-agent/skills/dream-agent/scripts/dream.py hook recover" }
      ] }
    ],
    "Stop": [
      { "hooks": [
        { "type": "command",
          "command": "python3 ~/.claude/skills/dream-agent/skills/dream-agent/scripts/dream.py hook checkpoint" }
      ] }
    ]
  }
}
```

What each hook does:

- **SessionEnd → `hook enqueue`** — cheap, no model. Appends one idempotent digest job (session id,
  transcript path + cursor, branch, commit, project). Finishes well inside the hook budget. This is
  the *only* work done at session end — the model call is deliberately not here.
- **SessionStart → `hook recover`** — first finishes any queued job from a prior session by running
  `digest` (this is where the cheap-model "dream" actually runs, so an abandoned/killed session gets
  consolidated on the next start), then prints `handoff.md` to stdout **only if** its branch/commit
  stamp still matches the current repo. A mismatch prints one `STALE:` line and injects nothing.
- **Stop → `hook checkpoint`** *(optional)* — enqueues a checkpoint after a turn so a force-killed
  terminal loses less. Idempotent by transcript cursor, so it will not pile up duplicate jobs.

### Note on the SessionStart model call

`hook recover` runs `digest` before printing, so the cheap-model call happens at session start. That
is the pragmatic MVP trigger — the panel's SessionStart step is explicitly "finish any abandoned
prior job, then recover." If you prefer zero startup latency, drop `digest` out of the start path and
run it out of band instead (nightly cron or manual):

```sh
python3 ~/.claude/skills/dream-agent/skills/dream-agent/scripts/dream.py digest \
  --state-root ~/.claude/projects/<project>/dream
```

(The `recover` subcommand alone does not run the model — only the `hook recover` bridge chains
`digest` before it.)

## Step 3 — Review and promote (curated, never automatic)

Nothing crosses into durable memory or the vault automatically. Periodically:

```sh
R=~/.claude/projects/<project>/dream
python3 ~/.claude/skills/dream-agent/skills/dream-agent/scripts/dream.py validate --state-root "$R"   # gate: exit 1 on any bad candidate
cat "$R/candidates.jsonl"                                                           # review proposals
```

Accepted candidates are hand-carried through your existing vault **guard hook** into a per-project
inbox (e.g. `<vault>/Dream Inbox/<project>/`). The guard hook approves, rejects, or normalizes the
write — dream-agent does not write the vault and has no path to it.

## Uninstall

```sh
rm ~/.claude/skills/dream-agent            # remove the symlink
# then delete the three hook entries from ~/.claude/settings.json
# state files (if you want them gone): rm -rf ~/.claude/projects/*/dream
```
