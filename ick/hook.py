"""Hook entry point for UserPromptSubmit, PostToolUse (Write/Edit) and Stop.

- UserPromptSubmit: prevention. Tells Claude the user's slop rules before it
  answers. Kev reads the (short) prompt to decide which topic rules apply.
- PostToolUse: mid-task feedback. Checks each file Claude writes and tells
  Claude about problems before its next step.
- Stop: checks the finished reply. Rules marked "block" send Claude back to
  fix the offending part once; other hits are shown to the user.

Kev is only asked what it has been measured to answer well: questions about
the user's short prompt, and questions about one paragraph of a reply. Rules
without a validated check are prevention-only.

Fails open: if ick is off, the judge is down, or anything goes wrong, the hook
prints nothing (or, for prevention, sends every rule) and Claude carries on.
Errors go to ICK_HOME/hook.log so they are never silently lost.
"""
import datetime
import json
import os
import pathlib
import re
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ick import config, judge, rules, state, transcript  # noqa: E402

DOC_SUFFIXES = {".md", ".txt", ".log", ".rst", ".pdf", ".docx"}
FILE_ASKED = "Did the user ask Claude to create, write or save a file, document or report?"
NEXT_ACTION = re.compile(r"^\W*(next action|next step)s?\b", re.I)


def _log_error() -> None:
    try:
        log = config.home() / "hook.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(f"--- {datetime.datetime.now().isoformat()}\n{traceback.format_exc()}")
    except OSError:
        pass


def _project(payload: dict) -> str:
    """The session's project root. The payload cwd drifts when Claude changes directory."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def _question(rule: dict):
    if "criteria" in rule:
        return {"instructions": rule["question"], "criteria": rule["criteria"]}
    return rule["question"]


def paragraphs(text: str) -> list:
    """Paragraphs of a reply with fenced code removed, so code never trips a check."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def part_of(text: str, part: str) -> str:
    ps = paragraphs(text)
    if not ps:
        return ""
    if part == "end":
        return ps[-1]
    if part == "start":
        return ps[0]
    return "\n\n".join(ps)


def _log(payload: dict, event: str, **fields) -> None:
    with (config.home() / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "event": event, "tool": payload.get("tool_name"), "project": _project(payload), **fields,
        }) + "\n")


# --- prevention ---------------------------------------------------------------

def _route(prompt: str, candidates: list) -> dict:
    """Ask Kev which topic rules this prompt is about. Returns {rule id: probability}."""
    questions = {r["id"]: r["when"] for r in candidates}
    return judge.ask({"user_request": prompt[:1200]}, questions,
                     timeout=float(os.environ.get("ICK_ROUTE_TIMEOUT", "2")))


def _carry_path():
    return config.home() / "last_hits.json"


def _remember(payload: dict, hits: list) -> None:
    """Keep this reply's hits so the next prompt in the same session can warn Claude."""
    path = _carry_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data[payload.get("session_id", "")] = [r.get("avoid") or r["question"] for r in hits]
    path.write_text(json.dumps(data))


def _recall(payload: dict) -> list:
    path = _carry_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    lines = data.pop(payload.get("session_id", ""), [])
    path.write_text(json.dumps(data))
    return lines


def _prevent(payload: dict) -> dict:
    active = rules.load("file") + rules.load("reply")
    routed = [r for r in active if r.get("when")]
    probs, skipped = {}, []
    if routed and config.jev_url():
        try:
            probs = _route(payload.get("prompt", ""), routed)
            skipped = [r["id"] for r in routed if probs[r["id"]] < r.get("when_threshold", 0.45)]
        except Exception:
            _log_error()  # judge down or slow: send every rule
    sent = [r for r in active if r["id"] not in skipped]
    _log(payload, "UserPromptSubmit", sent=[r["id"] for r in sent], skipped=skipped,
         route={k: round(v, 3) for k, v in probs.items()})
    lines = [f"- {r.get('avoid') or r['question']}" for r in sent]
    context = (
        "The user runs ick, a slop filter. These are things this user has pushed back on before. "
        "Avoid them in this reply and in any files you write:\n" + "\n".join(lines)
    )
    missed = _recall(payload)
    if missed:
        context += "\n\nYour previous reply broke these rules. Do not do it again:\n" + "\n".join(f"- {m}" for m in missed)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}


# --- checks -------------------------------------------------------------------

def _code_check(name: str, text: str) -> bool:
    if name == "em_dash":
        return "—" in "\n\n".join(paragraphs(text))
    if name == "next_action_line":
        ps = paragraphs(text)
        return bool(ps) and bool(NEXT_ACTION.match(ps[-1]))
    return False


def _check_file(payload: dict, path: str) -> list:
    """Mid-task: a new document file the prompt never asked for."""
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path", "")
    if payload.get("tool_name") != "Write" or pathlib.Path(target).suffix.lower() not in DOC_SUFFIXES:
        return []
    candidates = [r for r in rules.load("file") if "doc_not_requested" in r.get("checks", [])]
    if not candidates or not config.jev_url():
        return []
    prompt = transcript.last_user_prompt(path) if path else ""
    p = judge.ask({"user_request": prompt[:1200]}, {"asked": FILE_ASKED})["asked"]
    hits = [r for r in candidates if p < r.get("threshold", 0.6)]  # low = the user did not ask for a file
    _log(payload, "PostToolUse", file=target, asked_for_file=round(p, 3), flagged=[r["id"] for r in hits])
    return hits


def _check_reply(payload: dict, path: str) -> tuple:
    text = transcript.last_assistant_text(path) if path else ""
    if not text.strip():
        return [], {}
    active = rules.load("reply")
    hits, probs = [], {}
    for r in active:
        if any(_code_check(c, text) for c in r.get("checks", [])):
            hits.append(r)
    judged = [r for r in active if r.get("judge") and r not in hits]
    if judged and config.jev_url():
        for part in {r.get("part", "whole") for r in judged}:
            group = [r for r in judged if r.get("part", "whole") == part]
            piece = part_of(text, part)
            if not piece:
                continue
            probs.update(judge.ask({"closing_text" if part == "end" else "text": piece[:700]},
                                   {r["id"]: _question(r) for r in group}))
        hits += [r for r in judged if r["id"] in probs and probs[r["id"]] >= r["threshold"]]
    _log(payload, "Stop", probs={k: round(v, 3) for k, v in probs.items()}, flagged=[r["id"] for r in hits])
    return hits, probs


def _should_block(hits: list) -> bool:
    mode = os.environ.get("ICK_MODE", "")
    if mode == "warn":
        return False
    if mode == "block":
        return bool(hits)
    return any(r.get("action") == "block" for r in hits)


def run(payload: dict):
    """Return the hook's JSON output as a dict, or None to stay silent."""
    if not state.is_on(_project(payload)):
        return None
    event = payload.get("hook_event_name")
    path = payload.get("transcript_path")

    if event == "UserPromptSubmit":
        return _prevent(payload)

    if event == "PostToolUse":
        hits = _check_file(payload, path)
        if not hits:
            return None
        fixes = "\n".join(f"- {r.get('avoid') or r['question']}" for r in hits)
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                f"ick: the user did not ask for this file. Unless it is really needed, delete it and give the content in chat instead.\n{fixes}"}}

    if event == "Stop" and not payload.get("stop_hook_active"):
        hits, _ = _check_reply(payload, path)
        if not hits:
            return None
        _remember(payload, hits)
        names = ", ".join(r["id"] for r in hits)
        fixes = "\n".join(f"- {r.get('avoid') or r['question']}" for r in hits)
        if _should_block(hits):
            return {"decision": "block", "reason": (
                f"ick flagged your last reply ({names}). Fix only the part that breaks these rules. "
                f"Do not repeat or rewrite the rest of the reply; if the fix is to drop something, just say nothing more.\n{fixes}")}
        return {"systemMessage": f"ick flagged possible slop: {names}"}
    return None


def main() -> None:
    try:
        out = run(json.load(sys.stdin))
        if out:
            print(json.dumps(out))
    except Exception:
        _log_error()
    sys.exit(0)


if __name__ == "__main__":
    main()
