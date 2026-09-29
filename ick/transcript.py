"""Reading Claude Code transcripts (~/.claude/projects/*/*.jsonl).

The format is not a documented API, so every reader here skips lines it
doesn't understand instead of failing.
"""
import json
import re

# User messages that come from the harness, not from a person reacting.
NOISE = re.compile(
    r"^\s*(<local-command-caveat>|<command-name>|<command-message>|<local-command-stdout>"
    r"|<system-reminder>|<task-notification>|Caveat: The messages below)"
)
DENIAL = re.compile(r"doesn't want to proceed|was rejected|user denied", re.I)


def _entries(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not d.get("isSidechain"):
                yield d


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if b.get("type") == "text")


def _human_text(entry):
    """The text of a message a person typed, or None for anything else."""
    if entry.get("type") != "user" or entry.get("isMeta"):
        return None
    content = (entry.get("message") or {}).get("content")
    if content is None:
        return None
    if isinstance(content, list) and any(b.get("type") == "tool_result" for b in content):
        return None
    text = _text(content).strip()
    if not text or NOISE.match(text):
        return None
    return text


def last_user_prompt(path) -> str:
    prompt = ""
    for d in _entries(path):
        text = _human_text(d)
        if text:
            prompt = text
    return prompt


def last_assistant_text(path) -> str:
    """All text Claude wrote since the last human message."""
    parts = []
    for d in _entries(path):
        if _human_text(d):
            parts = []
        content = (d.get("message") or {}).get("content")
        if d.get("type") == "assistant" and isinstance(content, list):
            parts += [b["text"] for b in content if b.get("type") == "text" and b["text"].strip()]
    return "\n\n".join(parts)


def pairs(path):
    """Yield one dict per (Claude turn, the human message that followed it)."""
    texts, tools, denied = [], [], False
    for d in _entries(path):
        content = (d.get("message") or {}).get("content")
        if d.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if b.get("type") == "text" and b["text"].strip():
                    texts.append(b["text"])
                elif b.get("type") == "tool_use":
                    tools.append({"tool": b.get("name"), "input": json.dumps(b.get("input", {}))[:600]})
            continue
        if isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_result" and b.get("is_error") and DENIAL.search(json.dumps(b.get("content"))):
                    denied = True
        reply = _human_text(d)
        if reply is None:
            continue
        if texts or tools:
            yield {
                "claude_text": "\n\n".join(texts)[-4000:],
                "claude_tools": tools[-15:],
                "interrupted": "Request interrupted by user" in reply,
                "tool_denied": denied,
                "user_reply": reply[:2000],
            }
        texts, tools, denied = [], [], False
