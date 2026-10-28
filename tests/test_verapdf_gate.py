"""Fail-closed controls for the dev/CI-only veraPDF oracle."""

import copy
import json
import os
from pathlib import Path

import pytest

from harness.verapdf_gate import parse_report, run_validator


def report(path="/input.pdf", compliant=True):
    rules = [] if compliant else [{"ruleStatus": "FAILED", "status": "failed",
        "specification": "ISO 19005-2:2011", "clause": "6.1.10", "testNumber": 1,
        "failedChecks": 1}]
    return {"report": {"jobs": [{"itemDetails": {"name": path}, "validationResult": [{
        "compliant": compliant, "profileName": "PDF/A-2b validation profile",
        "jobEndStatus": "normal", "details": {"passedRules": 143, "failedRules": len(rules),
        "passedChecks": 235, "failedChecks": len(rules), "ruleSummaries": rules}}]}],
        "batchSummary": {"totalJobs": 1, "failedParsingJobs": 0, "failedEncryptedJobs": 0,
        "outOfMemory": 0, "veraExceptions": 0, "validationSummary": {
        "failedJobCount": 0, "totalJobCount": 1, "successfulJobCount": 1,
        "compliantPdfaCount": int(compliant), "nonCompliantPdfaCount": int(not compliant)}}}}


def test_positive_and_negative_have_typed_verdicts():
    positive = parse_report(json.dumps(report()), 1)
    negative = parse_report(json.dumps(report(compliant=False)), 1)
    assert positive.passed
    assert negative.valid_report and not negative.passed
    assert negative.verdicts[0].failed_rule_ids == ("6.1.10-1",)


@pytest.mark.parametrize("passed_rules,passed_checks", [(0, 0), (0, 235), (143, 0)])
def test_compliant_report_requires_executed_rules_and_checks(passed_rules, passed_checks):
    data = report()
    data["report"]["jobs"][0]["validationResult"][0]["details"].update(
        passedRules=passed_rules, passedChecks=passed_checks)
    result = parse_report(json.dumps(data), 1)
    assert result.infrastructure_errors and not result.passed


@pytest.mark.parametrize("mutation", [
    lambda r: r["report"].update(jobs=[]),
    lambda r: r["report"]["jobs"].append(copy.deepcopy(r["report"]["jobs"][0])),
    lambda r: r["report"]["jobs"][0].update(validationResult=[]),
    lambda r: r["report"]["jobs"][0]["validationResult"].append(copy.deepcopy(r["report"]["jobs"][0]["validationResult"][0])),
    lambda r: r["report"]["jobs"][0]["validationResult"][0].update(compliant="true"),
    lambda r: r["report"]["jobs"][0]["validationResult"][0].update(jobEndStatus="exception"),
    lambda r: r["report"]["jobs"][0]["validationResult"][0].update(profileName="PDF/A-1b validation profile"),
    lambda r: r["report"]["jobs"][0]["validationResult"][0]["details"].update(failedRules=1),
    lambda r: r["report"]["batchSummary"]["validationSummary"].update(compliantPdfaCount=0),
    lambda r: r["report"]["jobs"][0]["itemDetails"].update(name=""),
    lambda r: r["report"]["batchSummary"].pop("failedParsingJobs"),
])
def test_incomplete_or_inconsistent_reports_fail_closed(mutation):
    data = report()
    mutation(data)
    result = parse_report(json.dumps(data), 1)
    assert result.infrastructure_errors and not result.passed


@pytest.mark.parametrize("counter", ["failedParsingJobs", "failedEncryptedJobs", "outOfMemory", "veraExceptions"])
def test_resource_and_parse_failures_are_infrastructure_errors(counter):
    data = report()
    data["report"]["batchSummary"][counter] = 1
    assert not parse_report(json.dumps(data), 1).valid_report


@pytest.mark.parametrize("payload,count", [("", 1), ("{}", 1), ("garbage", 1), ("[]", 1), ("null", 1), ("{}", 0)])
def test_empty_malformed_and_zero_expected_fail(payload, count):
    assert not parse_report(payload, count).valid_report


def executable(tmp_path, body):
    path = tmp_path / "validator"
    path.write_text("#!/usr/bin/env python3\n" + body)
    path.chmod(0o755)
    return path


def test_exit_zero_noncompliant_cannot_pass(tmp_path):
    source = tmp_path / "input.pdf"
    cli = executable(tmp_path, "print(" + repr(json.dumps(report(str(source), False))) + ")\n")
    result = run_validator([source], cli, 2)
    assert result.valid_report and not result.passed and result.returncode == 0


@pytest.mark.parametrize("compliant,exitcode,valid", [(True, 0, True), (False, 1, True), (True, 1, False), (True, 2, False), (False, 2, False)])
def test_process_status_is_reconciled(tmp_path, compliant, exitcode, valid):
    source = tmp_path / "input.pdf"
    cli = executable(tmp_path, "import sys\nprint(" + repr(json.dumps(report(str(source), compliant))) + f")\nsys.exit({exitcode})\n")
    result = run_validator([source], cli, 2)
    assert result.valid_report is valid
    assert result.passed is (compliant and exitcode == 0)


def test_different_filename_cannot_pass(tmp_path):
    cli = executable(tmp_path, "print(" + repr(json.dumps(report("/wrong.pdf"))) + ")\n")
    assert not run_validator([tmp_path / "expected.pdf"], cli, 2).valid_report


def test_timeout_and_missing_executable_fail_closed(tmp_path):
    cli = executable(tmp_path, "import time\ntime.sleep(5)\n")
    assert "timeout" in " ".join(run_validator([tmp_path / "a.pdf"], cli, .1).infrastructure_errors)
    assert not run_validator([tmp_path / "a.pdf"], tmp_path / "missing", 2).valid_report


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_is_bounded_while_process_runs(tmp_path, monkeypatch, stream):
    import harness.verapdf_gate as gate
    monkeypatch.setattr(gate, "MAX_OUTPUT_BYTES", 4096)
    cli = executable(tmp_path, f"import sys\nsys.{stream}.write('x' * 1000000)\n")
    result = run_validator([tmp_path / "a.pdf"], cli, 2)
    assert "output limit" in " ".join(result.infrastructure_errors)
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 4096


def test_actual_installed_controls_when_explicitly_requested():
    command = os.environ.get("VERAPDF_CMD")
    if not command:
        pytest.skip("set VERAPDF_CMD to exercise authenticated local CLI")
    result = run_validator([Path("corpus/public/verapdf_type3_font_fixture.pdf"),
                            Path("corpus/public/verapdf_inline_image_fixture.pdf")], command, 30)
    assert result.valid_report, result.infrastructure_errors
    assert [v.compliant for v in result.verdicts] == [True, False]
    assert result.returncode == 1
    assert "6.1.10-1" in result.verdicts[1].failed_rule_ids
