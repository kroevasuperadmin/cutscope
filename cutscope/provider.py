from __future__ import annotations

import base64
import mimetypes
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .models import AttemptOutcome, AttemptResult, Shot, Submission


class VideoProvider(ABC):
    """The one provider seam used by the Slice 1 orchestrator."""

    name: str
    model: str

    @abstractmethod
    def submit(self, shot: Shot, prompt: str) -> Submission:
        """Submit one video generation and return its long-running operation."""

    @abstractmethod
    def poll(self, submission: Submission) -> AttemptResult:
        """Poll one long-running operation to a terminal result."""


@dataclass(frozen=True)
class VeoCostEstimator:
    """Published 720p, video-only USD/second estimates; override in code only after review."""

    model: str

    def estimate(self, duration_seconds: int) -> float:
        if self.model.startswith("veo-3.1-fast"):
            per_second = 0.08
        elif self.model.startswith("veo-3.1"):
            per_second = 0.20
        elif self.model.startswith("veo-2.0"):
            per_second = 0.50
        else:
            raise ValueError(f"No reviewed cost estimate for Veo model {self.model!r}.")
        return round(duration_seconds * per_second, 4)


class VeoVertexProvider(VideoProvider):
    """Vertex AI Veo implementation. No other video or model provider is used."""

    name = "gcp.vertex_ai.veo"

    def __init__(self, client: Any, config: RuntimeConfig) -> None:
        self._client = client
        self.model = config.veo_model
        self._poll_interval_seconds = config.poll_interval_seconds
        self._poll_timeout_seconds = config.poll_timeout_seconds
        self._resolution = config.veo_resolution
        self._generate_audio = config.veo_generate_audio

    def submit(self, shot: Shot, prompt: str) -> Submission:
        from google.genai import types

        source_kwargs: dict[str, Any] = {"prompt": prompt}
        if shot.reference_image_path:
            source_kwargs["image"] = _load_reference_image(types, shot.reference_image_path)
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=shot.expected_duration_seconds,
            resolution=self._resolution,
            generate_audio=self._generate_audio,
            enhance_prompt=True,
        )
        operation = self._client.models.generate_videos(
            model=self.model,
            source=types.GenerateVideosSource(**source_kwargs),
            config=config,
        )
        return Submission(operation=operation, operation_name=str(getattr(operation, "name", "unknown-operation")))

    def poll(self, submission: Submission) -> AttemptResult:
        operation = submission.operation
        deadline = time.monotonic() + self._poll_timeout_seconds
        while not bool(getattr(operation, "done", False)):
            if time.monotonic() >= deadline:
                return AttemptResult(
                    AttemptOutcome.TIMEOUT,
                    operation_name=submission.operation_name,
                    reason=f"Veo operation exceeded {self._poll_timeout_seconds:g} seconds.",
                )
            time.sleep(self._poll_interval_seconds)
            try:
                operation = self._client.operations.get(operation)
            except Exception as exc:
                return AttemptResult(
                    _classify_exception(exc),
                    operation_name=submission.operation_name,
                    reason=_short_error(exc),
                )

        if getattr(operation, "error", None):
            error = getattr(operation, "error")
            return AttemptResult(
                _classify_text(str(error)),
                operation_name=submission.operation_name,
                reason=_short_text(str(error)),
            )

        response = getattr(operation, "response", None) or getattr(operation, "result", None)
        if response is None:
            return AttemptResult(
                AttemptOutcome.ERROR,
                operation_name=submission.operation_name,
                reason="Veo completed without a result.",
            )
        filtered_count = getattr(response, "rai_media_filtered_count", 0) or 0
        filtered_reasons = getattr(response, "rai_media_filtered_reasons", None) or []
        if filtered_count or filtered_reasons:
            reason = "; ".join(str(item) for item in filtered_reasons) or "Veo safety filtering."
            return AttemptResult(AttemptOutcome.REFUSED, submission.operation_name, reason=_short_text(reason))
        generated = getattr(response, "generated_videos", None) or []
        if not generated:
            return AttemptResult(
                AttemptOutcome.ERROR,
                operation_name=submission.operation_name,
                reason="Veo completed without a generated video or safety refusal.",
            )
        video = getattr(generated[0], "video", None)
        asset_uri = getattr(video, "uri", None) if video else None
        return AttemptResult(AttemptOutcome.SUCCESS, submission.operation_name, asset_uri=asset_uri)


def _load_reference_image(types: Any, source_path: Path) -> Any:
    if not source_path.exists():
        raise ValueError(f"Reference image not found: {source_path}")
    if source_path.suffix == ".base64":
        try:
            raw = base64.b64decode(source_path.read_text(encoding="ascii").strip(), validate=True)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"Reference image base64 is invalid: {source_path}") from exc
        suffix = source_path.with_suffix("").suffix or ".png"
        # The SDK factory gives the file its correct MIME type without Pillow or another dependency.
        with tempfile.TemporaryDirectory(prefix="cutscope-reference-") as temp_dir:
            decoded_path = Path(temp_dir) / f"reference{suffix}"
            decoded_path.write_bytes(raw)
            return types.Image.from_file(location=str(decoded_path))
    mime_type, _ = mimetypes.guess_type(source_path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError(
            f"Reference image must be PNG, JPEG, or WebP (got {source_path.name!r})."
        )
    return types.Image.from_file(location=str(source_path))


def _classify_exception(exc: Exception) -> AttemptOutcome:
    return _classify_text(str(exc))


def _classify_text(value: str) -> AttemptOutcome:
    lowered = value.lower()
    refusal_markers = (
        "safety",
        "responsible ai",
        "policy violation",
        "content policy",
        "blocked",
        "filtered",
        "prohibited",
    )
    return AttemptOutcome.REFUSED if any(marker in lowered for marker in refusal_markers) else AttemptOutcome.ERROR


def _short_error(exc: Exception) -> str:
    return _short_text(str(exc) or type(exc).__name__)


def _short_text(value: str) -> str:
    return value.replace("\n", " ").strip()[:400]
