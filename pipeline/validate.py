"""Validate (and lightly normalise) every lesson in course/nl/lessons.

Usage: python pipeline/validate.py [--fix]
Hard errors make the script exit 1. --fix applies safe automatic repairs (types, missing lists, tile issues).
"""
import re
import sys

from common import LESSONS, all_lessons, read_json, write_json

TYPES = {"match", "choice", "article", "build", "gap", "translate", "listen", "reply"}
PUNCT = re.compile(r"[.,!?;:\"“”()…]")


def norm(s):
    return re.sub(r"\s+", " ", PUNCT.sub(" ", s.lower())).strip()


def tiles(s):
    return [t for t in PUNCT.sub(" ", s).split() if t]


def check(lesson, meta, fix):
    errs, warns = [], []
    lid = lesson.get("id")
    for key in ("title", "subtitle", "level", "intro", "words", "phrases", "grammar", "dialogue", "exercises", "roleplay", "culture", "summary"):
        if key not in lesson:
            errs.append(f"missing {key}")
    if errs:
        return errs, warns
    if fix:
        lesson["title"] = meta["title"]
        lesson["subtitle"] = meta["subtitle"]
    for i, w in enumerate(lesson["words"]):
        for k in ("nl", "en", "pos", "example"):
            if not w.get(k):
                errs.append(f"word {i} missing {k}")
        nl0 = w.get("nl", "")
        if w.get("pos") == "noun" and nl0.lower().startswith(("de ", "het ")) and w.get("article") not in ("de", "het") and fix:
            w["article"] = nl0.split(" ", 1)[0].lower()
        if w.get("pos") == "noun" and w.get("article") not in ("de", "het"):
            if fix and nl0[:1].isupper():
                w["pos"] = "other"  # proper noun: Amsterdam, Nederland
            else:
                warns.append(f"noun without article: {nl0}")
        if w.get("pos") != "noun" and w.get("article") and fix:
            w["article"] = None
        if fix:
            for k in ("article", "plural", "forms", "note"):
                w.setdefault(k, None)
        if w.get("nl", "").lower().startswith(("de ", "het ")) and w.get("pos") == "noun":
            if fix:
                w["nl"] = w["nl"].split(" ", 1)[1]
            else:
                warns.append(f"word with article in nl: {w['nl']}")
    if not (12 <= len(lesson["words"]) <= 40):
        warns.append(f"{len(lesson['words'])} words")
    for p in lesson["phrases"]:
        if fix:
            p.setdefault("note", None)
    for g in lesson["grammar"]:
        if fix:
            g.setdefault("table", None)
            g.setdefault("tip", None)
            g.setdefault("examples", [])
        t = g.get("table")
        if t and (not t.get("headers") or not isinstance(t.get("rows"), list)):
            if fix:
                g["table"] = None
            else:
                errs.append(f"bad table in {g.get('title')}")
    d = lesson["dialogue"]
    names = {s["name"] for s in d.get("speakers", [])}
    for ln in d.get("lines", []):
        if ln.get("speaker") not in names:
            errs.append(f"dialogue speaker {ln.get('speaker')} not in speakers")
    exs = lesson["exercises"]
    if not (12 <= len(exs) <= 30):
        warns.append(f"{len(exs)} exercises")
    keep = []
    for i, e in enumerate(exs):
        t = e.get("type")
        bad = None
        if t not in TYPES:
            bad = f"unknown type {t}"
        elif t == "match":
            if len(e.get("pairs", [])) < 3:
                bad = "match with <3 pairs"
            elif len({p[0] for p in e["pairs"]}) != len(e["pairs"]) or len({p[1] for p in e["pairs"]}) != len(e["pairs"]):
                bad = "match with duplicate sides"
        elif t == "choice":
            if not isinstance(e.get("answer"), int) or not (0 <= e["answer"] < len(e.get("options", []))):
                bad = "choice answer out of range"
            elif len(set(map(norm, e["options"]))) != len(e["options"]):
                bad = "choice duplicate options"
            if fix:
                e.setdefault("nl", None)
                e.setdefault("explain", "")
        elif t == "article":
            if e.get("answer") not in ("de", "het"):
                bad = "article answer"
            elif e.get("word", "").lower().startswith(("de ", "het ")):
                if fix:
                    e["word"] = e["word"].split(" ", 1)[1]
        elif t == "build":
            ans = tiles(e.get("answer", ""))
            if len(ans) < 2:
                bad = "build too short"
            if fix:
                e.setdefault("accept", [])
                e["extra"] = [x for x in e.get("extra", []) if x.lower() not in {a.lower() for a in ans}]
            bank = [t.lower() for t in ans + list(e.get("extra", []))]

            def buildable(sentence):
                pool = list(bank)
                for t in tiles(sentence):
                    if t.lower() not in pool:
                        return False
                    pool.remove(t.lower())
                return True

            if fix:
                e["accept"] = [a for a in e.get("accept", []) if buildable(a)]
            for x in e.get("extra", []):
                # a distractor tile must not complete another accepted sentence: we cannot check meaning here,
                # but at least it must differ from every answer tile
                pass
        elif t == "gap":
            if e.get("text", "").count("___") != 1:
                bad = "gap without exactly one ___"
            elif not e.get("answers"):
                bad = "gap without answers"
        elif t == "translate":
            if not e.get("answers"):
                bad = "translate without answers"
            if not e.get("mistakes"):
                warns.append(f"ex {i} translate without mistakes")
        elif t == "listen":
            if not e.get("nl"):
                bad = "listen without nl"
        elif t == "reply":
            if not e.get("examples") or not e.get("say", {}).get("nl"):
                bad = "reply incomplete"
            if not e.get("mistakes"):
                warns.append(f"ex {i} reply without mistakes")
        if bad:
            (warns if fix else errs).append(f"ex {i} ({t}): {bad}" + (" -> dropped" if fix else ""))
            if not fix:
                keep.append(e)
        else:
            keep.append(e)
    lesson["exercises"] = keep
    r = lesson["roleplay"]
    if not r.get("turns"):
        errs.append("roleplay without turns")
    for j, tr in enumerate(r.get("turns", [])):
        if not tr.get("examples") or not tr.get("say", {}).get("nl"):
            errs.append(f"roleplay turn {j} incomplete")
        if not tr.get("mistakes"):
            warns.append(f"roleplay turn {j} without mistakes")
    if r.get("partner", {}).get("gender") not in ("f", "m"):
        if fix:
            r.setdefault("partner", {})["gender"] = "f"
        else:
            errs.append("roleplay partner gender")
    if not r.get("closing", {}).get("nl"):
        errs.append("roleplay without closing")
    return errs, warns


def main():
    fix = "--fix" in sys.argv
    total_err = 0
    metas = {l["id"]: (u, l) for u, l in all_lessons()}
    for lid, (unit, meta) in metas.items():
        p = LESSONS / f"{lid}.json"
        if not p.exists():
            print(f"{lid}: MISSING")
            total_err += 1
            continue
        lesson = read_json(p)
        lesson["id"] = lid
        lesson["level"] = unit["level"]
        errs, warns = check(lesson, meta, fix)
        if fix:
            write_json(p, lesson)
        if errs or warns:
            print(f"{lid}: {len(errs)} errors, {len(warns)} warnings")
            for e in errs:
                print(f"   ERROR {e}")
            for w in warns:
                print(f"   warn  {w}")
        total_err += len(errs)
    print(f"total errors: {total_err}")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
