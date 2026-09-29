"""Entry point for /ick: flips ick on or off for the current project."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ick import config, judge, state  # noqa: E402


def main() -> None:
    project = os.getcwd()
    if not state.toggle(project):
        print(f"ick is OFF for {project}")
        return
    print(f"ick is ON for {project}")
    if not config.jev_url():
        print("WARNING: no judge is set up, so nothing will be checked. Set ICK_JEV_URL (see the ick README).")
        return
    problem = judge.check()
    if problem:
        print(f"WARNING: the judge at {config.jev_url()} is not answering, so nothing will be checked until it is. ({problem})")


if __name__ == "__main__":
    main()
