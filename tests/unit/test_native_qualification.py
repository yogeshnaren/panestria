"""Certificate issuance needs the complete clean-source OS/native conformance set."""

import json
import subprocess
import xml.etree.ElementTree as ET

import pytest
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.execution import native_qualification as qualification

CANDIDATE = "ab" * 20


def report():
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for module, name in sorted(qualification.EXPECTED):
        case = ET.SubElement(suite, "testcase", classname=module, name=name)
        props = ET.SubElement(case, "properties")
        ET.SubElement(props, "property", name="candidate_commit", value=CANDIDATE)
        ET.SubElement(props, "property", name="worktree_state", value="clean")
    return root, suite


def test_complete_evidence_is_runtime_only_and_no_fixture_certificate_is_accepted():
    root, suite = report()
    assert len(qualification.validate_report(ET.tostring(root), CANDIDATE)) == 11
    ET.SubElement(suite[0].find("properties"), "property", name="certificate", value="TEST_FIXTURE_NOT_LIVE")
    with pytest.raises(qualification.QualificationUnavailable, match="evidence_incomplete"):
        qualification.validate_report(ET.tostring(root), CANDIDATE)


@pytest.mark.parametrize("bad", ["missing", "duplicate", "extra", "failed", "skipped", "dirty", "other-source"])
def test_incomplete_or_wrong_source_observations_cannot_issue(bad):
    root, suite = report()
    if bad == "missing":
        suite.remove(suite[0])
    elif bad == "duplicate":
        suite.append(ET.fromstring(ET.tostring(suite[0])))
    elif bad == "extra":
        ET.SubElement(suite, "testcase", classname="unreviewed", name="unreviewed")
    elif bad in {"failed", "skipped"}:
        ET.SubElement(suite[0], "failure" if bad == "failed" else "skipped")
    elif bad == "dirty":
        suite[0].find("properties")[1].set("value", "dirty")
    else:
        suite[0].find("properties")[0].set("value", "cd" * 20)
    with pytest.raises(qualification.QualificationUnavailable, match="evidence_incomplete"):
        qualification.validate_report(ET.tostring(root), CANDIDATE)


def test_operator_opt_in_is_required_before_any_source_or_provider_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must not inspect or launch without explicit public smoke flag")

    monkeypatch.setattr(qualification, "_state", forbidden)
    result = CliRunner().invoke(app, ["native", "qualify-build", "--evidence-directory", str(tmp_path / "evidence")])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == "UNAVAILABLE"
    assert not (tmp_path / "evidence").exists()


def test_failed_conformance_records_current_failure_without_a_certificate(tmp_path, monkeypatch):
    monkeypatch.setattr(qualification, "_state", lambda root: CANDIDATE)
    monkeypatch.setattr(qualification, "runtime_versions", lambda: {"fixture": "never-qualified"})
    monkeypatch.setattr(qualification.shutil, "which", lambda executable: "/usr/bin/uv")
    real = subprocess.Popen

    def failed(*args, **kwargs):
        return real(["/usr/bin/false"], **kwargs)

    monkeypatch.setattr(qualification.subprocess, "Popen", failed)
    directory = tmp_path / "private"
    result = qualification.qualify(directory, public_subscription_smoke=True)
    assert result["status"] == "UNAVAILABLE" and result["reason"] == "qualification_cases_failed"
    assert json.loads((directory / "latest.json").read_text()) == result
    assert json.loads(next(directory.glob("run-*/result.json")).read_text()) == result
    assert not (directory / "certificates").exists()
