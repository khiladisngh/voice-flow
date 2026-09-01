"""CUDA-accelerated speech-to-text via faster-whisper.

The bundled NVIDIA cuBLAS/cuDNN shared objects must be loaded into the process
with RTLD_GLOBAL *before* faster_whisper pulls in ctranslate2, otherwise
ctranslate2 fails with "libcublas.so.12 is not found". That ordering is
load-bearing: do not hoist the faster_whisper import to the top of the file.
"""

import ctypes
import sys
from pathlib import Path


def _ensure_cuda_libs():
    """Load bundled nvidia cuBLAS and cuDNN libraries if present in venv."""
    sp = (
        Path(sys.prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    for lib_dir in [sp / "nvidia" / "cublas" / "lib", sp / "nvidia" / "cudnn" / "lib"]:
        if lib_dir.exists():
            for so in sorted(lib_dir.glob("*.so*")):
                try:
                    ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                except Exception:
                    pass


_ensure_cuda_libs()

from faster_whisper import WhisperModel  # noqa: E402  (see module docstring)


class Transcriber:
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        language: str | None = None,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str) -> tuple[str, str, float]:
        """
        Transcribe the audio file.
        Returns: (transcribed_text, detected_language, duration)
        """
        segments, info = self.model.transcribe(
            audio_path,
            beam_size=1,
            language=self.language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            initial_prompt="Hello, this is a clean dictation with proper punctuation and formatting.",
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, info.language, info.duration
