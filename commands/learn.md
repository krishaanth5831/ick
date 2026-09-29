---
description: "Build your personal slop rulebook from your past Claude Code chats"
allowed-tools: ["Bash(cd ${CLAUDE_PLUGIN_ROOT} && python3 -m ick:*)", "Read", "Write"]
---

```!
cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m ick scan && python3 -m ick sort
```

The output above says where `slop.jsonl` was written. Each line is one of your past Claude replies (`claude_text`), what the user said next (`user_reply`), and the judge's scores (`probs.unhappy`, `probs.about_slop`).

Build the user's personal rulebook from it:

1. Read `slop.jsonl` and keep the lines where both scores are at least 0.5. Skim them all before grouping.
2. Group the complaints into 5 to 10 categories of slop. A complaint the user made several times is stronger evidence than one made once. Ignore complaints about bugs or broken code.
3. For each category write one yes/no question the judge can answer from only three fields: `what_the_user_asked`, `what_claude_wrote` and `length_in_words`. Ask about what Claude wrote, never about the user's reaction. Keep each question under 30 words.
4. Write the result to `rules.json` in the same folder as `slop.jsonl`, in exactly this shape:

```json
{"version": 1, "rules": [
  {"id": "short_snake_case", "on": "file", "question": "...", "threshold": 0.8, "why": "one line, your own words"}
]}
```

`on` is `"file"` for things Claude writes into files and `"reply"` for its chat replies. Use 0.8 for every threshold. Do not copy the user's messages into `why`, since the file may be shared.

5. Run `cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m ick check` and fix every problem it prints until it says OK.
6. Tell the user the categories you found in a short list, and that ick now uses them.
