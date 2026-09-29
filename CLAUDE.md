# ick

Claude Code plugin that judges Claude's output for slop. See README.md.

## Git rules

- Work directly on `dev`. No feature branches unless the user asks.
- `main` only receives working code, through a PR from `dev`. Never push to `main`.
- Only open a PR when the user asks. Always pass `--base main` explicitly.
- Never merge a PR. The user merges.

## Code rules

- Python standard library only. The hook runs as `python3` with no install step.
- The hook must fail open: exit 0 with no output on any error, and log it to `ICK_HOME/hook.log`.
- Nothing personal in the repo. Mined chats, rulebooks and state live in `ICK_HOME` (default `~/.ick`). Test fixtures are synthetic.
- Run tests with `python3 -m unittest discover tests`.
