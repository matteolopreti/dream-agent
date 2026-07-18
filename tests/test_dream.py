#!/usr/bin/env python3
"""Offline tests for dream.py. Model is stubbed via an injectable command, so no
network and no `claude` CLI are touched. Plain asserts, no framework.

Run: python3 tests/test_dream.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DREAM = os.path.join(os.path.dirname(HERE), "skills", "dream-agent", "scripts", "dream.py")

SECRET = "sk-ant-api03-SECRETSECRETSECRETSECRET1234567890"

# Stub model: records stdin to $STUB_CAPTURE, emits a valid handoff + one anchored
# candidate. Deliberately never invents a secret.
STUB = r'''import sys, os, json
data = sys.stdin.read()
cap = os.environ.get("STUB_CAPTURE")
if cap:
    with open(cap, "w") as f:
        f.write(data)
print(json.dumps({
    "handoff": "# Handoff\nObjective: fix the JSONL parser\nNext actions: run the test suite\nKey files: scripts/dream.py",
    "candidates": [
        {"claim": "Run the suite with python3 tests/test_dream.py",
         "kind": "lesson", "confidence": 0.7, "source_events": "L1-L2"}
    ]
}))
'''

TRANSCRIPT = [
    {"role": "user", "text": "Please fix the JSONL parser in dream.py"},
    {"role": "assistant", "text": "I will run the suite to verify"},
    {"role": "user", "text": "here is my key " + SECRET + " do not leak it"},
    {"role": "assistant", "text": "Understood, proceeding without it"},
]


def run(args, env=None, cwd=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, DREAM] + args, capture_output=True,
                          text=True, env=e, cwd=cwd)


def setup(tmp):
    stub = os.path.join(tmp, "stub.py")
    open(stub, "w").write(STUB)
    transcript = os.path.join(tmp, "session.jsonl")
    with open(transcript, "w") as f:
        for ev in TRANSCRIPT:
            f.write(json.dumps(ev) + "\n")
    state = os.path.join(tmp, "state")
    return stub, transcript, state


def test_digest_produces_handoff_and_anchored_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        stub, transcript, state = setup(tmp)
        cap = os.path.join(tmp, "capture.txt")
        assert run(["enqueue", "--state-root", state, "--session-id", "S1",
                    "--transcript", transcript]).returncode == 0
        r = run(["digest", "--state-root", state, "--model-cmd",
                 "%s %s" % (sys.executable, stub)], env={"STUB_CAPTURE": cap})
        assert r.returncode == 0, r.stderr

        handoff = open(os.path.join(state, "handoff.md")).read()
        assert "Objective" in handoff, "handoff.md missing body"
        for stampkey in ("project:", "branch:", "commit:", "session_id: S1", "timestamp:"):
            assert stampkey in handoff, "handoff.md missing stamp %r" % stampkey

        cands = [json.loads(l) for l in
                 open(os.path.join(state, "candidates.jsonl")).read().splitlines() if l.strip()]
        assert len(cands) >= 1, "expected >=1 candidate"
        c = cands[0]
        assert c["source_session"] == "S1" and c["source_events"], "candidate lacks evidence anchors"
        print("PASS (a) digest -> handoff.md + anchored candidate")


def test_validate_rejects_missing_anchors():
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "state")
        os.makedirs(state)
        bad = {"claim": "x", "kind": "lesson", "project": "p", "source_session": "S1",
               "source_events": "", "observed_at": "t", "confidence": 0.5,
               "status": "proposed", "supersedes": None, "expires_at": None}
        open(os.path.join(state, "candidates.jsonl"), "w").write(json.dumps(bad) + "\n")
        r = run(["validate", "--state-root", state])
        assert r.returncode == 1, "validate should exit 1 on missing anchors"
        assert "evidence anchors" in r.stdout, r.stdout
        print("PASS (b) validate exits 1 on candidate missing anchors")


def test_recover_stale_on_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        stub, transcript, state = setup(tmp)
        run(["enqueue", "--state-root", state, "--session-id", "S1", "--transcript", transcript])
        run(["digest", "--state-root", state, "--model-cmd", "%s %s" % (sys.executable, stub)],
            env={"STUB_CAPTURE": os.path.join(tmp, "cap.txt")})

        stamp = {}
        for line in open(os.path.join(state, "handoff.md")).read().splitlines():
            if line.startswith(("branch:", "commit:")):
                k, v = line.split(":", 1)
                stamp[k.strip()] = v.strip()

        match = run(["recover", "--state-root", state, "--branch", stamp["branch"],
                     "--commit", stamp["commit"]])
        assert match.returncode == 0 and "Objective" in match.stdout, "match should print body"

        miss = run(["recover", "--state-root", state, "--branch", "other-branch",
                    "--commit", "deadbeefdeadbeef"])
        assert miss.returncode == 0, "recover must exit 0 (fail-open)"
        assert "STALE" in miss.stdout, "mismatch should print STALE"
        assert "Objective" not in miss.stdout, "STALE must NOT leak handoff body"
        print("PASS (c) recover prints STALE on branch/commit mismatch, hides body")


def test_enqueue_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        _, transcript, state = setup(tmp)
        run(["enqueue", "--state-root", state, "--session-id", "S1", "--transcript", transcript])
        run(["enqueue", "--state-root", state, "--session-id", "S1", "--transcript", transcript])
        jobs = [l for l in open(os.path.join(state, "queue.jsonl")).read().splitlines() if l.strip()]
        assert len(jobs) == 1, "same session+cursor twice must produce ONE job, got %d" % len(jobs)
        print("PASS (d) enqueue idempotent by (session_id, cursor)")


def test_secret_never_propagates():
    with tempfile.TemporaryDirectory() as tmp:
        stub, transcript, state = setup(tmp)
        cap = os.path.join(tmp, "capture.txt")
        run(["enqueue", "--state-root", state, "--session-id", "S1", "--transcript", transcript])
        run(["digest", "--state-root", state, "--model-cmd", "%s %s" % (sys.executable, stub)],
            env={"STUB_CAPTURE": cap})

        for name in ("handoff.md", "candidates.jsonl"):
            body = open(os.path.join(state, name)).read()
            assert SECRET not in body, "secret leaked into %s" % name
        model_input = open(cap).read()
        assert SECRET not in model_input, "secret reached the model command input"
        # sanity: the model DID receive the non-secret lines (filter is not a blackhole)
        assert "JSONL parser" in model_input, "non-secret content wrongly dropped"
        print("PASS (e) planted sk-ant secret never reaches handoff/candidates/model input")


if __name__ == "__main__":
    tests = [
        test_digest_produces_handoff_and_anchored_candidate,
        test_validate_rejects_missing_anchors,
        test_recover_stale_on_mismatch,
        test_enqueue_idempotent,
        test_secret_never_propagates,
    ]
    for t in tests:
        t()
    print("\nAll %d tests passed." % len(tests))
