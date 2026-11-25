"""Trusted, owner-invoked setup of the pinned worker image.

Workers launch with ``pull=never``, so the image must already be present. This
module is the only place that downloads it, and only by its pinned digest.
"""

from __future__ import annotations

import subprocess
from typing import Literal

from panestria.sandbox.profiles import DEFAULT_IMAGE

INSPECT_TIMEOUT_SECONDS = 10
PULL_TIMEOUT_SECONDS = 180

ImageStatus = Literal["present", "pulled"]


class ImageUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _docker(*args: str, timeout: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError:
        raise ImageUnavailable("docker_unavailable") from None
    except subprocess.TimeoutExpired:
        raise ImageUnavailable("worker_image_timeout") from None


def prepare_worker_image() -> ImageStatus:
    """Ensure the pinned image is present locally; pull it by digest if it is not."""
    if _docker("image", "inspect", DEFAULT_IMAGE, timeout=INSPECT_TIMEOUT_SECONDS).returncode == 0:
        return "present"
    if _docker("pull", DEFAULT_IMAGE, timeout=PULL_TIMEOUT_SECONDS).returncode != 0:
        raise ImageUnavailable("worker_image_pull_failed")
    if _docker("image", "inspect", DEFAULT_IMAGE, timeout=INSPECT_TIMEOUT_SECONDS).returncode != 0:
        raise ImageUnavailable("worker_image_pull_failed")
    return "pulled"
