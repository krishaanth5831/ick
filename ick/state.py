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


def _covering(project: str, enabled: list) -> list:
    """Enabled folders that contain `project` (itself or a parent)."""
    project = os.path.realpath(project)
    return [e for e in enabled if project == e or project.startswith(e.rstrip(os.sep) + os.sep)]


def is_on(project: str) -> bool:
    return bool(_covering(project, _load()["enabled"]))


def toggle(project: str) -> bool:
    """Flip the switch for a project and return the new state.

    Turning off from a subfolder turns off the enabled folder that covers it.
    """
    data = _load()
    covering = _covering(project, data["enabled"])
    if covering:
        data["enabled"] = [e for e in data["enabled"] if e not in covering]
    else:
        data["enabled"].append(os.path.realpath(project))
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, indent=2))
    return project in data["enabled"]
