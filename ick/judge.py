"""Client for any server that speaks the Jev /v1/systemone API.

That covers TypeSafe's hosted Jev and self-hosted, Jev-compatible servers such
as Kev and Laya. Only yes/no ("noul") questions are used so far.
"""
import json
import urllib.request

from ick import config


def ask(state, questions: dict, timeout: float = 5.0) -> dict:
    """Ask yes/no questions about `state`. Returns {question_id: probability of yes}.

    `questions` maps an id to the question text. Raises on network or API errors;
    callers decide whether that should fail open.
    """
    body = {
        "model": config.jev_model(),
        "state": state,
        "questions": {qid: {"type": "noul", "instructions": text} for qid, text in questions.items()},
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
