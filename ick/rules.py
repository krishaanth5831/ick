"""The rulebook: your personal one in ICK_HOME/rules.json if it exists, else the defaults."""
import json

from ick import config


def _path():
    personal = config.home() / "rules.json"
    return personal if personal.exists() else config.DEFAULT_RULES


def load(kind: str) -> list:
    """Rules that apply to `kind`: "file" (code Claude wrote) or "reply" (its final message)."""
    return [r for r in json.loads(_path().read_text())["rules"] if r["on"] == kind]


def validate(path) -> list:
    """Every problem that would make the hook misbehave. Empty list means the file is fine."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read {path}: {e}"]
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list) or not rules:
        return ['top level must be {"rules": [ ... ]} with at least one rule']
    problems, seen = [], set()
    for i, r in enumerate(rules):
        where = f"rule {i} ({r.get('id', '?') if isinstance(r, dict) else '?'})"
        if not isinstance(r, dict):
            problems.append(f"{where}: must be an object")
            continue
        if not isinstance(r.get("id"), str) or not r["id"] or r["id"] in seen:
            problems.append(f"{where}: id must be a unique non-empty string")
        seen.add(r.get("id"))
        if r.get("on") not in ("file", "reply"):
            problems.append(f'{where}: "on" must be "file" or "reply"')
        if not isinstance(r.get("question"), str) or not r["question"].strip():
            problems.append(f"{where}: question must be a non-empty string")
        if "avoid" in r and (not isinstance(r["avoid"], str) or not r["avoid"].strip()):
            problems.append(f"{where}: avoid must be a non-empty string")
        c = r.get("criteria")
        if c is not None and (not isinstance(c, dict) or not c or set(c) - {"true", "false"}
                              or not all(isinstance(v, str) for v in c.values())):
            problems.append(f'{where}: criteria must be {{"true": "...", "false": "..."}}')
        t = r.get("threshold")
        if not isinstance(t, (int, float)) or isinstance(t, bool) or not 0 < t < 1:
            problems.append(f"{where}: threshold must be a number between 0 and 1")
    return problems


def check() -> None:
    path = _path()
    problems = validate(path)
    for p in problems:
        print(p)
    print(f"{path}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    if problems:
        raise SystemExit(1)
