import hashlib
import json

import pytest

from panestria.contracts.native_context import NativeContextManifest, context_path


def context(files):
    return json.dumps(
        {"intent": "Review selected PUBLIC input", "source_tree": "ab" * 20, "files": files},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


@pytest.mark.parametrize("content", [None, "original π\n"])
def test_metadata_restores_exact_utf8_or_empty_selected_input_without_retaining_file_content(content):
    raw = b"" if content is None else content.encode()
    files = (
        []
        if content is None
        else [{"path": "notes/π.py", "sha256": hashlib.sha256(raw).hexdigest(), "content": content}]
    )
    original = context(files)
    manifest = NativeContextManifest.from_context(original)
    assert '"content"' not in manifest.model_dump_json()
    assert manifest.render({} if content is None else {"notes/π.py": raw}) == original.encode()
    if content is not None:
        with pytest.raises(ValueError, match="file_mismatch"):
            manifest.render({"notes/π.py": b"modified"})


@pytest.mark.parametrize("path", ["../private", ".claude/auth.json", ".env", ".mcp.json", "x\\y", "/etc/passwd", "."])
def test_untrusted_manifest_never_resolves_private_or_ambiguous_paths(path):
    with pytest.raises(ValueError, match="selected_context_path"):
        context_path(path)


def test_noncanonical_and_oversize_inputs_cannot_be_labeled_as_original():
    original = context([])
    with pytest.raises(ValueError, match="not_canonical"):
        NativeContextManifest.from_context(original + " ")
    with pytest.raises(ValueError, match="context_limit"):
        NativeContextManifest.from_context(context([]).replace("PUBLIC", "a" * 17000))
