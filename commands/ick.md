---
description: "Turn ick on or off for this project"
allowed-tools: ["Bash(python3 ${CLAUDE_PLUGIN_ROOT}/ick/toggle.py:*)"]
---

Run `cd "<the session's primary working directory>" && python3 "${CLAUDE_PLUGIN_ROOT}/ick/toggle.py"` with the Bash tool. Use the primary working directory from your environment, not whatever folder the shell was last in, so ick covers the whole project. If it fails with a sandbox error (for example `apply-seccomp`, `bwrap` or `Operation not permitted`), run it again with the sandbox disabled: the script only flips a switch in `~/.ick/state.json` and pings the local judge.

Then repeat the script's output to the user exactly as printed, and say nothing else.
