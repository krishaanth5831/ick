"""Learning what slop means to you, from your own Claude Code history.

  scan: pair every Claude turn with the message you sent next  -> ICK_HOME/pairs.jsonl
  sort: ask the judge which of those replies were slop complaints -> ICK_HOME/slop.jsonl

The third step (condensing slop.jsonl into ICK_HOME/rules.json) is not built yet.
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


def sort(threshold: float = 0.7) -> pathlib.Path:
    src, out = config.home() / "pairs.jsonl", config.home() / "slop.jsonl"
    kept = 0
    with src.open() as f, out.open("w") as g:
        for line in f:
            pair = json.loads(line)
            probs = judge.ask(
                {"claude_wrote": pair["claude_text"][-3000:], "user_replied": pair["user_reply"]},
                SORT_QUESTIONS,
            )
            if probs["unhappy"] >= threshold and probs["about_slop"] >= threshold:
                g.write(json.dumps({**pair, "probs": probs}) + "\n")
                kept += 1
    print(f"{kept} slop complaints written to {out}")
    return out
