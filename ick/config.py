"""Where ick keeps its files, and which judge it talks to.

Everything personal (on/off state, mined chats, your rulebook, logs) lives in
ICK_HOME, outside any repo, so it can never be committed by accident.
"""
import os
import pathlib

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_RULES = PACKAGE_DIR.parent / "rules" / "default.json"


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("ICK_HOME", pathlib.Path.home() / ".ick"))


def jev_url():
    """Base URL of any server speaking the Jev /v1/systemone API, or None."""
    url = os.environ.get("ICK_JEV_URL", "").strip().rstrip("/")
    return url or None


def jev_key():
    return os.environ.get("ICK_JEV_KEY") or None


def jev_model() -> str:
    return os.environ.get("ICK_JEV_MODEL", "jev-latest")
