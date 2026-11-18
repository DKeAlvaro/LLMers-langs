# LLMers-langs

Course content for [LLMers](https://github.com/DKeAlvaro/LLMers-app): **Dutch from zero to A2+**, for English speakers.

- `course/nl/syllabus.json` — the curriculum: 12 units ("lines"), 63 lessons, each with goals, grammar points,
  vocabulary, scene and culture topic. Hand-designed; everything else is generated from it.
- `course/nl/lessons/<id>.json` — finished lessons (format: `pipeline/schema.md`).
- `course/nl/index.json` — what the app loads first.
- `course/nl/audio/` — native audio, file name = FNV-64 of `voice|text` (mirrored in the app). Words and phrases:
  ElevenLabs (Roos); sentences: neural nl-NL voices. `sources.json` records which is which.

## Pipeline

```bash
python pipeline/generate.py write              # DeepSeek V4.1 Flash writes a draft per lesson (drafts/, not committed)
python pipeline/generate.py review             # second pass as native editor; adds authored mistakes/explanations
python pipeline/validate.py --fix              # schema + exercise consistency, safe auto-fixes
python pipeline/coverage.py -v                 # TEACH BEFORE TEST: lists any Dutch word used before it was taught
python pipeline/repair.py                      # DeepSeek fixes what coverage found (rewrite or teach the word)
python pipeline/jevcheck.py                    # Jev grades every model answer like the app does
python pipeline/tts.py                         # audio (ElevenLabs for words/phrases, --el-all for everything)
python pipeline/build_index.py
pytest tests/test_course.py
```

Keys: `OPENSCALE_API_KEY`, `TYPESAFE_API_KEY`, `ELEVENLABS_API_KEY` (env vars or the vault `.env`).

The coverage checker builds, lesson by lesson, the set of Dutch forms the learner has been taught (words with
plurals, conjugations and participles, phrases, grammar tables and examples) and flags every word in example
sentences, dialogues, exercises and roleplays that is not in it. Compound numbers and compounds of two taught words
(4+ letters each) count as known.

`lessons/` holds the old v1 lessons used by the legacy Expo app.
