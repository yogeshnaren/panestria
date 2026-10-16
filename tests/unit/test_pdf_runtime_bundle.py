"""Real installed wheel/filesystem checks only; no PDF input parsed on host."""

import os
from dataclasses import replace

import pytest

import panestria.brokers.research.pdf_bundle as module
from panestria.brokers.research.pdf_bundle import PdfBundleUnavailable, stage_pdf_bundle, verify_pdf_bundle


def test_pinned_wheel_bundle_includes_only_reviewed_package_and_bsd_license(tmp_path):
    bundle = stage_pdf_bundle(tmp_path / "pdf")
    assert bundle.file_count == 61 and bundle.size_bytes == 1736355
    assert "Redistribution" in (bundle.directory / "LICENSE-pypdf").read_text()
    assert (bundle.directory / "pypdf" / "_reader.py").is_file()
    assert not list(bundle.directory.rglob("*.pyc"))
    verify_pdf_bundle(bundle)


@pytest.mark.parametrize("mutation", ["content", "extra", "missing", "mode", "symlink", "hardlink", "manifest"])
def test_changed_dependency_tree_never_verifies(tmp_path, mutation):
    bundle = stage_pdf_bundle(tmp_path / "pdf")
    target = bundle.directory / "pypdf" / "_reader.py"
    if mutation == "content":
        target.chmod(0o600)
        target.write_bytes(b"changed")
        target.chmod(0o400)
    elif mutation == "extra":
        p = bundle.directory / "pypdf" / "unreviewed.py"
        p.write_bytes(b"changed")
        p.chmod(0o400)
    elif mutation == "missing":
        target.unlink()
    elif mutation == "mode":
        target.chmod(0o666)
    elif mutation == "symlink":
        target.unlink()
        target.symlink_to(tmp_path / "owner-data")
    elif mutation == "hardlink":
        os.link(target, tmp_path / "alias")
    else:
        p = bundle.directory / "manifest.json"
        p.chmod(0o600)
        p.write_bytes(b"{}")
        p.chmod(0o400)
    with pytest.raises(PdfBundleUnavailable, match="pdf_bundle_integrity_unconfirmed"):
        verify_pdf_bundle(bundle)


def test_changed_receipt_is_not_a_new_dependency_pin(tmp_path):
    bundle = stage_pdf_bundle(tmp_path / "pdf")
    for altered in [
        replace(bundle, manifest_sha256="00" * 32),
        replace(bundle, file_count=62),
        replace(bundle, size_bytes=1),
    ]:
        with pytest.raises(PdfBundleUnavailable):
            verify_pdf_bundle(altered)


def test_existing_owner_directory_and_files_preserved(tmp_path):
    dest = tmp_path / "owner"
    dest.mkdir()
    marker = dest / "owner.txt"
    marker.write_text("owner data")
    with pytest.raises(PdfBundleUnavailable):
        stage_pdf_bundle(dest)
    assert marker.read_text() == "owner data"


def test_corrupt_installed_bytes_refused_before_creating_destination(tmp_path, monkeypatch):
    original = module._safe_file

    def corrupt(path, **kwargs):
        raw = original(path, **kwargs)
        return raw + b"changed" if path.name == "_reader.py" else raw

    monkeypatch.setattr(module, "_safe_file", corrupt)
    with pytest.raises(PdfBundleUnavailable):
        stage_pdf_bundle(tmp_path / "pdf")
    assert not (tmp_path / "pdf").exists()


def test_unsafe_parent_and_source_fifo_never_open_or_create_bundle(tmp_path):
    parent = tmp_path / "unsafe"
    parent.mkdir(mode=0o755)
    with pytest.raises(PdfBundleUnavailable):
        stage_pdf_bundle(parent / "pdf")
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError):
        module._safe_file(fifo)
