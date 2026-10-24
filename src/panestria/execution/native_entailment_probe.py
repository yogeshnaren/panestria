"""Pinned PUBLIC-fixture subscription observations, never private claim or task authority."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from panestria.brokers.harness.claude_check import SETTINGS, _hostile_fixture
from panestria.brokers.harness.claude_proposal import MANAGED_PATHS, ClaudeProposalAdapter, ProposalUnavailable
from panestria.brokers.harness.cli_profile import BinaryPin, NativeProbeUnavailable, _unchanged
from panestria.brokers.harness.event_parser import (
    ClaudeEventParser,
    NativeEvent,
    ProtocolRejected,
    _invalid_constant,
    _pairs,
)
from panestria.brokers.harness.process_runner import collect_native
from panestria.contracts.native_model import NativeModel, validate_native_model
from panestria.execution.entailment_probe import ENTAILMENT_RULES
from panestria.verification.entailment import (
    SNLI_SUBSET_SHA256,
    EntailmentPrediction,
    EntailmentScore,
    load_snli_subset,
    score_predictions,
)

BATCH_RUBRIC = ENTAILMENT_RULES + (
    "Classify EVERY provided case independently. Return ONLY one JSON object "
    '{"predictions":[{"case_id":"exact input ID","verdict":"SUPPORTED|CONTRADICTED|INSUFFICIENT|UNKNOWN"}]}. '
    "One prediction per case, no extra fields or explanation, no missing or invented IDs.\n"
)
BATCH_RUBRIC_SHA256 = hashlib.sha256(BATCH_RUBRIC.encode()).hexdigest()


class _PublicFixtureParser(ClaudeEventParser):
    def __init__(self, native_model: NativeModel | None = None) -> None:
        super().__init__(capture_candidate=True, expected_model=validate_native_model(native_model))
        self.model: str | None = None
        self.subscription_overage: bool | None = None
        self.profile_flags: tuple[tuple[str, int | bool], ...] = ()

    def _frame(self, raw: bytes) -> NativeEvent:
        body = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        if isinstance(body, dict) and body.get("type") == "system" and body.get("subtype") == "init":
            arrays = ("tools", "mcp_servers", "skills", "plugins", "slash_commands")
            self.profile_flags = (
                ("expected_model", body.get("model") == (self.expected_model or "claude-haiku-4-5-20251001")),
                ("no_api_key", body.get("apiKeySource") == "none"),
                ("default_permissions", body.get("permissionMode") == "default"),
                *((key + "_count", len(body[key]) if type(body.get(key)) is list else -1) for key in arrays),
            )
            if (
                body.get("model") != (self.expected_model or "claude-haiku-4-5-20251001")
                or body.get("apiKeySource") != "none"
                or body.get("permissionMode") != "default"
                or any(body.get(key) != [] for key in ("tools", "mcp_servers", "skills", "plugins", "slash_commands"))
            ):
                raise ProtocolRejected("unexpected_public_fixture_profile")
            self.model = body["model"]
        if isinstance(body, dict) and body.get("type") == "rate_limit_event":
            value = body.get("rate_limit_info", {}).get("isUsingOverage")
            if value is not None:
                if type(value) is not bool or value is not False:
                    raise ProtocolRejected("unapproved_overage")
                self.subscription_overage = False
        if (
            self.expected_model is not None
            and isinstance(body, dict) and body.get("type") == "result" and body.get("is_error") is False
            and (type(body.get("modelUsage")) is not dict or set(body["modelUsage"]) != {self.expected_model})
        ):
            raise ProtocolRejected("native_model_usage_unconfirmed")
        return super()._frame(raw)


@dataclass(frozen=True)
class NativeEntailmentObservation:
    status: Literal["COMPLETE", "UNAVAILABLE", "REJECTED"]
    reason: str
    fold: Literal["calibration", "qualification"]
    predictions: tuple[EntailmentPrediction, ...]
    score: EntailmentScore | None
    model: str | None
    prompt_sha256: str
    result_sha256: str | None
    observed_overage: bool | None
    rubric_sha256: str = BATCH_RUBRIC_SHA256
    corpus_sha256: str = SNLI_SUBSET_SHA256
    cash_actual_microusd: None = None
    authority: Literal["PUBLIC_NATIVE_OBSERVATION_ONLY"] = "PUBLIC_NATIVE_OBSERVATION_ONLY"
    profile_flags: tuple[tuple[str, int | bool], ...] = ()
    requested_model: NativeModel | None = None


def native_observation_json(observation: NativeEntailmentObservation) -> str:
    body = asdict(observation)
    if observation.requested_model is None:
        body.pop("requested_model")  # Preserve the original legacy observation shape.
    body["predictions"] = [p.model_dump(mode="json") for p in observation.predictions]
    return json.dumps(body, sort_keys=True, allow_nan=False)


def _decode(text: str, requested: set[str]) -> tuple[EntailmentPrediction, ...]:
    if type(text) is not str or len(text.encode()) > 16 * 1024:
        raise ValueError
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4]
    body = json.loads(text, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
    if type(body) is not dict or set(body) != {"predictions"} or type(body["predictions"]) is not list:
        raise ValueError
    predictions = tuple(EntailmentPrediction.model_validate(item) for item in body["predictions"])
    if len(predictions) != len(requested) or {p.case_id for p in predictions} != requested:
        raise ValueError
    return predictions


class NativeEntailmentProbe:
    def __init__(
        self, pin: BinaryPin, config_directory: Path, archive: Path, *, native_model: NativeModel | None = None
    ) -> None:
        self.pin, self.config, self.archive = pin, config_directory, archive
        self.native_model = validate_native_model(native_model)

    def run(
        self,
        corpus_path: Path,
        fold: Literal["calibration", "qualification"],
        *,
        cancel: threading.Event | None = None,
        wall_seconds: float = 120.0,
    ) -> NativeEntailmentObservation:
        selected_model = validate_native_model(self.native_model)
        corpus = load_snli_subset(corpus_path)  # Public immutable bytes ONLY, before auth/process access.
        inputs = corpus.model_inputs(fold)
        payload = json.dumps(
            {"cases": [item.model_dump(mode="json") for item in inputs]}, ensure_ascii=False, separators=(",", ":")
        )
        if len(payload.encode()) > 12 * 1024 or type(wall_seconds) not in {int, float} or not 1 <= wall_seconds <= 120:
            raise ValueError("invalid_public_fixture_batch")
        digest = hashlib.sha256((BATCH_RUBRIC + payload).encode()).hexdigest()
        parser = _PublicFixtureParser(selected_model)

        def stopped(
            status: Literal["UNAVAILABLE", "REJECTED"],
            reason: str,
            result: str | None = None,
        ) -> NativeEntailmentObservation:
            return NativeEntailmentObservation(
                status,
                reason,
                fold,
                (),
                None,
                parser.model,
                digest,
                result,
                parser.subscription_overage,
                profile_flags=parser.profile_flags,
                requested_model=selected_model,
            )

        if cancel is not None and cancel.is_set():
            return stopped("UNAVAILABLE", "cancelled")
        binary_fd = config_fd = -1
        try:
            ClaudeProposalAdapter(self.pin, self.config, self.archive).inspect()
            if any(path.exists() or path.is_symlink() for path in MANAGED_PATHS):
                raise ProposalUnavailable("managed_configuration_present")
            deadline = time.monotonic() + wall_seconds
            binary_fd = os.open(self.pin.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            config_fd = os.open(self.config, os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY)
            _unchanged(self.pin, binary_fd, deadline)
            held = os.fstat(config_fd)
            if (
                self.config.resolve() != self.config
                or held.st_uid != os.getuid()
                or stat.S_IMODE(held.st_mode) != 0o700
            ):
                raise ProposalUnavailable("private_native_profile_required")
            with tempfile.TemporaryDirectory(prefix="panestria-public-nli-", dir="/tmp") as folder:
                root = Path(folder)
                prompt = root / "rubric.txt"
                prompt.write_text(BATCH_RUBRIC)
                prompt.chmod(0o400)
                markers = _hostile_fixture(root)
                settings, mcp = root / "settings.json", root / "mcp.json"
                pins = {prompt: BATCH_RUBRIC_SHA256}
                selected_settings = {
                    **SETTINGS,
                    **(
                        {"availableModels": [selected_model], "fallbackModel": [], "switchModelsOnFlag": False}
                        if selected_model is not None
                        else {}
                    ),
                }
                for path, body in ((settings, selected_settings), (mcp, {"mcpServers": {}})):
                    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                    path.write_bytes(raw)
                    path.chmod(0o400)
                    pins[path] = hashlib.sha256(raw).hexdigest()
                environment = {
                    "PATH": "/usr/bin:/bin",
                    "HOME": folder,
                    "LANG": "C.UTF-8",
                    "CLAUDE_CONFIG_DIR": f"/proc/self/fd/{config_fd}",
                    "DISABLE_AUTOUPDATER": "1",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_TELEMETRY": "1",
                    "DISABLE_ERROR_REPORTING": "1",
                    "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
                    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                    "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
                    "ENABLE_TOOL_SEARCH": "false",
                }
                argv = (
                    f"/proc/self/fd/{binary_fd}",
                    "--safe-mode",
                    "--restricted",
                    "--setting-sources",
                    "",
                    "--settings",
                    str(settings),
                    "--mcp-config",
                    str(mcp),
                    "--strict-mcp-config",
                    "--disable-slash-commands",
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--tools",
                    "",
                    "--permission-prompts",
                    "none",
                    "--permission-mode",
                    "default",
                    "--no-session-persistence",
                    "--max-turns",
                    "2",
                    "--max-budget-usd",
                    "0.25",
                    "--model",
                    selected_model or "haiku",
                    "--system-prompt-file",
                    str(prompt),
                    payload,
                )
                receipt = collect_native(
                    argv,
                    root,
                    environment,
                    parser,
                    wall_seconds=max(0.1, deadline - time.monotonic()),
                    cancel=cancel,
                    output_bytes=256 * 1024,
                    pass_fds=(binary_fd, config_fd),
                )
                _unchanged(self.pin, binary_fd, time.monotonic() + 5)
                current = self.config.lstat()
                if (
                    (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                    or current.st_uid != os.getuid()
                    or stat.S_IMODE(current.st_mode) != 0o700
                    or any(hashlib.sha256(path.read_bytes()).hexdigest() != sha for path, sha in pins.items())
                    or any(path.exists() or path.is_symlink() for path in markers)
                ):
                    raise ProposalUnavailable("native_reference_changed")
                result_sha = parser.result.result_sha256 if parser.result is not None else None
                if cancel is not None and cancel.is_set():
                    return stopped("UNAVAILABLE", "cancelled", result_sha)
                if receipt.status != "CANDIDATE" or parser.candidate_text is None:
                    return stopped("UNAVAILABLE", receipt.reason, result_sha)
                predictions = _decode(parser.candidate_text, {item.case_id for item in inputs})
                return NativeEntailmentObservation(
                    "COMPLETE",
                    "batch_observed",
                    fold,
                    predictions,
                    score_predictions(corpus, fold, predictions),
                    parser.model,
                    digest,
                    result_sha,
                    parser.subscription_overage,
                    profile_flags=parser.profile_flags,
                    requested_model=selected_model,
                )
        except (ProposalUnavailable, NativeProbeUnavailable, OSError):
            return stopped("UNAVAILABLE", "native_profile_or_launch_unavailable")
        except Exception:
            return stopped("REJECTED", "native_fixture_protocol_unconfirmed")
        finally:
            for fd in (binary_fd, config_fd):
                if fd >= 0:
                    os.close(fd)
