"""Kokoro speech. Pipelines stay in memory after the first use of each accent."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from saylo.config import TTS_SAMPLE_RATE, TTS_SPEED

logger = logging.getLogger(__name__)

_pipelines: dict[str, object] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class Speech:
    path: Path
    # "voice" is an ogg file Telegram can play as a voice message.
    # "audio" is a wav fallback when ffmpeg is missing.
    kind: str


def synthesize(text: str, lang_code: str, voice: str) -> Speech:
    import numpy as np
    import soundfile as sf

    pipeline = _pipeline(lang_code)
    chunks = []
    for _graphemes, _phonemes, audio in pipeline(text, voice=voice, speed=TTS_SPEED):
        if audio is not None and len(audio) > 0:
            chunks.append(audio)
    if not chunks:
        raise RuntimeError("Kokoro returned no audio.")

    samples = np.concatenate(chunks)
    seconds = len(samples) / TTS_SAMPLE_RATE
    logger.info(
        "kokoro voice=%s lang=%s seconds=%.2f",
        voice,
        lang_code,
        seconds,
    )

    wav_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wav_path = Path(wav_file.name)
    wav_file.close()
    sf.write(wav_path, samples, TTS_SAMPLE_RATE)

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.warning("ffmpeg not found; sending wav instead of a voice message")
        return Speech(wav_path, "audio")

    ogg_path = wav_path.with_suffix(".ogg")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(wav_path),
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-ac",
                "1",
                str(ogg_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")[-400:]
        logger.warning("ffmpeg failed (%s); sending wav", stderr)
        return Speech(wav_path, "audio")

    wav_path.unlink(missing_ok=True)
    return Speech(ogg_path, "voice")


def _pipeline(lang_code: str):
    with _lock:
        cached = _pipelines.get(lang_code)
        if cached is not None:
            return cached
        logger.info("loading Kokoro lang_code=%s", lang_code)
        from kokoro import KPipeline

        pipeline = KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")
        _pipelines[lang_code] = pipeline
        return pipeline
