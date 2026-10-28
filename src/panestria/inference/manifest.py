"""Describe the already startup-verified supported CPU model; no download/selection."""

import hashlib
import json
from pathlib import Path

from panestria.contracts.inference import InferenceUnavailable
from panestria.contracts.model_manifest import ModelManifest
from panestria.inference.artifacts import artifact_hash
from panestria.inference.runtime import IMAGE, MODEL, MODEL_DIGEST


def describe_cpu_model(models: Path) -> ModelManifest:
    """Called only after ModelRuntime verifies every model blob and isolation.

    Bundle digests identify template/license/weights and the containing tokenizer
    artifact. Runtime byte identities are observations, not quality certificates.
    """
    try:
        raw = (models / "manifests/registry.ollama.ai/library/qwen2.5/1.5b-instruct").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MODEL_DIGEST:
            raise ValueError
        document = json.loads(raw)
        layers = {
            part["mediaType"].removeprefix("application/vnd.ollama.image."): part["digest"][7:]
            for part in document["layers"]
        }
        config = models / "blobs" / document["config"]["digest"].replace(":", "-")
        if artifact_hash(config) != document["config"]["digest"][7:]:
            raise ValueError
        quantization = json.loads(config.read_bytes())["file_type"]
        root = Path("/usr/local/lib/ollama")
        entries = sorted(root.rglob("*"))
        if not root.is_dir() or not 1 <= len(entries) <= 4096:
            raise ValueError
        libraries = hashlib.sha256()
        for path in entries:
            if path.is_file():
                libraries.update(str(path.relative_to(root)).encode() + b"\0" + artifact_hash(path.resolve()).encode())
        return ModelManifest(
            model_ref=MODEL,
            model_bundle_sha256=MODEL_DIGEST,
            weights_sha256=layers["model"],
            tokenizer_container_sha256=layers["model"],
            template_sha256=layers["template"],
            system_sha256=layers["system"],
            quantization=quantization,
            runtime_image=IMAGE,
            engine_sha256=artifact_hash(Path("/usr/local/bin/ollama").resolve()),
            libraries_sha256=libraries.hexdigest(),
            bridge_sha256=artifact_hash(Path(__file__).with_name("runtime_bridge.py")),
            license_refs=(layers["license"],),
        )
    except (OSError, ValueError, KeyError, TypeError):
        raise InferenceUnavailable("model_manifest_unavailable") from None
