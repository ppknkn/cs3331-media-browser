"""Run unittest and retain machine-readable and full text evidence for every run."""
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.started = {}

    def startTest(self, test):
        self.started[test.id()] = time.perf_counter()
        super().startTest(test)

    def record(self, test, status, details=None):
        self.records.append({"id": test.id(), "status": status, "seconds": round(time.perf_counter() - self.started.get(test.id(), time.perf_counter()), 6), "details": details})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failed", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, "skipped", reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.record(subtest, "failed_subtest", self._exc_info_to_string(err, test))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    started = datetime.now(timezone.utc)
    output = ROOT / "docs" / "test-results"
    output.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S%fZ")
    transcript = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    runner = unittest.TextTestRunner(stream=transcript, resultclass=RecordingResult, verbosity=2)
    beginning = time.perf_counter()
    with contextlib.redirect_stdout(transcript), contextlib.redirect_stderr(transcript):
        result = runner.run(suite)
    report = {"started_utc": started.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
              "command": "python tests/run_tests.py", "scope": "backend unit and real HTTP loopback integration; native picker is stubbed",
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
              "duration_seconds": round(time.perf_counter() - beginning, 6), "success": result.wasSuccessful(), "cases": result.records}
    (output / ("backend-" + stamp + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / ("backend-" + stamp + ".log")).write_text(transcript.getvalue(), encoding="utf-8")
    print(transcript.getvalue())
    print(f"Saved evidence: docs/test-results/backend-{stamp}.json and .log")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
