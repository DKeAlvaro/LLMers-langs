"""Generate native-speaker audio for every Dutch string the app can play.

Words and phrases (the clips played most: cards, review, matching) use ElevenLabs (native Dutch library voices);
everything else uses edge-tts neural nl-NL voices, unless --el-all is given.

Usage: python pipeline/tts.py [--workers N] [--el-all] [--no-el] [ID ...]
Files: course/nl/audio/<fnv64(voice|text)>.mp3 — the app computes the same name (src/lib/text.ts fnv64).
Voice rules mirror the app (src/lib/audio.ts, components): F = Fenna, M = Maarten, C = Colette.
"""
import asyncio
import json
import sys
import urllib.error
import urllib.request

import edge_tts

from common import AUDIO, LESSONS, all_lessons, key, read_json

VOICES = {"F": "nl-NL-FennaNeural", "M": "nl-NL-MaartenNeural", "C": "nl-NL-ColetteNeural"}
# ElevenLabs shared-library voices, native Netherlands Dutch, educational profile
EL_VOICES = {"F": "7qdUFMklKPaaAVMsBTBt",  # Roos - kind, articulate
             "C": "OlBRrVAItyi00MuGMbna",  # Emma - calm, clear
             "M": "UNBIyLbtFB9k7FKW8wJv"}  # Serge de Beer - reliable, instructional
EL_MODEL = "eleven_flash_v2_5"           # 0.5 credits per character
SOURCES = AUDIO / "sources.json"


def fnv64(s):
    h = 0xCBF29CE484222325
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def clip(text, voice):
    return f"{fnv64(voice + '|' + text.strip())}.mp3"


def speaker_voice(speakers, name):
    sp = next((s for s in speakers if s["name"] == name), None)
    if not sp:
        return "F"
    if sp["gender"] == "m":
        return "M"
    women = [s for s in speakers if s["gender"] == "f"]
    return "C" if women.index(sp) % 2 == 1 else "F"


def gap_full(e, w):
    before, _, after = e["text"].partition("___")
    return " ".join(f"{before}{w}{after}".split())


def core_items(lesson):
    """Words and phrases: the clips that go to ElevenLabs by default."""
    out = []
    for w in lesson["words"]:
        out.append((f"{w['article']} {w['nl']}" if w.get("article") and w.get("pos") == "noun" else w["nl"]).strip())
    out += [p["nl"].strip() for p in lesson["phrases"]]
    return {(t, "F") for t in out if t}


def items(lesson):
    out = []
    add = lambda t, v: t and t.strip() and out.append((t.strip(), v))  # noqa: E731
    for w in lesson["words"]:
        add(f"{w['article']} {w['nl']}" if w.get("article") and w.get("pos") == "noun" else w["nl"], "F")
        add((w.get("example") or {}).get("nl"), "M")
    for p in lesson["phrases"]:
        add(p["nl"], "F")
    for g in lesson["grammar"]:
        for e in g.get("examples", []):
            add(e["nl"].replace("**", ""), "M")
    d = lesson["dialogue"]
    for ln in d["lines"]:
        add(ln["nl"], speaker_voice(d["speakers"], ln["speaker"]))
    for e in lesson["exercises"]:
        t = e["type"]
        if t == "match":
            for a, _ in e["pairs"]:
                add(a, "F")
        elif t == "choice":
            add(e.get("nl"), "F")
            add(e["options"][e["answer"]], "F")
        elif t == "article":
            add(f"{e['answer']} {e['word']}", "F")
        elif t == "build":
            add(e["answer"], "F")
        elif t == "gap":
            add(gap_full(e, e["answers"][0]), "F")
        elif t == "translate":
            for a in e["answers"]:
                add(a, "F")
        elif t == "listen":
            add(e["nl"], "F")
        elif t == "reply":
            add(e["say"]["nl"], "C")
            for x in e["examples"]:
                add(x, "F")
    r = lesson["roleplay"]
    rv = "M" if r["partner"]["gender"] == "m" else "C"
    for tr in r["turns"]:
        add(tr["say"]["nl"], rv)
        for x in tr["examples"]:
            add(x, "F")
    add(r["closing"]["nl"], rv)
    return out


def el_credits_left():
    req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key("ELEVENLABS_API_KEY")})
    d = json.load(urllib.request.urlopen(req, timeout=20))
    return d["character_limit"] - d["character_count"]


def el_tts(text, voice):
    body = json.dumps({"text": text, "model_id": EL_MODEL, "language_code": "nl",
                       "voice_settings": {"stability": 0.6, "similarity_boost": 0.8}}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICES[voice]}?output_format=mp3_44100_64", data=body,
        headers={"xi-api-key": key("ELEVENLABS_API_KEY"), "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=90).read()


async def synth(sem, text, voice, stats, use_el, sources):
    path = AUDIO / clip(text, voice)
    want = "el" if use_el else "edge"
    if path.exists() and path.stat().st_size > 0 and (not use_el or sources.get(path.name) == "el"):
        stats["skip"] += 1
        return
    async with sem:
        err = None
        for attempt in range(6):
            try:
                tmp = path.with_suffix(".tmp")
                if use_el:
                    data = await asyncio.to_thread(el_tts, text, voice)
                    tmp.write_bytes(data)
                else:
                    await edge_tts.Communicate(text, VOICES[voice]).save(str(tmp))
                tmp.replace(path)
                sources[path.name] = want
                stats["el" if use_el else "ok"] += 1
                n = stats["el"] + stats["ok"]
                if n % 200 == 0:
                    print(f"  {n} new clips", flush=True)
                    SOURCES.write_text(json.dumps(sources, indent=0), encoding="utf-8")
                return
            except urllib.error.HTTPError as e:
                err = f"{e.code} {e.read()[:160]!r}"
                if e.code in (401, 402, 403):
                    break
                await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:  # noqa: BLE001
                err = e
                await asyncio.sleep(1.5 * (attempt + 1))
        stats["fail"] += 1
        print(f"FAIL {'el' if use_el else 'edge'} {voice} {text[:60]!r}: {err}", flush=True)


async def main():
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 12
    el_all = "--el-all" in args
    no_el = "--no-el" in args
    ids = [a for a in args if a.startswith("u")]
    AUDIO.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    todo, core = {}, set()
    for _, meta in all_lessons():
        if ids and meta["id"] not in ids:
            continue
        p = LESSONS / f"{meta['id']}.json"
        if not p.exists():
            continue
        lesson = read_json(p)
        core |= core_items(lesson)
        for t, v in items(lesson):
            todo[(t, v)] = True
    el_todo = set() if no_el else ({k for k in todo} if el_all else {k for k in todo if k in core})
    el_todo = {k for k in el_todo if sources.get(clip(*k)) != "el"}
    need = sum(len(t) for t, _ in el_todo) // 2  # flash = 0.5 credits/char
    if el_todo:
        left = el_credits_left()
        print(f"ElevenLabs: {len(el_todo)} clips need ~{need:,} credits, {left:,} left", flush=True)
        if need > left - 500:
            print("not enough ElevenLabs credits: those clips fall back to edge-tts", flush=True)
            el_todo = set()
    print(f"{len(todo)} unique clips ({len(el_todo)} via ElevenLabs)", flush=True)
    stats = {"ok": 0, "el": 0, "skip": 0, "fail": 0}
    sem_edge = asyncio.Semaphore(workers)
    sem_el = asyncio.Semaphore(5)  # Starter plan: max 6 concurrent requests
    await asyncio.gather(*(synth(sem_el if (t, v) in el_todo else sem_edge, t, v, stats, (t, v) in el_todo, sources) for t, v in todo))
    SOURCES.write_text(json.dumps(sources, indent=0), encoding="utf-8")
    print(f"done: elevenlabs={stats['el']} edge={stats['ok']} existing={stats['skip']} failed={stats['fail']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
