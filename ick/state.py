"""Per-project on/off switch, stored in ICK_HOME/state.json."""
import json
import os

from ick import config


def _path():
    return config.home() / "state.json"


def _load() -> dict:
    try:
        return json.loads(_path().read_text())
    except FileNotFoundError:
        return {"enabled": []}


def is_on(project: str) -> bool:
    return os.path.realpath(project) in _load()["enabled"]


def toggle(project: str) -> bool:
    """Flip the switch for a project and return the new state."""
    project = os.path.realpath(project)
    data = _load()
    if project in data["enabled"]:
        data["enabled"].remove(project)
    else:
        data["enabled"].append(project)
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, indent=2))
    return project in data["enabled"]
