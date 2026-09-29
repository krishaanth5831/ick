"""Loading the rulebook: your personal one in ICK_HOME/rules.json if it exists, else the defaults."""
import json

from ick import config


def load(kind: str) -> list:
    """Rules that apply to `kind`: "file" (code Claude wrote) or "reply" (its final message)."""
    personal = config.home() / "rules.json"
    path = personal if personal.exists() else config.DEFAULT_RULES
    return [r for r in json.loads(path.read_text())["rules"] if r["on"] == kind]
