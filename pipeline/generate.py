"""Generate Dutch lessons with DeepSeek: write a draft, then a native-editor review pass.

Usage:
  python pipeline/generate.py write [ID ...]    drafts/<id>.json (skips existing unless --force)
  python pipeline/generate.py review [ID ...]   lessons/<id>.json from drafts (skips existing unless --force)
  python pipeline/generate.py all [ID ...]      write + review
  options: --force  --workers N
"""
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from common import DRAFTS, LESSONS, ROOT, all_lessons, llm, read_json, write_json

SCHEMA = (ROOT / "pipeline" / "schema.md").read_text(encoding="utf-8")
LOCK = threading.Lock()
STATS = {"in": 0, "out": 0, "done": 0, "fail": 0}

WRITER = """You are an expert Dutch teacher and course author (CEFR A0-A2+), a native speaker of Netherlands Dutch,
writing one lesson of a complete beginner-to-A2+ Dutch course for English-speaking adults. The app is called LLMers.

Return ONLY a JSON object that follows this format exactly:

{schema}

Rules
- Teach before test. Every Dutch word used in dialogue, exercises and roleplay must be in this lesson's `words`/`phrases`/`grammar`
  or in the KNOWN VOCABULARY list, or be a very basic function word (de, het, een, en, ik, is, ...). Keep sentences short and level-appropriate.
- Respect the level: do not use grammar that the course has not taught yet (see GRAMMAR SO FAR) except as fixed, glossed phrases.
- Dutch must be correct standard Netherlands Dutch, exactly as a native would naturally say it: correct spelling, articles, plurals,
  verb forms and word order. No Flemish words unless the lesson is about Flemish. Use realistic Dutch names and places.
- English: clear, warm, compact. No emojis. Explanations aimed at a total beginner who is not a linguist.
- `words`: cover the syllabus vocabulary for this lesson (you may drop a few less useful items or add a few essential ones).
  Do not re-teach words from KNOWN VOCABULARY unless the lesson adds something new (then add a note).
- Exercises: 18-24 items, ordered from recognition to production, roughly: 2 match, 3 choice, 2 article (only nouns of this lesson),
  3 build, 3 gap, 3 translate, 2 listen, 2 reply. Most items must practise this lesson's words and grammar.
  - choice: exactly ONE option is correct; distractors clearly wrong for a careful learner; `explain` = one sentence why.
  - build: answer 3-9 words. `accept` = every other correct sentence that uses exactly the same tiles (e.g. time-first inversion);
    empty list if none. `extra` = 1-3 distractor tiles that cannot form another correct sentence (wrong verb form, wrong article...).
  - gap: exactly one `___` in `text`; `answers` = every correct fill-in; `hint` = base form or a short English cue.
  - translate: 4-10 word English sentences; `answers` = 2-4 common correct Dutch versions (je/jij, ze/zij, alternative word order,
    u/je when English is ambiguous). `focus` = what it practises.
  - build / gap `explain`: one English sentence with the rule behind the correct answer.
  - translate / reply / roleplay turns `mistakes`: the 2-4 most likely beginner errors on that item, each with a grader-facing
    `pattern` (include a concrete wrong example) and a learner-facing `explain` (rule in plain words + correct Dutch in quotes).
  - listen: a 3-9 word Dutch sentence made of words the learner knows.
  - reply: a short situation; someone says `say` to the learner; `task` tells in English what to answer; `examples` = 2-3 model replies.
- Dialogue: natural, 8-14 lines, set in the lesson scene, uses the new words and grammar.
- Roleplay: the learner plays themself in the scene; 3-5 turns. Each `task` says WHAT to communicate in English (not the exact Dutch);
  `examples` = 2-3 short correct model answers at this level. Partner lines react naturally to a typical answer.
- `culture.text` must be accurate and useful; no clichés stated as facts.
"""

REVIEWER = """You are a meticulous native Dutch editor and experienced CEFR examiner. You receive one lesson (JSON) of a Dutch course
for English speakers. Check EVERYTHING and fix every problem:
- Dutch errors: spelling, articles (de/het), plurals, verb forms, participles, word order, prepositions, unnatural or non-native phrasing,
  Flemish usage. Translations that do not match.
- Exercises: wrong `answer` index; choice questions with more than one defensible option; build `answer` that cannot be made from
  the tiles; missing `accept` orders that are also correct; distractor `extra` tiles that could make another correct sentence;
  gap `text` with not exactly one `___` or missing valid fill-ins in `answers`; translate items missing common correct variants
  (je/jij, ze/zij, u/je, other natural word orders or synonyms taught in the course); listen sentences that are too hard;
  items that test words never taught (see KNOWN VOCABULARY) - rewrite them.
- Grammar notes: every claim must be correct; tables complete and consistent; examples correct.
- Level: nothing beyond the lesson's level and GRAMMAR SO FAR.
- Self-contained feedback: the app has NO tutor at runtime, only a classifier that picks which authored mistake the learner made.
  Make sure every build and gap item has `explain`, and every translate item, reply item and roleplay turn has `mistakes`:
  the 2-4 errors beginners most likely make on THAT item (word order, verb ending, de/het, niet/geen, hebben/zijn, a false friend,
  a missing word...), each with a precise `pattern` (include a concrete wrong example) and a learner-facing `explain`
  (1-2 short sentences: the rule in plain words and the correct Dutch in quotes). Add them if missing, fix them if wrong.
- Format: must follow the schema below exactly (field names, types, counts). Keep good content as is.

Schema:
{schema}

Return ONLY a JSON object: {{"changes": ["short description of each fix"], "lesson": <the full corrected lesson>}}
"""


def context(idx):
    lessons = all_lessons()
    unit, lesson = lessons[idx]
    known = [f"{l['id']}: {l['vocab'].split(':', 1)[-1].strip()}" for _, l in lessons[:idx]]
    grammar = [f"{l['id']} ({l['title']}): " + " | ".join(l["grammar"]) for _, l in lessons[:idx]]
    nxt = [f"{l['id']}: {l['subtitle']}" for _, l in lessons[idx + 1: idx + 4]]
    return unit, lesson, known, grammar, nxt


def brief(idx):
    unit, lesson, known, grammar, nxt = context(idx)
    return "\n".join([
        f"LESSON {lesson['id']} - unit {unit['id']} \"{unit['title']}\" ({unit['subtitle']}), level {unit['level']}",
        f"Title: {lesson['title']}  |  Subtitle: {lesson['subtitle']}",
        "Goals: " + "; ".join(lesson["goals"]),
        "Grammar to teach: " + " || ".join(lesson["grammar"]),
        "Syllabus vocabulary: " + lesson["vocab"],
        "Scene (dialogue + roleplay): " + lesson["scene"],
        "Culture note topic: " + lesson["culture"],
        "",
        "GRAMMAR SO FAR (already taught):",
        *(grammar or ["(nothing yet - this is the very first lesson)"]),
        "",
        "KNOWN VOCABULARY (taught in earlier lessons):",
        *(known or ["(none - absolute beginner)"]),
        "",
        "Coming next (do not teach these yet): " + ("; ".join(nxt) or "end of course"),
    ])


def count(usage):
    with LOCK:
        STATS["in"] += usage.get("prompt_tokens", 0)
        STATS["out"] += usage.get("completion_tokens", 0)


def write(idx, force=False):
    _, lesson = all_lessons()[idx]
    out = DRAFTS / f"{lesson['id']}.json"
    if out.exists() and not force:
        return "skip"
    data, usage = llm([
        {"role": "system", "content": WRITER.format(schema=SCHEMA)},
        {"role": "user", "content": brief(idx)},
    ])
    count(usage)
    data["id"] = lesson["id"]
    write_json(out, data)
    return "ok"


def review(idx, force=False):
    _, lesson = all_lessons()[idx]
    src = DRAFTS / f"{lesson['id']}.json"
    out = LESSONS / f"{lesson['id']}.json"
    if out.exists() and not force:
        return "skip"
    draft = read_json(src)
    data, usage = llm([
        {"role": "system", "content": REVIEWER.format(schema=SCHEMA)},
        {"role": "user", "content": brief(idx) + "\n\nLESSON JSON:\n" + json.dumps(draft, ensure_ascii=False)},
    ])
    count(usage)
    fixed = data.get("lesson") or data
    fixed["id"] = lesson["id"]
    write_json(out, fixed)
    write_json(DRAFTS / f"{lesson['id']}.review.json", {"changes": data.get("changes", [])})
    return f"ok ({len(data.get('changes', []))} fixes)"


def main():
    args = sys.argv[1:]
    force = "--force" in args
    workers = 8
    if "--workers" in args:
        workers = int(args[args.index("--workers") + 1])
    mode = args[0]
    ids = [a for a in args[1:] if a.startswith("u")]
    lessons = all_lessons()
    idxs = [i for i, (_, l) in enumerate(lessons) if not ids or l["id"] in ids]
    steps = {"write": [write], "review": [review], "all": [write, review]}[mode]

    def job(i):
        lid = lessons[i][1]["id"]
        for step in steps:
            t = time.time()
            try:
                res = step(i, force)
            except Exception as e:  # noqa: BLE001
                with LOCK:
                    STATS["fail"] += 1
                print(f"FAIL {step.__name__} {lid}: {e}", flush=True)
                return
            print(f"{step.__name__} {lid}: {res} {time.time() - t:.0f}s", flush=True)
        with LOCK:
            STATS["done"] += 1

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(job, idxs))
    cost = STATS["in"] / 1e6 * 0.06 + STATS["out"] / 1e6 * 0.24
    print(f"done={STATS['done']} fail={STATS['fail']} tokens in={STATS['in']} out={STATS['out']} ~${cost:.3f}", flush=True)


if __name__ == "__main__":
    main()
