"""Learning what slop means to you, from your own Claude Code history.

  scan:   pair every Claude turn with the message you sent next   -> ICK_HOME/pairs.jsonl
  sort:   ask the judge which replies were slop complaints          -> ICK_HOME/slop.jsonl
  label:  label pairs by hand (slop / bug / fine)                   -> ICK_HOME/labels.jsonl
  export: turn your labels into Kev fine-tuning records             -> ICK_HOME/kev/records.jsonl

Condensing slop.jsonl into ICK_HOME/rules.json is done by the /ick:learn command.
"""
import json
import pathlib

from ick import config, judge, transcript

TRANSCRIPTS = pathlib.Path.home() / ".claude" / "projects"

SORT_QUESTIONS = {
    "unhappy": "Is the user unhappy with, or pushing back on, what Claude just did or wrote?",
    "about_slop": (
        "Is the complaint about style or quality (too long, unrequested extras, filler, generic, "
        "made-up details) rather than about a bug, an error, or something not working?"
    ),
}

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
    """The state the judge sees for one pair. sort and export must use the same one."""
    return {
        "claude_wrote": judge.excerpt(pair["claude_text"], 900),
        "user_replied": judge.excerpt(pair["user_reply"], 400),
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
