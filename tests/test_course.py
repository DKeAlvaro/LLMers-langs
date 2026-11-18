"""Course v2 checks: every lesson valid, nothing tested before it is taught."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))


def test_lessons_validate():
    r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "validate.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]


def test_teach_before_test():
    from coverage import analyse
    report, _ = analyse()
    bad = {lid: issues for lid, issues in report.items() if issues}
    assert not bad, "\n".join(f"{lid}: {[i['unknown'] for i in issues]}" for lid, issues in bad.items())
