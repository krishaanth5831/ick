"""python3 -m ick scan | sort | label | export | check"""
import sys

from ick import config, learn, rules

USAGE = "usage: python3 -m ick scan | sort | label | export | check"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sort" and not config.jev_url():
        sys.exit("Set ICK_JEV_URL first (see README).")
    commands = {
        "scan": learn.scan, "sort": learn.sort, "label": learn.label,
        "export": learn.export, "check": rules.check,
    }
    if cmd not in commands:
        sys.exit(USAGE)
    commands[cmd]()


if __name__ == "__main__":
    main()
