"""Fix model answers that Jev rejected (jevcheck.json): make task and examples match exactly, using only taught words."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from common import COURSE, DRAFTS, LESSONS, ROOT, all_lessons, llm, read_json, write_json
from coverage import ALWAYS, load, taught

SCHEMA = (ROOT / "pipeline" / "schema.md").read_text(encoding="utf-8")
PROMPT = """You are a native Dutch course editor. A strict grader checked the model answers of this lesson against their tasks.
The listed model answers do NOT fully do what their task asks (a part is missing, a required word like 'omdat' is not used,
the content differs from the task, or the Dutch is off). The app grades learners against these tasks and uses the examples as
reference answers, so task and examples must match exactly.

For each listed item, fix it: complete or rewrite the examples so each one does everything the task asks, or simplify the task
so the examples fully do it. Keep tasks short and clear (one or two things to say). Every example must be natural, correct
Dutch at the lesson's level, using only words the learner knows (taught in this lesson or listed below). No placeholders like
[naam]: use a realistic name. Update `mistakes` if needed. Keep everything else unchanged.

Schema:
{schema}

Return ONLY JSON: {{"changes": ["..."], "lesson": <full corrected lesson>}}"""


def main():
    flagged = json.loads((COURSE / "jevcheck.json").read_text(encoding="utf-8"))["flagged"]
    only = [a for a in sys.argv[1:] if a.startswith("u")]
    by = {}
    for f in flagged:
        if not only or f["lesson"] in only:
            by.setdefault(f["lesson"], []).append(f)
    order = [l["id"] for _, l in all_lessons()]

    def job(lid):
        known = set(ALWAYS)
        for prev in order[: order.index(lid)]:
            d = load(prev)
            if d:
                known |= taught(d)
        lesson = read_json(LESSONS / f"{lid}.json")
        lines = []
        for f in by[lid]:
            w = f["where"]
            if w.startswith("roleplay"):
                t = lesson["roleplay"]["turns"][int(w[8:])]
                lines.append(f"- roleplay turn {w[8:]}: partner says \"{t['say']['nl']}\"; task: \"{t['task']}\"; rejected example: \"{f['answer']}\"")
            else:
                i = int(w.split()[0][2:])
                e = lesson["exercises"][i]
                lines.append(f"- exercise {i} ({e['type']}): task: \"{e.get('task') or e.get('en')}\"; rejected example: \"{f['answer']}\"")
        user = (f"LESSON {lid}: {lesson['title']} (level {lesson['level']})\n\nREJECTED MODEL ANSWERS:\n" + "\n".join(lines)
                + "\n\nWORDS TAUGHT IN EARLIER LESSONS:\n" + ", ".join(sorted(w for w in known if w.isalpha()))
                + "\n\nLESSON JSON:\n" + json.dumps(lesson, ensure_ascii=False))
        t = time.time()
        try:
            data, _ = llm([{"role": "system", "content": PROMPT.format(schema=SCHEMA)}, {"role": "user", "content": user}], reasoning="medium")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {lid}: {e}", flush=True)
            return
        fixed = data.get("lesson") or data
        fixed["id"] = lid
        write_json(LESSONS / f"{lid}.json", fixed)
        write_json(DRAFTS / f"{lid}.fixtasks.json", {"items": by[lid], "changes": data.get("changes", [])})
        print(f"fixtasks {lid}: {len(by[lid])} items, {len(data.get('changes', []))} changes, {time.time() - t:.0f}s", flush=True)

    with ThreadPoolExecutor(12) as ex:
        list(ex.map(job, list(by)))
    print("done", flush=True)


if __name__ == "__main__":
    main()
