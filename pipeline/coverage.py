"""Teach-before-test checker.

For every lesson, builds the Dutch vocabulary the learner has actually been taught up to and including
that lesson (words with plurals/forms/inflections, phrases, grammar tables, bold words and examples), then
lists every word used in example sentences, dialogue, exercises and roleplay that was never taught.

Usage:
  python pipeline/coverage.py              summary per lesson
  python pipeline/coverage.py -v [ID ...]  every untaught word with its sentence
  python pipeline/coverage.py --json OUT   machine-readable report (used by repair.py)
"""
import json
import re
import sys

from common import DRAFTS, LESSONS, all_lessons, read_json

ALWAYS = {"de", "het", "een", "'t"}  # articles are shown on every noun from lesson 1
SEP_PREFIXES = ("terug", "samen", "binnen", "buiten", "thuis", "langs", "voorbij", "aan", "af", "bij", "door", "in", "mee",
                "na", "om", "op", "over", "toe", "uit", "voor", "weg", "vast", "klaar", "kapot", "schoon", "neer", "rond", "tegen")
INSEP = ("be", "ge", "her", "ont", "er", "ver")
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)*|['’]s\b", re.U)
VOWELS = "aeiouy"


def tokens(text):
    return [m.group(0).replace("’", "'") for m in WORD_RE.finditer(text or "")]


def load(lid):
    p = LESSONS / f"{lid}.json"
    if p.exists():
        return read_json(p)
    p = DRAFTS / f"{lid}.json"
    return read_json(p) if p.exists() else None


def stem_variants(stem):
    """Spelling variants of a Dutch stem: woon/won, zit/zitt, leef/leev, reis/reiz."""
    out = {stem}
    if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in VOWELS:
        out.add(stem[:-1])
    if len(stem) >= 3 and stem[-1] not in VOWELS and stem[-2] in VOWELS and stem[-3] not in VOWELS:
        out.add(stem[:-2] + stem[-2] * 2 + stem[-1])  # won -> woon, grot -> groot
    if len(stem) >= 3 and stem[-1] not in VOWELS and stem[-2] == stem[-3] and stem[-2] in VOWELS:
        out.add(stem[:-2] + stem[-1])  # woon -> won
    if stem.endswith("v"):
        out.add(stem[:-1] + "f")
    if stem.endswith("f"):
        out.add(stem[:-1] + "v")
    if stem.endswith("z"):
        out.add(stem[:-1] + "s")
    if stem.endswith("s"):
        out.add(stem[:-1] + "z")
    return out


def verb_forms(inf):
    inf = inf.lower()
    forms = {inf}
    parts = [("", inf)]
    for p in SEP_PREFIXES:
        if inf.startswith(p) and len(inf) - len(p) >= 4:
            parts.append((p, inf[len(p):]))
            forms.add(p)
    for prefix, core in parts:
        if core.endswith("en"):
            stem = core[:-2]
        elif core.endswith("n"):
            stem = core[:-1]  # gaan, staan, doen, zien
        else:
            continue
        for st in stem_variants(stem):
            forms |= {st, st + "t", st + "te", st + "ten", st + "de", st + "den", core}
            ge = "" if core.startswith(INSEP) else "ge"
            for pp in (ge + st + "t", ge + st + "d", ge + core):
                forms.add(prefix + pp)
                forms.add(pp)
            if prefix:
                forms.add(prefix + st + "t")
    return forms


def variants(tok):
    """Possible base forms of a token (strip inflection, plural, diminutive, participle)."""
    t = tok.lower()
    out = {t}
    if t.endswith("'s"):
        out.add(t[:-2])
    for suf in ("etjes", "tjes", "pjes", "jes", "etje", "tje", "pje", "je", "sten", "ste", "st", "ere", "er", "en", "es", "e", "s", "n", "t", "d", "te", "ten", "de", "den"):
        if t.endswith(suf) and len(t) - len(suf) >= 2:
            base = t[: -len(suf)]
            out |= stem_variants(base)
            out |= {b + "en" for b in stem_variants(base)}
    if t.startswith("ge") and len(t) > 5:
        core = t[2:]
        out |= variants_core(core)
    for p in SEP_PREFIXES:
        if t.startswith(p + "ge") and len(t) > len(p) + 4:
            out |= variants_core(t[len(p) + 2:])
            out.add(p)
    return out


def variants_core(core):
    out = {core}
    for suf in ("en", "t", "d"):
        if core.endswith(suf):
            base = core[: -len(suf)]
            out |= stem_variants(base)
            out |= {b + "en" for b in stem_variants(base)}
    return out


def taught(lesson):
    """Dutch forms a lesson explicitly teaches."""
    known = set()

    def add_text(text):
        for t in tokens(text):
            known.add(t.lower())

    for w in lesson.get("words", []):
        nl = w.get("nl", "")
        add_text(nl)
        add_text(w.get("plural") or "")
        add_text(re.sub(r"\(.*?\)", lambda m: m.group(0)[1:-1], w.get("forms") or ""))
        if w.get("pos") == "verb":
            for part in [nl] + re.findall(r"\b\w+en\b", w.get("forms") or ""):
                if " " not in part:
                    known |= verb_forms(part)
        if w.get("pos") == "adj":
            for t in tokens(nl):
                for st in stem_variants(t.lower()):
                    known |= {st, st + "e", st + "er", st + "st", st + "ste"}
        if w.get("pos") == "noun":
            for t in tokens(nl):
                known |= {t.lower() + "je", t.lower() + "tje"}
    for p in lesson.get("phrases", []):
        add_text(p.get("nl", ""))
    for g in lesson.get("grammar", []):
        for b in re.findall(r"\*\*(.+?)\*\*", (g.get("explanation") or "") + " " + (g.get("tip") or "")):
            add_text(b)
        t = g.get("table") or {}
        heads = [h.lower() for h in (t.get("headers") or [])]
        skip = {i for i, h in enumerate(heads) if any(k in h for k in ("english", "meaning", "translation", "sounds like", "like in", "time", "use", "when"))}
        for row in t.get("rows", []) or []:
            for k, cell in enumerate(row):
                if k not in skip:
                    add_text(cell)
        for e in g.get("examples", []) or []:
            add_text(e.get("nl", ""))
    return known


def names_in(lesson):
    names = set()
    d = lesson.get("dialogue", {})
    for s in d.get("speakers", []):
        names |= {t.lower() for t in tokens(s.get("name", ""))}
    names |= {t.lower() for t in tokens(lesson.get("roleplay", {}).get("partner", {}).get("name", ""))}
    return names


def checked_texts(lesson):
    """(section, Dutch text the learner must understand or produce)."""
    out = []
    for w in lesson.get("words", []):
        out.append(("word example", (w.get("example") or {}).get("nl", "")))
    for ln in lesson.get("dialogue", {}).get("lines", []):
        out.append(("dialogue", ln.get("nl", "")))
    for i, e in enumerate(lesson.get("exercises", [])):
        t = e.get("type")
        tag = f"ex{i} {t}"
        if t == "match":
            for a, _ in e.get("pairs", []):
                out.append((tag, a))
        elif t == "choice":
            if e.get("nl"):
                out.append((tag, e["nl"]))
        elif t == "build":
            out.append((tag, e.get("answer", "")))
            out += [(tag, x) for x in e.get("extra", [])]
        elif t == "gap":
            out.append((tag, e.get("text", "").replace("___", (e.get("answers") or [""])[0])))
        elif t == "translate":
            out.append((tag, (e.get("answers") or [""])[0]))
        elif t == "listen":
            out.append((tag, e.get("nl", "")))
        elif t == "reply":
            out.append((tag, e.get("say", {}).get("nl", "")))
            out.append((tag + " example", (e.get("examples") or [""])[0]))
        elif t == "article":
            out.append((tag, e.get("word", "")))
    r = lesson.get("roleplay", {})
    for j, tr in enumerate(r.get("turns", [])):
        out.append((f"roleplay{j}", tr.get("say", {}).get("nl", "")))
        out.append((f"roleplay{j} example", (tr.get("examples") or [""])[0]))
    out.append(("roleplay closing", r.get("closing", {}).get("nl", "")))
    return [(s, t) for s, t in out if t]


NUM_PARTS = ["een", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien", "elf", "twaalf", "dertien",
             "veertien", "vijftien", "zestien", "zeventien", "achttien", "negentien", "twintig", "dertig", "veertig",
             "vijftig", "zestig", "zeventig", "tachtig", "negentig", "honderd", "duizend", "en", "ën"]


def is_number(tok, known):
    """Compound numbers (vijfentwintig, driehonderd) made only of number words already taught."""
    t = tok.lower().replace("ë", "e") if "ën" not in tok else tok.lower()
    i = 0
    used = 0
    while i < len(t):
        for part in sorted(NUM_PARTS, key=len, reverse=True):
            if t.startswith(part, i) and (part in ("en", "ën") or part in known):
                i += len(part)
                used += 1
                break
        else:
            return False
    return used >= 2


def is_compound(tok, known):
    """Dutch compound of two taught words (dinsdag+avond, bus+halte), optional linking s/e/en."""
    t = tok.lower()
    for k in range(4, len(t) - 3):
        head, tail = t[:k], t[k:]
        if not any(v in known for v in variants(tail)):
            continue
        for h in (head, head[:-1] if head.endswith("s") else None, head[:-2] if head.endswith("en") else None, head[:-1] if head.endswith("e") else None):
            if h and len(h) >= 4 and h in known:
                return True
    return False


def is_known(tok, known):
    if any(v in known for v in variants(tok)):
        return True
    plain = tok.lower().replace("é", "e").replace("è", "e").replace("ë", "e").replace("ï", "i")
    if plain != tok.lower() and any(v in known for v in variants(plain)):
        return True
    return is_number(tok, known) or is_compound(tok, known)


def analyse():
    lessons = all_lessons()
    known = set(ALWAYS)
    proper = set()
    report = {}
    # proper names: capitalised mid-sentence anywhere in the course (Sanne, Utrecht, Nederland...)
    all_data = {l["id"]: load(l["id"]) for _, l in lessons}
    for data in all_data.values():
        if not data:
            continue
        proper |= names_in(data)
        for _, text in checked_texts(data):
            toks = tokens(text)
            for k, t in enumerate(toks):
                if k > 0 and t[:1].isupper() and toks[k - 1][-1:] not in ".!?":
                    proper.add(t.lower())
    for _, meta in lessons:
        lid = meta["id"]
        data = all_data[lid]
        if not data:
            continue
        known |= taught(data)
        issues = []
        for section, text in checked_texts(data):
            bad = []
            for t in tokens(text):
                lt = t.lower()
                if lt in proper or lt in ALWAYS or is_known(lt, known):
                    continue
                bad.append(t)
            if bad:
                issues.append({"section": section, "text": text, "unknown": sorted(set(bad), key=str.lower)})
        report[lid] = issues
    return report, known


def main():
    args = sys.argv[1:]
    report, _ = analyse()
    if "--json" in args:
        out = args[args.index("--json") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    verbose = "-v" in args
    only = [a for a in args if a.startswith("u")]
    total = 0
    for lid, issues in report.items():
        if only and lid not in only:
            continue
        words = sorted({w.lower() for i in issues for w in i["unknown"]})
        total += len(words)
        print(f"{lid}: {len(issues):3d} sentences, {len(words):3d} untaught words" + (f"  {', '.join(words[:14])}" if words else ""))
        if verbose:
            for i in issues:
                print(f"     [{i['section']}] {i['text']}  ->  {', '.join(i['unknown'])}")
    print(f"TOTAL untaught word types (summed per lesson): {total}")


if __name__ == "__main__":
    main()
