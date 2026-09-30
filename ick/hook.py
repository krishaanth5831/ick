"""Hook entry point for UserPromptSubmit, PostToolUse (Write/Edit) and Stop.

- UserPromptSubmit: prevention. Tells Claude the user's slop rules before it
  answers. Needs no judge.
- PostToolUse: a flagged file edit is passed back to Claude as context.
- Stop: a flagged reply is shown to the user (ICK_MODE=warn, the default), or
  sent back to Claude to revise once (ICK_MODE=block).

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


def _project(payload: dict) -> str:
    """The session's project root. The payload cwd drifts when Claude changes directory."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def _prevent() -> dict:
    lines = [f"- {r.get('avoid') or r['question']}" for r in rules.load("file") + rules.load("reply")]
    context = (
        "The user runs ick, a slop filter. These are things this user has pushed back on before. "
        "Avoid them in this reply and in any files you write:\n" + "\n".join(lines)
    )
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}


def _question(rule: dict):
    if "criteria" in rule:
        return {"instructions": rule["question"], "criteria": rule["criteria"]}
    return rule["question"]


def run(payload: dict):
    """Return the hook's JSON output as a dict, or None to stay silent."""
    if not state.is_on(_project(payload)):
        return None
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        return _prevent()
    if not config.jev_url():
        return None
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
        {r["id"]: _question(r) for r in active},
    )
    hits = [r for r in active if probs[r["id"]] >= r["threshold"]]
    # Every judgment is kept so thresholds can later be tuned on real data.
    with (config.home() / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "event": event, "tool": payload.get("tool_name"), "project": _project(payload),
            "probs": {k: round(v, 3) for k, v in probs.items()}, "flagged": bool(hits),
        }) + "\n")
    if not hits:
        return None

    names = ", ".join(f"{r['id']} ({probs[r['id']]:.0%})" for r in hits)
    fixes = "\n".join(f"- {r.get('avoid') or r['question']}" for r in hits)
    if event == "PostToolUse":
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                       "additionalContext": f"ick flagged possible slop: {names}. The user wants:\n{fixes}"}}
    if os.environ.get("ICK_MODE", "warn") == "block":
        return {"decision": "block",
                "reason": f"ick flagged your last reply as possible slop ({names}). Rewrite it so that:\n{fixes}"}
    return {"systemMessage": f"ick flagged possible slop: {names}"}


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
