"""Explicit metadata fixture: NOT an observed runtime/cache/quality certificate."""

from panestria.contracts.model_manifest import ModelManifest
from panestria.inference.runtime import IMAGE, MODEL, MODEL_DIGEST


def model_manifest(**changes):
    values = dict(
        model_ref=MODEL, model_bundle_sha256=MODEL_DIGEST, weights_sha256="1" * 64,
        tokenizer_container_sha256="1" * 64, template_sha256="2" * 64, system_sha256="3" * 64,
        quantization="Q4_K_M", runtime_image=IMAGE, engine_sha256="4" * 64,
        libraries_sha256="5" * 64, bridge_sha256="6" * 64, license_refs=("7" * 64,),
    )
    return ModelManifest.model_validate({**values, **changes})
