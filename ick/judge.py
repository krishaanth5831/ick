"""Client for any server that speaks the Jev /v1/systemone API.

That covers TypeSafe's hosted Jev and self-hosted, Jev-compatible servers such
as Kev and Laya. Only yes/no ("noul") questions are used so far.
"""
import json
import os
import urllib.request

from ick import config


def excerpt(text: str, limit: int) -> str:
    """Keep the start and end of long text. Kev was trained on states of about 1400 characters."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n[...]\n" + text[-half:]


def ask(state, questions: dict, timeout: float = None) -> dict:
    """Ask yes/no questions about `state`. Returns {question_id: probability of yes}.

    `questions` maps an id to the question text, or to {"instructions", "criteria"} where
    criteria describes what counts as true and false. Raises on network or API errors;
    callers decide whether that should fail open.
    """
    if timeout is None:
        timeout = float(os.environ.get("ICK_JEV_TIMEOUT", "8"))
    body = {
        "model": config.jev_model(),
        "state": state,
        "questions": {
            qid: {"type": "noul", **(q if isinstance(q, dict) else {"instructions": q})}
            for qid, q in questions.items()
        },
    }
    headers = {"content-type": "application/json"}
    if config.jev_key():
        headers["authorization"] = f"Bearer {config.jev_key()}"
    req = urllib.request.Request(
        config.jev_url() + "/v1/systemone", data=json.dumps(body).encode(), headers=headers
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answers = json.load(resp)["answers"]
    return {qid: float(answers[qid]["noul"]) for qid in questions}


def check():
    """Return None if the judge answers a trivial question, else a short reason it didn't."""
    try:
        ask("The sky is blue.", {"ok": "Is this sentence about the sky?"}, timeout=30)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"
