"""Actual read-only Docker dependency import, not PDF extraction qualification."""

import json
import os

from panestria.brokers.research.pdf_bundle import PYPDF_VERSION, stage_pdf_bundle, verify_pdf_bundle
from panestria.sandbox.profiles import ReadOnlyMount, SandboxProfile
from panestria.sandbox.runner import DockerSandbox


def test_pinned_pdf_dependency_imports_only_from_readonly_runtime_bundle(tmp_path, record_property):
    bundle = stage_pdf_bundle(tmp_path / "pdf-deps")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    script = tmp_path / "check.py"
    script.write_text(
        "import sys,json\nsys.path.insert(0,'/runtime/pdf-deps')\nimport pypdf\n"
        "config=pypdf.Configuration(zlib_maximum_output_length=2097152,jbig2dec_binary=None)\n"
        "print(json.dumps({'version':pypdf.__version__,'zlib_limit':config.zlib_maximum_output_length,"
        "'external_decoder':config.jbig2dec_binary}))\n"
    )
    script.chmod(0o444)
    profile = SandboxProfile(name="read-only-research", uid=os.getuid(), gid=os.getgid(), wall_seconds=10)
    receipt = DockerSandbox(
        tmp_path,
        runtime_mounts=(
            ReadOnlyMount(bundle.directory, "/runtime/pdf-deps"),
            ReadOnlyMount(script, "/runtime/check.py"),
        ),
    ).run(workspace, ("/usr/local/bin/python", "-I", "-B", "/runtime/check.py"), profile)
    assert receipt.reason == "completed" and receipt.exit_code == 0
    assert json.loads(receipt.output) == {"version": PYPDF_VERSION, "zlib_limit": 2097152, "external_decoder": None}
    verify_pdf_bundle(bundle)
    assert not list(bundle.directory.rglob("*.pyc"))
    record_property(
        "pdf_bundle_runtime",
        json.dumps(
            {
                "version": PYPDF_VERSION,
                "bundle_sha256": bundle.manifest_sha256,
                "profile_sha256": receipt.profile_sha256,
                "effective_config_sha256": receipt.effective_config_sha256,
                "scope": "actual readonly Docker import/configuration only; no PDF input/extraction/citation authority",
            },
            sort_keys=True,
        ),
    )
