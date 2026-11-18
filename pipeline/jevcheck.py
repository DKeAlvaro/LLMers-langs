"""QA with Jev: grade every model answer with the same questions the app's correction server uses.

A model answer that Jev rejects is either wrong Dutch or a case where the app would mark a correct learner wrong.
Usage: python pipeline/jevcheck.py [--workers N] [ID ...]   -> course/nl/jevcheck.json + summary
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from common import COURSE, LESSONS, all_lessons, jev, read_json

CONTEXT = ("A beginner (CEFR A1-A2) is learning Dutch. `task` is what they were asked to do. `references` are correct model "
           "answers, but other wordings with the same meaning are also correct{free}. `answer` is what the learner typed. Ignore "
           "capital letters and final punctuation. Both formal (u) and informal (je) are fine unless the task says otherwise.")


def grade(kind, task, refs, answer, situation="", mistakes=()):
    free = kind != "translate"
    q = {"correct": {"type": "noul", "instructions": (
        "Is `answer` a correct Dutch reply (grammar and spelling right) that does what `task` asks?" if free else
        "Is `answer` a fully correct Dutch response to `task` (grammar, spelling and meaning all right)?")},
         "order": {"type": "noul", "instructions": "Read `answer` as the same kind of sentence as the references (a statement stays a statement, a question stays a question). Are all its words in an order a native speaker would use for that meaning?"}}
    for m in mistakes:
        q[f"m_{m['id']}"] = {"type": "noul", "instructions": f"Does `answer` make this specific mistake: {m['pattern']}"}
    state = {"context": CONTEXT.format(free=", and for free replies any natural Dutch answer that does what the task asks is correct" if free else ""),
             "task": task, "references": refs, "answer": answer}
    if situation:
        state["situation"] = situation
    a = jev(state, q)
    fired = max([v["noul"] for k, v in a.items() if k.startswith("m_")] or [0])
    score = a["correct"]["noul"]
    if a["order"]["noul"] < 0.5:
        score = min(score, a["order"]["noul"])
    if fired >= 0.5:
        score = min(score, 1 - fired)
    return score


def items(lesson):
    out = []
    for i, e in enumerate(lesson["exercises"]):
        if e["type"] == "translate":
            for a in e["answers"][:2]:
                out.append((f"ex{i} translate", "translate", f"Translate into Dutch: {e['en']}", e["answers"], a, "", e.get("mistakes", [])))
        elif e["type"] == "reply":
            for a in e["examples"][:2]:
                out.append((f"ex{i} reply", "reply", e["task"], e["examples"], a, f"{e['context']} They say: \"{e['say']['nl']}\"", e.get("mistakes", [])))
    r = lesson["roleplay"]
    for j, t in enumerate(r["turns"]):
        for a in t["examples"][:2]:
            out.append((f"roleplay{j}", "roleplay", t["task"], t["examples"], a,
                        f"{r['setting']} {r['partner']['name']} ({r['partner']['role']}) says: \"{t['say']['nl']}\"", t.get("mistakes", [])))
    return out


def main():
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 24
    only = [a for a in args if a.startswith("u")]
    jobs = []
    for _, m in all_lessons():
        if only and m["id"] not in only:
            continue
        lesson = read_json(LESSONS / f"{m['id']}.json")
        jobs += [(m["id"], *it) for it in items(lesson)]

    def run(j):
        lid, where, kind, task, refs, ans, sit, ms = j
        try:
            return lid, where, ans, grade(kind, task, refs, ans, sit, ms)
        except Exception as e:  # noqa: BLE001
            return lid, where, ans, None

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(run, jobs))
    flagged = [r for r in res if r[3] is not None and r[3] < 0.5]
    errors = [r for r in res if r[3] is None]
    out = {"checked": len(res), "flagged": [{"lesson": a, "where": b, "answer": c, "score": d} for a, b, c, d in flagged]}
    (COURSE / "jevcheck.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"checked {len(res)} model answers, {len(flagged)} rejected by Jev, {len(errors)} errors")
    for a, b, c, d in flagged:
        print(f"  {a} [{b}] {d:.2f}  {c}")


if __name__ == "__main__":
    main()
