"""Fix teach-before-test violations found by coverage.py.

For each lesson with untaught words, DeepSeek either rewrites the sentence with words the learner already knows
or adds the missing word to the lesson's `words`/`phrases` when it is useful and fits the lesson.

Usage: python pipeline/repair.py [--workers N] [ID ...]
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from common import DRAFTS, LESSONS, ROOT, all_lessons, llm, read_json, write_json
from coverage import analyse, taught, load, ALWAYS

SCHEMA = (ROOT / "pipeline" / "schema.md").read_text(encoding="utf-8")
LOCK = threading.Lock()

PROMPT = """You are a native Dutch course editor. The course rule is TEACH BEFORE TEST: a learner who started from zero must
already have been taught every Dutch word they read, hear or must write. An automatic checker found Dutch words in this lesson
that were never taught (not in this lesson's `words`/`phrases`/grammar, nor in any earlier lesson).

Fix EVERY listed problem, choosing per case:
 (a) rewrite the Dutch sentence (and its English translation and every dependent field: build `answer`/`accept`/`extra`,
     gap `answers`, translate `answers`, `mistakes`, roleplay `examples`, choice `options`) using only known words; or
 (b) if the word is genuinely useful for this lesson's topic and level, add it to `words` (all fields filled; nouns with
     article and plural; verbs with forms) or, for a fixed expression or interjection (oké, hè, nou), to `phrases`.
Prefer (b) for words a learner at this point clearly needs (max ~6 additions); prefer (a) for rare or off-topic words.
Do not introduce any other new word while rewriting. Keep everything else unchanged. Dutch must stay natural and correct.

Schema:
{schema}

Return ONLY JSON: {{"changes": ["what you did for each problem"], "lesson": <full corrected lesson>}}"""


def main():
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 12
    only = [a for a in args if a.startswith("u")]
    report, _ = analyse()
    lessons = all_lessons()
    order = [l["id"] for _, l in lessons]
    todo = [lid for lid in order if report.get(lid) and (not only or lid in only)]
    print(f"{len(todo)} lessons to repair", flush=True)

    def job(lid):
        i = order.index(lid)
        known = set(ALWAYS)
        for prev in order[:i]:
            d = load(prev)
            if d:
                known |= taught(d)
        lesson = read_json(LESSONS / f"{lid}.json")
        issues = report[lid]
        user = (
            f"LESSON {lid}: {lesson.get('title')} - {lesson.get('subtitle')} (level {lesson.get('level')})\n\n"
            "UNTAUGHT WORDS FOUND:\n"
            + "\n".join(f"- [{x['section']}] \"{x['text']}\" -> untaught: {', '.join(x['unknown'])}" for x in issues)
            + "\n\nWORDS TAUGHT IN EARLIER LESSONS (any inflected form is fine):\n"
            + ", ".join(sorted(w for w in known if w.isalpha() or "'" in w))
            + "\n\nLESSON JSON:\n"
            + json.dumps(lesson, ensure_ascii=False)
        )
        t = time.time()
        try:
            data, _ = llm([{"role": "system", "content": PROMPT.format(schema=SCHEMA)}, {"role": "user", "content": user}], reasoning="medium")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {lid}: {e}", flush=True)
            return
        fixed = data.get("lesson") or data
        fixed["id"] = lid
        write_json(LESSONS / f"{lid}.json", fixed)
        write_json(DRAFTS / f"{lid}.repair.json", {"issues": issues, "changes": data.get("changes", [])})
        with LOCK:
            print(f"repair {lid}: {len(issues)} issues, {len(data.get('changes', []))} changes, {time.time() - t:.0f}s", flush=True)

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(job, todo))
    print("done", flush=True)


if __name__ == "__main__":
    main()
