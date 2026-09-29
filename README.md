# ick

A Claude Code plugin that catches AI slop, using your own definition of slop.

Everyone finds different things sloppy. Some people hate long answers, some hate extra files nobody asked for, some hate comments that restate the code. ick doesn't guess. It reads your past Claude Code chats, finds the moments you pushed back, and turns them into your personal rulebook. From then on, a small, fast judge model checks what Claude writes against those rules.

> **Status: early scaffold.** The on/off switch, the hook, the judge client and the chat scan work and are tested. Learning your rulebook from the scan is not built yet, so for now ick uses the starter rules in `rules/default.json`, and it only warns. It never blocks.

## How it works

```
 your past chats ──scan──► every Claude reply + what you said next
                               │
                             sort   the judge asks: were you unhappy?
                               │    was it about slop, or about a bug?
                               ▼
                         your slop moments
                               │
                           condense (not built yet)
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
3. **Condense.** Claude groups your slop moments into a short rulebook. Complaints you repeated count more. *(Not built yet.)*
4. **Enforce.** Each rule becomes a question for the judge. When Claude writes a file or ends a reply, ick asks every rule at once and reports the ones over their threshold.

## The judge

ick talks to any server that speaks the Jev `/v1/systemone` API. Jev is TypeSafe's "System One" decision model: you send text plus yes/no questions and get back probabilities in a fraction of a second. It doesn't write anything, which is exactly what a judge should do.

You can point ick at:

| Judge | Cost | Notes |
|---|---|---|
| [TypeSafe Jev](https://docs.typesafe.ai/api) | Paid per input token | Hosted. Waitlist access. |
| [Laya](https://github.com/NandhaKishorM/laya) | Free, runs locally | Apache-2.0. `pip install "laya[serve]"`, runs on CPU. |
| [Kev](https://github.com/jaredpalmer/kev) | Free, runs locally | Apache-2.0. Wants a GPU or Apple Silicon. |

A local judge also means your chats never leave your machine.

Nobody has shown that the open models are as well calibrated as Jev, and thresholds tuned on one judge won't carry over to another. Tune them on your own examples.

## Install

Requires Claude Code and `python3`. No other dependencies.

```
/plugin marketplace add krishaanth5831/ick
/plugin install ick@ick
```

Then tell ick where the judge is. For example, a local Laya server:

```bash
pip install "laya[serve]"
LAYA_HOST=127.0.0.1 LAYA_MODELS=english laya-serve
```

and in `~/.claude/settings.json`:

```json
{ "env": { "ICK_JEV_URL": "http://127.0.0.1:8000" } }
```

Use the port your server prints. For TypeSafe, set `ICK_JEV_URL` to their API base and add `ICK_JEV_KEY`.

## Use

```
/ick     turn ick on for this project
/ick     run it again to turn it off
```

Learning from your history (run from the ick folder):

```bash
python3 -m ick scan    # pairs your chats into ~/.ick/pairs.jsonl
python3 -m ick sort    # keeps the slop complaints in ~/.ick/slop.jsonl
```

## Your data

Everything personal lives in `~/.ick/`: the on/off state, the scanned pairs, your rulebook and an error log. None of it goes in any repo. Delete the folder to reset ick completely. Set `ICK_HOME` to move it.

ick fails open: if it's off, has no judge, or hits an error, Claude carries on as normal and the error goes to `~/.ick/hook.log`.

## Development

```bash
python3 -m unittest discover tests
```

Work happens on `dev`. `main` only gets working code, through a pull request from `dev`.

## License

MIT
