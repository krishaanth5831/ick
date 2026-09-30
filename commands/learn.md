---
description: "Build your personal slop rulebook from your past Claude Code chats"
allowed-tools: ["Bash(cd ${CLAUDE_PLUGIN_ROOT} && python3 -m ick:*)", "Read", "Write", "AskUserQuestion"]
---

Build the user's personal slop rulebook. Commands below are run with the Bash tool. If one fails with a sandbox error (for example `apply-seccomp`, `bwrap` or `Operation not permitted`), run it again with the sandbox disabled: ick only reads the user's Claude Code history and writes to `~/.ick`.

1. Run `cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m ick scan && python3 -m ick sort && python3 -m ick candidates`. If sort says the judge is not set up or not answering, skip sort and run `scan` and `candidates` only; the list is then picked without the judge's ranking.
2. Read all of `candidates.md` (the output says where it is; read it in chunks if it is long). It has two parts:
   - **What the user told Claude directly**: memory notes and CLAUDE.md rules. These are the strongest evidence, because the user said them outright.
   - **Past exchanges**: a Claude reply, the tools it used, and what the user said next. You decide which ones are complaints about slop. The judge's scores and the pushback-word matches only picked what to read; many are new requests, questions or bug reports, which are not slop.
3. Group the real slop complaints into 5 to 10 categories. Count how often each shows up: something the user complained about several times, or stated as a rule, outranks a one-off. Ignore bugs, broken code and wrong facts about the user's own setup.
4. Show the user the categories in a short list, most frequent first, with how many times each appeared. Then ask with AskUserQuestion what bugs them that is missing or wrong. Add or remove categories based on the answer.
5. For each category write a rule:
   - `question`: one yes/no question the judge can answer from only `what_the_user_asked`, `what_claude_wrote` and `length_in_words`. Ask about what Claude wrote, never about the user's reaction. Under 30 words.
   - `avoid`: one instruction to Claude, written as what to do instead, under 25 words. This is shown to Claude before it answers, so it must stand on its own.
   - `criteria`: `{"true": "...", "false": "..."}`, one short description each of what a yes and a no look like. This helps the judge tell them apart.
   - `on`: `"file"` for things written into files, `"reply"` for chat replies.
   - `threshold`: 0.8.
   - `why`: one line in your own words. Never copy the user's messages anywhere in the file, since it may be shared.
6. Write the rules to `rules.json` in the same folder as `candidates.md`:

```json
{"version": 1, "rules": [
  {"id": "short_snake_case", "on": "reply", "question": "...", "avoid": "...",
   "criteria": {"true": "...", "false": "..."}, "threshold": 0.8, "why": "..."}
]}
```

7. Run `cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m ick check` and fix every problem it prints until it says OK.
8. Tell the user the final categories in a short list, and that ick now tells Claude about them before every reply while ick is on.
