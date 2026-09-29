"""python3 -m ick scan | sort"""
import sys

from ick import config, learn

USAGE = "usage: python3 -m ick scan | sort"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "scan":
        learn.scan()
    elif cmd == "sort":
        if not config.jev_url():
            sys.exit("Set ICK_JEV_URL first (see README).")
        learn.sort()
    else:
        sys.exit(USAGE)


if __name__ == "__main__":
    main()
