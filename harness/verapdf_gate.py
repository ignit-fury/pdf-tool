"""Dev/CI-only PDF/A-2b oracle. Never imported by the product runtime."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time
from typing import Sequence

MAX_OUTPUT_BYTES = 16 * 1024 * 1024
PROFILE = "PDF/A-2b validation profile"


@dataclass(frozen=True)
class FileVerdict:
    path: str
    compliant: bool
    failed_rule_ids: tuple[str, ...]
    profile: str


@dataclass(frozen=True)
class ValidatorReport:
    verdicts: tuple[FileVerdict, ...]
    infrastructure_errors: tuple[str, ...]
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def valid_report(self) -> bool:
        return not self.infrastructure_errors

    @property
    def passed(self) -> bool:
        return (self.valid_report and bool(self.verdicts)
                and self.returncode in (None, 0)
                and all(v.compliant for v in self.verdicts))


def parse_report(payload: str | bytes, expected_count: int) -> ValidatorReport:
    """Reject missing/inconsistent data rather than deriving success from exit status."""
    verdicts: list[FileVerdict] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def counter(obj: dict, key: str) -> int:
        value = obj[key]
        require(type(value) is int and value >= 0, f"invalid counter {key}")
        return value

    try:
        require(type(expected_count) is int and expected_count > 0, "expected_count must be positive")
        require(len(payload.encode("utf-8") if isinstance(payload, str) else payload)
                <= MAX_OUTPUT_BYTES, "report output limit exceeded")
        data = json.loads(payload)
        require(isinstance(data, dict), "report root must be an object")
        report = data["report"]
        require(isinstance(report, dict), "missing report object")
        jobs = report["jobs"]
        require(isinstance(jobs, list) and len(jobs) == expected_count, "wrong job count")
        names: set[str] = set()
        for job in jobs:
            name = job["itemDetails"]["name"]
            require(isinstance(name, str) and bool(name.strip()) and name not in names,
                    "missing or duplicate filename")
            names.add(name)
            results = job["validationResult"]
            require(isinstance(results, list) and len(results) == 1, "wrong validation result count")
            result = results[0]
            compliant = result["compliant"]
            require(type(compliant) is bool, "compliant must be a boolean")
            require(result["profileName"] == PROFILE, "unexpected validation profile")
            require(result["jobEndStatus"] == "normal", "abnormal validation status")
            details = result["details"]
            counter(details, "passedRules")
            counter(details, "passedChecks")
            failed = counter(details, "failedRules")
            failed_checks = counter(details, "failedChecks")
            rules = details["ruleSummaries"]
            require(isinstance(rules, list) and len(rules) == failed, "failed rule count mismatch")
            rule_ids = []
            checks = 0
            for rule in rules:
                require(rule["ruleStatus"] == "FAILED" and rule["status"] == "failed",
                        "unexpected rule status")
                clause, number = rule["clause"], rule["testNumber"]
                require(isinstance(clause, str) and bool(clause) and type(number) is int
                        and number > 0, "invalid failed rule identifier")
                require(isinstance(rule["specification"], str) and bool(rule["specification"]),
                        "missing rule specification")
                count = counter(rule, "failedChecks")
                require(count > 0, "failed rule has no failed checks")
                checks += count
                rule_ids.append(f"{clause}-{number}")
            require(checks == failed_checks, "failed check count mismatch")
            require((compliant and failed == failed_checks == 0)
                    or (not compliant and failed > 0 and failed_checks > 0),
                    "compliance and failed rules disagree")
            verdicts.append(FileVerdict(name, compliant, tuple(rule_ids), result["profileName"]))

        batch = report["batchSummary"]
        require(counter(batch, "totalJobs") == expected_count, "batch job count mismatch")
        for key in ("failedParsingJobs", "failedEncryptedJobs", "outOfMemory", "veraExceptions"):
            require(counter(batch, key) == 0, f"validator infrastructure failure: {key}")
        summary = batch["validationSummary"]
        require(counter(summary, "failedJobCount") == 0, "failed validation jobs")
        for key in ("totalJobCount", "successfulJobCount"):
            require(counter(summary, key) == expected_count, f"{key} mismatch")
        positives = sum(v.compliant for v in verdicts)
        require(counter(summary, "compliantPdfaCount") == positives, "compliant count mismatch")
        require(counter(summary, "nonCompliantPdfaCount") == expected_count - positives,
                "noncompliant count mismatch")
        return ValidatorReport(tuple(verdicts), ())
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError, RecursionError) as exc:
        return ValidatorReport(tuple(verdicts), (f"invalid veraPDF report: {exc}",))


def run_validator(paths: Sequence[str | Path], executable: str | Path,
                  timeout_seconds: float = 60) -> ValidatorReport:
    """Run an argv-only, time/output-bounded child and verify every input filename."""
    inputs = [str(Path(path).resolve()) for path in paths]
    if not inputs or len(set(inputs)) != len(inputs) or timeout_seconds <= 0:
        return ValidatorReport((), ("expected unique nonempty inputs and a positive timeout",))
    command = [str(executable), "--flavour", "2b", "--format", "json", *inputs]
    captured = [bytearray(), bytearray()]
    errors: list[str] = []
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        return ValidatorReport((), (f"cannot execute veraPDF: {exc}",))

    deadline = time.monotonic() + timeout_seconds
    with selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        for index, pipe in enumerate((process.stdout, process.stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, index)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                errors.append("validator timeout exceeded")
                break
            for key, _ in selector.select(min(remaining, .1)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                capacity = MAX_OUTPUT_BYTES - sum(len(stream) for stream in captured)
                captured[key.data].extend(chunk[:max(0, capacity)])
                if len(chunk) > capacity:
                    errors.append("validator output limit exceeded")
                    break
            if errors:
                break
        if not errors:
            try:
                process.wait(timeout=max(.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                errors.append("validator timeout exceeded")
        if errors:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        process.stdout.close()
        process.stderr.close()

    stdout, stderr = (bytes(stream).decode("utf-8", errors="ignore") for stream in captured)
    parsed = parse_report(bytes(captured[0]), len(inputs)) if not errors else ValidatorReport((), ())
    errors.extend(parsed.infrastructure_errors)
    if parsed.valid_report and not errors:
        if sorted(v.path for v in parsed.verdicts) != sorted(inputs):
            errors.append("validator filenames do not match exact requested inputs")
        if process.returncode not in (0, 1):
            errors.append(f"validator process failed with exit {process.returncode}")
        elif process.returncode == 1 and not any(not v.compliant for v in parsed.verdicts):
            errors.append("validator exit 1 without a noncompliant verdict")
    return replace(parsed, infrastructure_errors=tuple(errors), returncode=process.returncode,
                   stdout=stdout, stderr=stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("baseline", "gate"))
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--executable", default=os.environ.get("VERAPDF_CMD", "verapdf"))
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence: dict = {"schema_version": 1, "profile": PROFILE,
                      "measured_at": datetime.now(timezone.utc).isoformat()}
    if args.mode == "baseline":
        if args.manifest is None or args.paths:
            parser.error("baseline requires --manifest and no positional paths")
        from harness.pdfa_fixture import materialize_manifest
        manifest = json.loads(args.manifest.read_text())
        records = []
        with tempfile.TemporaryDirectory(prefix="pdfa-baseline-") as directory:
            for case, path in materialize_manifest(manifest, Path(directory)):
                result = run_validator([path], args.executable, args.timeout)
                records.append({"id": case["id"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                **asdict(result)})
        evidence["records"] = records
        # Raw noncompliance is expected; infrastructure errors remain an explicit failure.
        passed = bool(records) and all(not record["infrastructure_errors"] for record in records)
    else:
        if not args.paths or args.manifest is not None:
            parser.error("gate requires one or more PDF paths")
        result = run_validator(args.paths, args.executable, args.timeout)
        evidence.update(asdict(result))
        passed = result.passed
    evidence["passed"] = passed
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
