"""Entry point for /ick: flips ick on or off for the current project."""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ick import config, state  # noqa: E402


def main() -> None:
    project = os.getcwd()
    if state.toggle(project):
        print(f"ick is ON for {project}")
        if not config.jev_url():
            print("No judge is set up yet, so nothing will be checked. Set ICK_JEV_URL (see the ick README).")
    else:
        print(f"ick is OFF for {project}")


if __name__ == "__main__":
    main()
