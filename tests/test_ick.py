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

from ick import transcript  # noqa: E402

# Probabilities the fake judge returns for every question id.
FAKE_PROBS = {"unrequested_file": 0.95, "padding": 0.95}


class FakeJudge(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        answers = {q: {"type": "noul", "noul": FAKE_PROBS.get(q, 0.1)} for q in body["questions"]}
        data = json.dumps({"answers": answers}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


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
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.transcript = self.tmp / "t.jsonl"
        write_transcript(self.transcript, [user("add a login button"), assistant("Done. " * 50)])
        self.env = {**os.environ, "ICK_HOME": str(self.tmp / "home"), "ICK_JEV_URL": self.url}

    def run_script(self, name, stdin="", env=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "ick" / name)],
            input=stdin, capture_output=True, text=True, cwd=self.project, env=env or self.env,
        )

    def hook(self, payload, env=None):
        payload = {"cwd": str(self.project), "transcript_path": str(self.transcript), **payload}
        result = self.run_script("hook.py", json.dumps(payload), env)
        self.assertEqual(result.returncode, 0)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def write_event(self, content="# PLAN.md\nsteps..."):
        return {"hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": "PLAN.md", "content": content}}

    def test_toggle_flips_on_and_off(self):
        self.assertIn("ON", self.run_script("toggle.py").stdout)
        self.assertIn("OFF", self.run_script("toggle.py").stdout)

    def test_silent_when_off(self):
        self.assertIsNone(self.hook(self.write_event()))

    def test_file_flag_goes_back_to_claude(self):
        self.run_script("toggle.py")
        out = self.hook(self.write_event())
        context = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("unrequested_file", context)
        self.assertNotIn("scope_creep", context)

    def test_reply_flag_is_shown_to_user(self):
        self.run_script("toggle.py")
        out = self.hook({"hook_event_name": "Stop", "stop_hook_active": False})
        self.assertIn("padding", out["systemMessage"])

    def test_stop_hook_does_not_loop(self):
        self.run_script("toggle.py")
        self.assertIsNone(self.hook({"hook_event_name": "Stop", "stop_hook_active": True}))

    def test_no_judge_configured_stays_silent(self):
        self.run_script("toggle.py")
        env = {k: v for k, v in self.env.items() if k != "ICK_JEV_URL"}
        self.assertIsNone(self.hook(self.write_event(), env))

    def test_judge_down_fails_open_and_logs(self):
        self.run_script("toggle.py")
        env = {**self.env, "ICK_JEV_URL": "http://127.0.0.1:9"}
        self.assertIsNone(self.hook(self.write_event(), env))
        self.assertIn("Error", (self.tmp / "home" / "hook.log").read_text())


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


if __name__ == "__main__":
    unittest.main()
