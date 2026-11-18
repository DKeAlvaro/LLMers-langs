"""Build course/nl/index.json (what the app loads first) from the syllabus and the finished lessons."""
import datetime

from common import COURSE, LESSONS, read_json, syllabus, write_json


def main():
    syl = syllabus()
    units = []
    for u in syl["units"]:
        lessons = []
        for l in u["lessons"]:
            p = LESSONS / f"{l['id']}.json"
            if not p.exists():
                continue
            data = read_json(p)
            lessons.append({
                "id": l["id"],
                "title": l["title"],
                "subtitle": l["subtitle"],
                "level": u["level"],
                "goals": l["goals"],
                "words": len(data.get("words", [])),
                "exercises": len(data.get("exercises", [])),
            })
        if lessons:
            units.append({"id": u["id"], "title": u["title"], "subtitle": u["subtitle"], "level": u["level"], "lessons": lessons})
    index = {
        "language": "nl",
        "name": "Dutch",
        "version": datetime.date.today().isoformat(),
        "units": units,
    }
    write_json(COURSE / "index.json", index)
    n = sum(len(u["lessons"]) for u in units)
    w = sum(l["words"] for u in units for l in u["lessons"])
    e = sum(l["exercises"] for u in units for l in u["lessons"])
    print(f"index: {len(units)} units, {n} lessons, {w} words, {e} exercises")


if __name__ == "__main__":
    main()
