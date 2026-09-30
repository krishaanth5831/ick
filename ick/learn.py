"""Learning what slop means to you, from your own Claude Code history.

  scan:   pair every Claude turn with the message you sent next   -> ICK_HOME/pairs.jsonl
  sort:   ask the judge which replies were slop complaints          -> ICK_HOME/slop.jsonl
  candidates: everything worth reading when writing the rulebook    -> ICK_HOME/candidates.md
  label:  label pairs by hand (slop / bug / fine)                   -> ICK_HOME/labels.jsonl
  export: turn your labels into Kev fine-tuning records             -> ICK_HOME/kev/records.jsonl

Condensing candidates.md into ICK_HOME/rules.json is done by the /ick:learn command.
"""
import json
import pathlib
import re

from ick import config, judge, transcript

TRANSCRIPTS = pathlib.Path.home() / ".claude" / "projects"

SORT_QUESTIONS = {
    "unhappy": "Is the user unhappy with, or pushing back on, what Claude just did or wrote?",
    "about_slop": (
        "Is the complaint about style or quality (too long, unrequested extras, filler, generic, "
        "made-up details) rather than about a bug, an error, or something not working?"
    ),
}

# Words that usually mean the user is pushing back. Only used to pick what Claude reads, never to decide.
PUSHBACK = re.compile(
    r"\b(no|don'?t|dont|stop|why|wrong|instead|too|again|still|never|remove|get rid|shorter|simpler|"
    r"slop|generic|fluff|bloat\w*|ramble|annoying|verbose|long|useless|not what)\b", re.I)

# What each hand label means for the two sort questions.
LABEL_ANSWERS = {
    "slop": {"unhappy": True, "about_slop": True},
    "bug": {"unhappy": True, "about_slop": False},
    "fine": {"unhappy": False, "about_slop": False},
}


def _read(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open() if line.strip()]


def pair_state(pair: dict) -> dict:
    """The state the judge sees for one pair. sort and export must use the same one.

    Kev's trainer rejects states over 384 tokens; 700 + 350 characters stays under it.
    """
    return {
        "claude_wrote": judge.excerpt(pair["claude_text"], 700),
        "user_replied": judge.excerpt(pair["user_reply"], 350),
    }


def scan(root=TRANSCRIPTS) -> pathlib.Path:
    out = config.home() / "pairs.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w") as f:
        for path in sorted(pathlib.Path(root).glob("*/*.jsonl")):
            for pair in transcript.pairs(path):
                pair["project"] = path.parent.name
                f.write(json.dumps(pair) + "\n")
                n += 1
    print(f"{n} pairs written to {out}")
    return out


def sort(threshold: float = 0.5) -> pathlib.Path:
    out = config.home() / "slop.jsonl"
    kept = 0
    with out.open("w") as g:
        for pair in _read(config.home() / "pairs.jsonl"):
            probs = judge.ask(pair_state(pair), SORT_QUESTIONS)
            if probs["unhappy"] >= threshold and probs["about_slop"] >= threshold:
                kept += 1
            g.write(json.dumps({**pair, "probs": probs}) + "\n")
    print(f"{kept} slop complaints (both questions >= {threshold}); all scores written to {out}")
    return out


def label() -> None:
    """Walk through unlabelled pairs and record s(lop) / b(ug) / f(ine); q quits, Enter skips."""
    path = config.home() / "labels.jsonl"
    done = {l["user_reply"] for l in _read(path)}
    keys = {"s": "slop", "b": "bug", "f": "fine"}
    todo = [p for p in _read(config.home() / "pairs.jsonl") if p["user_reply"] not in done]
    print(f"{len(todo)} pairs to label. s = slop complaint, b = bug complaint, f = fine, Enter = skip, q = quit\n")
    with path.open("a") as f:
        for i, pair in enumerate(todo, 1):
            print(f"--- {i}/{len(todo)}\nCLAUDE: {judge.excerpt(pair['claude_text'], 600)}\n\nYOU: {pair['user_reply'][:600]}\n")
            answer = input("[s/b/f/Enter/q] ").strip().lower()
            if answer == "q":
                break
            if answer in keys:
                f.write(json.dumps({"user_reply": pair["user_reply"], "claude_text": pair["claude_text"], "label": keys[answer], "by": "you"}) + "\n")
                f.flush()


def export() -> pathlib.Path:
    """Write every labelled pair as a Kev training record with both sort questions labelled."""
    out = config.home() / "kev" / "records.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    labels = _read(config.home() / "labels.jsonl")
    with out.open("w") as f:
        for l in labels:
            questions = {
                qid: {"type": "noul", "instructions": text, "label": LABEL_ANSWERS[l["label"]][qid]}
                for qid, text in SORT_QUESTIONS.items()
            }
            f.write(json.dumps({"state": pair_state(l), "questions": questions}) + "\n")
    counts = {k: sum(l["label"] == k for l in labels) for k in LABEL_ANSWERS}
    print(f"{len(labels)} records written to {out} ({counts})")
    return out


def _explicit_rules(home=None):
    """Things the user told Claude outright: memory feedback notes and their global CLAUDE.md."""
    home = home or pathlib.Path.home()
    files = sorted((home / ".claude" / "projects").glob("*/memory/feedback_*.md"))
    files += [f for f in [home / ".claude" / "CLAUDE.md"] if f.exists()]
    return [(f, f.read_text(errors="replace")[:1500]) for f in files]


def candidates(limit: int = 250) -> pathlib.Path:
    """Write a compact reading list for the rulebook step.

    The judge only ranks here. Claude reads everything picked and decides itself, because a
    small judge misses most complaints and misreads new requests as complaints.
    """
    pairs = _read(config.home() / "slop.jsonl") or _read(config.home() / "pairs.jsonl")

    def score(p):
        probs = p.get("probs") or {}
        return probs.get("unhappy", 0) * probs.get("about_slop", 0)

    picked, seen = [], set()

    def take(p, why):
        if p["user_reply"] not in seen and len(picked) < limit:
            seen.add(p["user_reply"])
            picked.append((p, why))

    for p in pairs:
        if p.get("interrupted") or p.get("tool_denied"):
            take(p, "interrupted" if p.get("interrupted") else "tool denied")
    for p in pairs:
        if PUSHBACK.search(p["user_reply"][:500]):
            take(p, "pushback words")
    for p in sorted(pairs, key=score, reverse=True)[:120]:
        take(p, f"judge score {score(p):.2f}")

    explicit = _explicit_rules()
    out = config.home() / "candidates.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        f.write("# ick candidates\n\n## What the user told Claude directly\n\n")
        for path, text in explicit:
            f.write(f"### {path.name}\n{text.strip()}\n\n")
        f.write(f"## {len(picked)} past exchanges worth reading (of {len(pairs)})\n\n")
        for i, (p, why) in enumerate(picked, 1):
            tools = ", ".join(str(t.get("tool")) for t in p.get("claude_tools", [])[-5:])
            f.write(f"### {i} ({why})\nCLAUDE: {judge.excerpt(p['claude_text'], 500)}\n")
            if tools:
                f.write(f"TOOLS: {tools}\n")
            f.write(f"USER: {p['user_reply'][:600]}\n\n")
    print(f"{len(picked)} exchanges and {len(explicit)} explicit rule files written to {out}")
    return out
