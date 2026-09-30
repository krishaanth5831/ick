"""Runs the real hook and toggle scripts as subprocesses against a fake judge server.

All transcripts here are synthetic. Run with: python3 -m unittest discover tests
"""
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ick import learn, rules, transcript  # noqa: E402

# Probabilities the fake judge returns, by question id. Tests override entries; setUp resets them.
DEFAULT_PROBS = {"asked": 0.1, "pushy_ending": 0.95, "unchecked_claims": 0.9, "generic": 0.1}
FAKE_PROBS = dict(DEFAULT_PROBS)


class FakeJudge(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        FakeJudge.last_state = body["state"]
        FakeJudge.calls += 1
        answers = {q: {"type": "noul", "noul": FAKE_PROBS.get(q, 0.1)} for q in body["questions"]}
        data = json.dumps({"answers": answers}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


FakeJudge.calls = 0


def write_transcript(path, lines):
    path.write_text("\n".join(json.dumps(line) for line in lines))


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


class IckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeJudge)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FAKE_PROBS.clear()
        FAKE_PROBS.update(DEFAULT_PROBS)
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.transcript = self.tmp / "t.jsonl"
        self.reply("Here is the answer.\n\nWant me to add more examples?")
        self.env = {**os.environ, "ICK_HOME": str(self.tmp / "home"), "ICK_JEV_URL": self.url}
        self.env.pop("CLAUDE_PROJECT_DIR", None)
        self.env.pop("ICK_MODE", None)

    def reply(self, text, prompt="explain pull-up resistors"):
        write_transcript(self.transcript, [user(prompt), assistant(text)])

    def run_script(self, name, stdin="", env=None, cwd=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "ick" / name)],
            input=stdin, capture_output=True, text=True, cwd=cwd or self.project, env=env or self.env,
        )

    def hook(self, payload, env=None):
        payload = {"cwd": str(self.project), "transcript_path": str(self.transcript), "session_id": "s1", **payload}
        result = self.run_script("hook.py", json.dumps(payload), env)
        self.assertEqual(result.returncode, 0)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def write_event(self, path="PLAN.md", content="# Plan\nsteps..."):
        return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": path, "content": content}}

    def stop(self, active=False):
        return {"hook_event_name": "Stop", "stop_hook_active": active}

    def prompt(self, text="give me ideas"):
        return {"hook_event_name": "UserPromptSubmit", "prompt": text}

    def use_rules(self, rule_list):
        home = self.tmp / "home"
        home.mkdir(exist_ok=True)
        (home / "rules.json").write_text(json.dumps({"rules": rule_list}))

    def no_judge(self):
        return {k: v for k, v in self.env.items() if k != "ICK_JEV_URL"}

    # switching

    def test_toggle_flips_on_and_off(self):
        on = self.run_script("toggle.py").stdout
        self.assertIn("ON", on)
        self.assertNotIn("WARNING", on)
        self.assertIn("OFF", self.run_script("toggle.py").stdout)

    def test_toggle_warns_when_judge_is_down(self):
        env = {**self.env, "ICK_JEV_URL": "http://127.0.0.1:9"}
        self.assertIn("not answering", self.run_script("toggle.py", env=env).stdout)

    def test_silent_when_off(self):
        self.assertIsNone(self.hook(self.write_event()))
        self.assertIsNone(self.hook(self.prompt()))
        self.assertIsNone(self.hook(self.stop()))

    def test_subfolder_of_enabled_project_is_on(self):
        self.run_script("toggle.py")
        sub = self.project / "src" / "deep"
        sub.mkdir(parents=True)
        self.assertIsNotNone(self.hook({**self.prompt(), "cwd": str(sub)}))

    def test_turning_off_from_subfolder_turns_off_project(self):
        self.run_script("toggle.py")
        sub = self.project / "src"
        sub.mkdir()
        self.assertIn("OFF", self.run_script("toggle.py", cwd=sub).stdout)
        self.assertIsNone(self.hook(self.prompt()))

    # prevention

    def test_prompt_gets_every_rule_without_a_judge(self):
        self.run_script("toggle.py")
        out = self.hook(self.prompt(), self.no_judge())
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("Avoid them", context)
        self.assertIn("Avoid obvious, generic ideas", context)
        self.assertIn("mark estimates clearly", context)

    def test_routing_drops_rules_the_prompt_is_not_about(self):
        self.run_script("toggle.py")
        context = self.hook(self.prompt("how big is the market?"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("mark estimates clearly", context)          # facts rule, Kev says it applies
        self.assertNotIn("Avoid obvious, generic ideas", context)  # ideas rule, Kev says it doesn't
        self.assertIn("No restated summaries", context)            # core rule, never routed
        self.assertEqual(FakeJudge.last_state, {"user_request": "how big is the market?"})

    def test_routing_sends_every_rule_when_judge_is_down(self):
        self.run_script("toggle.py")
        env = {**self.env, "ICK_JEV_URL": "http://127.0.0.1:9"}
        context = self.hook(self.prompt(), env)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Avoid obvious, generic ideas", context)
        self.assertIn("Error", (self.tmp / "home" / "hook.log").read_text())

    # mid-task file checks

    def test_unrequested_document_goes_back_to_claude(self):
        self.run_script("toggle.py")
        context = self.hook(self.write_event())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("did not ask for this file", context)
        self.assertEqual(FakeJudge.last_state["user_request"], "explain pull-up resistors")

    def test_requested_document_is_fine(self):
        self.run_script("toggle.py")
        FAKE_PROBS["asked"] = 0.9
        self.assertIsNone(self.hook(self.write_event()))

    def test_code_files_and_edits_are_not_checked(self):
        self.run_script("toggle.py")
        before = FakeJudge.calls
        self.assertIsNone(self.hook(self.write_event("main.py", "print(1)")))
        edit = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "tool_input": {"file_path": "a.md", "new_string": "b"}}
        self.assertIsNone(self.hook(edit))
        self.assertEqual(FakeJudge.calls, before)

    def test_every_judgment_is_logged(self):
        self.run_script("toggle.py")
        self.hook(self.write_event())
        rows = [json.loads(l) for l in (self.tmp / "home" / "decisions.jsonl").read_text().splitlines()]
        self.assertEqual(rows[-1]["event"], "PostToolUse")
        self.assertEqual(rows[-1]["flagged"], ["unrequested_file"])

    # reply checks

    def test_kev_sees_only_the_last_paragraph(self):
        self.run_script("toggle.py")
        out = self.hook(self.stop())
        self.assertIn("pushy_ending", out["systemMessage"])
        self.assertEqual(FakeJudge.last_state, {"closing_text": "Want me to add more examples?"})

    def test_clean_ending_is_not_flagged(self):
        self.run_script("toggle.py")
        FAKE_PROBS["pushy_ending"] = 0.2
        self.assertIsNone(self.hook(self.stop()))

    def test_next_action_line_is_caught_without_a_judge(self):
        self.run_script("toggle.py")
        self.reply("Done.\n\n**Next action:** run the tests.")
        self.assertIn("pushy_ending", self.hook(self.stop(), self.no_judge())["systemMessage"])

    def test_em_dash_check_ignores_code(self):
        self.run_script("toggle.py")
        self.use_rules([{"id": "dash", "on": "reply", "question": "q", "checks": ["em_dash"], "threshold": 0.8}])
        self.reply("Plain text.\n\n```\nx = 'a \u2014 b'\n```")
        self.assertIsNone(self.hook(self.stop(), self.no_judge()))
        self.reply("Text \u2014 with a dash.")
        self.assertIn("dash", self.hook(self.stop(), self.no_judge())["systemMessage"])

    def test_block_rule_sends_reply_back_to_claude(self):
        self.run_script("toggle.py")
        self.use_rules([{"id": "dash", "on": "reply", "question": "q", "checks": ["em_dash"], "threshold": 0.8,
                         "action": "block", "avoid": "Never use em dashes."}])
        self.reply("Text \u2014 with a dash.")
        out = self.hook(self.stop(), self.no_judge())
        self.assertEqual(out["decision"], "block")
        self.assertIn("Fix only the part", out["reason"])
        self.assertIn("Never use em dashes.", out["reason"])

    def test_warn_mode_overrides_block_rules(self):
        self.run_script("toggle.py")
        self.use_rules([{"id": "dash", "on": "reply", "question": "q", "checks": ["em_dash"], "threshold": 0.8, "action": "block"}])
        self.reply("Text \u2014 with a dash.")
        out = self.hook(self.stop(), {**self.no_judge(), "ICK_MODE": "warn"})
        self.assertIn("systemMessage", out)

    def test_block_mode_does_not_loop(self):
        self.run_script("toggle.py")
        self.assertIsNone(self.hook(self.stop(active=True), {**self.env, "ICK_MODE": "block"}))

    def test_flagged_reply_is_carried_into_the_next_prompt_once(self):
        self.run_script("toggle.py")
        self.hook(self.stop())
        first = self.hook(self.prompt())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Your previous reply broke these rules", first)
        second = self.hook(self.prompt())["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Your previous reply broke these rules", second)

    def test_judge_down_fails_open_and_logs(self):
        self.run_script("toggle.py")
        env = {**self.env, "ICK_JEV_URL": "http://127.0.0.1:9"}
        self.assertIsNone(self.hook(self.stop(), env))
        self.assertIn("Error", (self.tmp / "home" / "hook.log").read_text())


class PartTest(unittest.TestCase):
    def test_parts_skip_code_fences(self):
        from ick import hook
        text = "Intro line.\n\n```\ncode\n\nmore code\n```\n\nLast words."
        self.assertEqual(hook.part_of(text, "start"), "Intro line.")
        self.assertEqual(hook.part_of(text, "end"), "Last words.")
        self.assertNotIn("code", hook.part_of(text, "whole"))


class TranscriptTest(unittest.TestCase):
    def test_pairs_skip_tool_results_and_mark_interrupts(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "t.jsonl"
        write_transcript(path, [
            user("make a readme"),
            assistant("Here is a long plan."),
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
            assistant("And a changelog too."),
            user("[Request interrupted by user]"),
            assistant("Sorry."),
            user("no, just the readme"),
        ])
        pairs = list(transcript.pairs(path))
        self.assertEqual(len(pairs), 2)
        self.assertTrue(pairs[0]["interrupted"])
        self.assertIn("changelog", pairs[0]["claude_text"])
        self.assertEqual(pairs[1]["user_reply"], "no, just the readme")
        self.assertEqual(transcript.last_user_prompt(path), "no, just the readme")
        self.assertEqual(transcript.last_assistant_text(path), "")


class RulesTest(unittest.TestCase):
    def test_default_rules_are_valid(self):
        from ick import config
        self.assertEqual(rules.validate(config.DEFAULT_RULES), [])

    def test_bad_rules_are_caught(self):
        path = pathlib.Path(tempfile.mkdtemp()) / "rules.json"
        path.write_text(json.dumps({"rules": [{"id": "a", "on": "chat", "question": "", "threshold": 2}]}))
        self.assertEqual(len(rules.validate(path)), 3)
        path.write_text(json.dumps({"rules": [{"id": "a", "on": "reply", "question": "q", "threshold": 0.5,
                                               "avoid": "", "criteria": {"yes": "x"}}]}))
        self.assertEqual(len(rules.validate(path)), 2)
        path.write_text(json.dumps({"rules": [{"id": "a", "on": "reply", "question": "q", "threshold": 0.5,
                                               "part": "middle", "action": "delete", "checks": ["vibes"], "when": ""}]}))
        self.assertEqual(len(rules.validate(path)), 4)
        path.write_text("{not json")
        self.assertIn("cannot read", rules.validate(path)[0])


class ExportTest(unittest.TestCase):
    def test_labels_become_kev_records(self):
        home = pathlib.Path(tempfile.mkdtemp())
        (home / "labels.jsonl").write_text("\n".join(json.dumps(l) for l in [
            {"user_reply": "too long, just the answer", "claude_text": "Here is a long essay.", "label": "slop", "by": "you"},
            {"user_reply": "it crashes on start", "claude_text": "Fixed the import.", "label": "bug", "by": "you"},
        ]))
        os.environ["ICK_HOME"] = str(home)
        try:
            out = learn.export()
        finally:
            del os.environ["ICK_HOME"]
        records = [json.loads(line) for line in out.open()]
        self.assertEqual(records[0]["questions"]["about_slop"]["label"], True)
        self.assertEqual(records[1]["questions"]["unhappy"]["label"], True)
        self.assertEqual(records[1]["questions"]["about_slop"]["label"], False)
        self.assertEqual(records[0]["questions"]["unhappy"]["instructions"], learn.SORT_QUESTIONS["unhappy"])


if __name__ == "__main__":
    unittest.main()
