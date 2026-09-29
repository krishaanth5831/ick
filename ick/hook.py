"""Hook entry point for PostToolUse (Write/Edit) and Stop.

Warn-only for now: a flagged file edit is passed back to Claude as context,
and a flagged reply is shown to the user. Nothing is blocked yet.

Fails open: if ick is off, no judge is set up, or anything goes wrong, the
hook prints nothing and Claude carries on. Errors go to ICK_HOME/hook.log so
they are never silently lost.
"""
import datetime
import json
import os
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ick import config, judge, rules, state, transcript  # noqa: E402

# Kev was trained on states of about 1400 characters; longer text is cut to its start and end.
MAX_CHARS = int(os.environ.get("ICK_MAX_STATE_CHARS", "1400"))


def _written_content(tool_input: dict) -> str:
    if "content" in tool_input:
        return tool_input["content"]
    if "new_string" in tool_input:
        return tool_input["new_string"]
    return "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))


def run(payload: dict):
    """Return the hook's JSON output as a dict, or None to stay silent."""
    if not state.is_on(payload.get("cwd") or os.getcwd()) or not config.jev_url():
        return None
    event = payload.get("hook_event_name")
    path = payload.get("transcript_path")

    if event == "PostToolUse":
        kind = "file"
        content = _written_content(payload.get("tool_input") or {})
    elif event == "Stop" and not payload.get("stop_hook_active"):
        kind = "reply"
        content = transcript.last_assistant_text(path) if path else ""
    else:
        return None

    active = rules.load(kind)
    if payload.get("tool_name") != "Write":
        active = [r for r in active if not r.get("new_files_only")]
    if not content.strip() or not active:
        return None
    request = transcript.last_user_prompt(path) if path else ""
    probs = judge.ask(
        {
            "what_the_user_asked": judge.excerpt(request, MAX_CHARS // 4),
            "what_claude_wrote": judge.excerpt(content, MAX_CHARS),
            "length_in_words": len(content.split()),
        },
        {r["id"]: r["question"] for r in active},
    )
    flagged = [f"{r['id']} ({probs[r['id']]:.0%})" for r in active if probs[r["id"]] >= r["threshold"]]
    # Every judgment is kept so thresholds can later be tuned on real data.
    with (config.home() / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "event": event, "tool": payload.get("tool_name"), "project": payload.get("cwd"),
            "probs": {k: round(v, 3) for k, v in probs.items()}, "flagged": bool(flagged),
        }) + "\n")
    if not flagged:
        return None

    message = "ick flagged possible slop: " + ", ".join(flagged)
    if event == "PostToolUse":
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}
    return {"systemMessage": message}


def main() -> None:
    try:
        out = run(json.load(sys.stdin))
        if out:
            print(json.dumps(out))
    except Exception:
        try:
            log = config.home() / "hook.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as f:
                f.write(f"--- {datetime.datetime.now().isoformat()}\n{traceback.format_exc()}")
        except OSError:
            pass
    sys.exit(0)


if __name__ == "__main__":
    main()
