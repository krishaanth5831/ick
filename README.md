# ick

A Claude Code plugin that catches AI slop, using your own definition of slop.

Everyone finds different things sloppy. Some people hate long answers, some hate extra files nobody asked for, some hate comments that restate the code. ick doesn't guess. It reads your past Claude Code chats, finds the moments you pushed back, and turns them into your personal rulebook. From then on, a small, fast judge model checks what Claude writes against those rules.

> **Status: early.** Prevention works: while ick is on, Claude is told your rules before every reply. In a side-by-side test, the same beginner question got a 21% shorter, simpler answer with no upsell at the end. Detection does not work yet: on labelled replies from real chats, Kev-0.8B separates slop from normal replies no better than chance, so replies are only warned about (never blocked by default) and the thresholds stay high. Fine-tuning Kev on the rule questions is the next step.

## How it works

```
 your past chats ──scan──► every Claude reply + what you said next
                               │
                             sort   the judge asks: were you unhappy?
                               │    was it about slop, or about a bug?
                               ▼
                         your slop moments
                               │
                         condense  (/ick:learn)
                               ▼
                    your rulebook: 5 to 10 slop categories,
                    each with a real example from your history
                               │
 Claude writes a file ─────────┤
 Claude finishes a reply ──────┘──► judge scores it against each rule
                                        │
                                   over the line? ──► ick tells Claude (for files)
                                                      or tells you (for replies)
```

1. **Scan.** Claude Code keeps every session as a transcript in `~/.claude/projects/`. ick pairs each Claude reply with the message you sent next. Interrupting Claude, denying a tool call, or replying "no, too long" is a label you already gave for free.
2. **Sort.** The judge answers two yes/no questions per pair: were you unhappy, and was it about style or quality rather than a bug? The second question keeps "that's broken" out of your slop rules.
3. **Condense.** `/ick:learn` builds a reading list: rules you stated outright (memory notes, CLAUDE.md), every interruption and denied tool call, replies with pushback words, and the judge's top-ranked pairs. Claude reads it, groups the real complaints into a rulebook in `~/.ick/rules.json`, asks you what's missing, and validates it. Complaints you repeated count more.
4. **Prevent.** Before every reply, ick tells Claude your rules as instructions (each rule's `avoid` line). This needs no judge.
5. **Check.** When Claude writes a file or ends a reply, the judge scores it against every rule. File hits go back to Claude. Reply hits are shown to you, or with `ICK_MODE=block` sent back to Claude for one rewrite. Only turn blocking on once your thresholds are tuned.

## The judge

ick talks to any server that speaks the Jev `/v1/systemone` API. Jev is TypeSafe's "System One" decision model: you send text plus yes/no questions and get back probabilities in a fraction of a second. It doesn't write anything, which is exactly what a judge should do.

You can point ick at:

| Judge | Cost | Notes |
|---|---|---|
| [Kev](https://github.com/jaredpalmer/kev) (recommended) | Free, runs locally | Apache-2.0. Kev-0.8B runs on a 6 GB NVIDIA GPU or Apple Silicon. Reads long text. Can be fine-tuned on your own labels. |
| [TypeSafe Jev](https://docs.typesafe.ai/api) | Paid per input token | Hosted. Waitlist access. |
| [Laya](https://github.com/NandhaKishorM/laya) | Free, runs locally | Apache-2.0. Runs on CPU, but its English model reads only 512 tokens. Not tested with ick. |

A local judge also means your chats never leave your machine.

Nobody has shown that the open models are as well calibrated as Jev, and thresholds tuned on one judge won't carry over to another. Tune them on your own examples.

## Install

Requires Claude Code and `python3`. No other dependencies.

```
/plugin marketplace add krishaanth5831/ick
/plugin install ick@ick
```

Then run a judge. Kev-0.8B on Linux with an NVIDIA GPU (needs [uv](https://docs.astral.sh/uv/); the first install downloads about 7 GB):

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev
uv sync --extra serve
uv pip install "flash-linear-attention==0.5.2" "triton>=3.7.1"
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009
```

It holds about 4.5 GB of GPU memory while running. Keep it running while you use Claude Code; if it's down, ick stays silent and `/ick` warns you.

Point ick at it in `~/.claude/settings.json`:

```json
{ "env": { "ICK_JEV_URL": "http://127.0.0.1:8009" } }
```

For TypeSafe instead, set `ICK_JEV_URL` to their API base and add `ICK_JEV_KEY`.

## Use

```
/ick          turn ick on for this project (checks the judge is answering)
/ick          run it again to turn it off
/ick:learn    build your personal rulebook from your past chats
```

The steps behind `/ick:learn`, plus labelling for fine-tuning (run from the ick folder):

```bash
python3 -m ick scan     # pair your chats             -> ~/.ick/pairs.jsonl
python3 -m ick sort     # judge scores every pair     -> ~/.ick/slop.jsonl
python3 -m ick label    # label pairs by hand         -> ~/.ick/labels.jsonl
python3 -m ick export   # labels as Kev training data -> ~/.ick/kev/records.jsonl
python3 -m ick check    # validate your rulebook
```

## Your data

Everything personal lives in `~/.ick/`: the on/off state, the scanned pairs, your labels and rulebook, a log of every judgment (`decisions.jsonl`, for tuning thresholds) and an error log. None of it goes in any repo. Delete the folder to reset ick completely. Set `ICK_HOME` to move it.

ick fails open: if it's off, has no judge, or hits an error, Claude carries on as normal and the error goes to `~/.ick/hook.log`.

## Development

```bash
python3 -m unittest discover tests
```

Work happens on `dev`. `main` only gets working code, through a pull request from `dev`.

## License

MIT
