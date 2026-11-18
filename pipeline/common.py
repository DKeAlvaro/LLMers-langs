"""Shared helpers for the course pipeline: paths, keys, LLM + Jev calls."""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COURSE = ROOT / "course" / "nl"
LESSONS = COURSE / "lessons"
DRAFTS = COURSE / "drafts"
AUDIO = COURSE / "audio"
SYLLABUS = COURSE / "syllabus.json"

VAULT_ENV = ROOT.parent / "pocket-vault-2" / ".env"

LLM_URL = "https://api.openscale.so/v1/chat/completions"
LLM_MODEL = "deepseek/deepseek-v4.1-flash"
JEV_URL = "https://api.typesafe.ai/v1/systemone"


def key(name):
    if os.environ.get(name):
        return os.environ[name]
    if VAULT_ENV.exists():
        for line in VAULT_ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"missing {name} (env var or vault .env)")


def syllabus():
    return json.loads(SYLLABUS.read_text(encoding="utf-8"))


def all_lessons():
    """Flat list of (unit, lesson) in course order."""
    out = []
    for u in syllabus()["units"]:
        for l in u["lessons"]:
            out.append((u, l))
    return out


def _post(url, body, headers, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def llm(messages, max_tokens=32000, json_mode=True, reasoning="high", timeout=600, tries=5):
    body = {"model": LLM_MODEL, "messages": messages, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if reasoning:
        body["reasoning_effort"] = reasoning
    headers = {"Authorization": f"Bearer {key('OPENSCALE_API_KEY')}", "Content-Type": "application/json"}
    last = None
    for attempt in range(tries):
        try:
            r = _post(LLM_URL, body, headers, timeout)
            msg = r["choices"][0]["message"]["content"]
            usage = r.get("usage", {})
            if json_mode:
                return parse_json(msg), usage
            return msg, usage
        except urllib.error.HTTPError as e:
            last = f"{e.code} {e.read()[:300]!r}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(min(60, 3 * 2 ** attempt))
    raise RuntimeError(f"llm failed: {last}")


def parse_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start:end + 1])


def jev(state, questions, tries=6, timeout=60):
    body = {"model": "jev-latest", "state": state, "questions": questions}
    headers = {"Authorization": f"Bearer {key('TYPESAFE_API_KEY')}", "Content-Type": "application/json"}
    last = None
    for attempt in range(tries):
        try:
            return _post(JEV_URL, body, headers, timeout)["answers"]
        except urllib.error.HTTPError as e:
            last = f"{e.code} {e.read()[:300]!r}"
            if e.code not in (429, 500, 502, 503, 529):
                break
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"jev failed: {last}")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
