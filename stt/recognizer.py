"""
Модуль Speech-to-Text: преобразует голосовую запись в текст на русском языке.

Поддерживаемые режимы (config.STT_MODE):
  "groq"  — Groq Whisper API (облако, быстро, бесплатно до лимита)
  "vosk"  — локально на устройстве (офлайн, медленнее)
  "auto"  — сначала Groq, при ошибке — Vosk
"""

import io
import json
import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)


# ── Groq Whisper ──────────────────────────────────────────────────────────────

def _transcribe_groq(wav_bytes: bytes) -> str:
    """
    Отправить WAV-байты в Groq Whisper API и получить текст.
    Используем whisper-large-v3-turbo: он поддерживает русский и работает быстро.
    """
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Установи groq: pip install groq")

    if not config.GROQ_API_KEY or config.GROQ_API_KEY == "YOUR_GROQ_API_KEY":
        raise ValueError("Укажи GROQ_API_KEY в config.py")

    client = Groq(api_key=config.GROQ_API_KEY)

    # Groq API принимает file-like объект с именем файла
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"

    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model=config.GROQ_WHISPER_MODEL,
        language=config.LANGUAGE,
        response_format="text",
    )

    # response_format="text" возвращает строку напрямую
    text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
    logger.info(f"Groq STT: «{text}»")
    return text


# ── Vosk ──────────────────────────────────────────────────────────────────────

_vosk_model = None   # ленивая загрузка — модель грузится один раз при первом вызове


def _get_vosk_model():
    global _vosk_model
    if _vosk_model is not None:
        return _vosk_model

    try:
        from vosk import Model
    except ImportError:
        raise ImportError("Установи vosk: pip install vosk")

    model_path = Path(config.VOSK_MODEL_PATH)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Vosk модель не найдена: {model_path}\n"
            "Скачай с https://alphacephei.com/vosk/models (vosk-model-ru-0.42)\n"
            f"и распакуй в папку: {model_path}"
        )

    logger.info(f"Vosk: загружаем модель из {model_path} ...")
    _vosk_model = Model(str(model_path))
    logger.info("Vosk: модель загружена.")
    return _vosk_model


def _transcribe_vosk(wav_bytes: bytes) -> str:
    """
    Распознать речь локально через Vosk.
    Принимает WAV-байты (16-bit, mono, 16000 Hz).
    """
    try:
        from vosk import KaldiRecognizer
    except ImportError:
        raise ImportError("Установи vosk: pip install vosk")

    import wave

    model = _get_vosk_model()
    recognizer = KaldiRecognizer(model, config.SAMPLE_RATE)
    recognizer.SetWords(False)

    # Парсим WAV и читаем PCM-данные
    with io.BytesIO(wav_bytes) as buf:
        with wave.open(buf, "rb") as wf:
            pcm = wf.readframes(wf.getnframes())

    # Скармливаем данные по чанкам
    chunk_size = 4000
    for i in range(0, len(pcm), chunk_size):
        recognizer.AcceptWaveform(pcm[i : i + chunk_size])

    result = json.loads(recognizer.FinalResult())
    text = result.get("text", "").strip()
    logger.info(f"Vosk STT: «{text}»")
    return text


# ── Публичный интерфейс ───────────────────────────────────────────────────────

class SpeechRecognizer:
    """
    Единая точка входа для STT.

    Пример:
        recognizer = SpeechRecognizer()
        text = recognizer.transcribe(wav_bytes)
    """

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode or config.STT_MODE

    def transcribe(self, wav_bytes: bytes) -> str:
        """
        Принимает WAV-байты, возвращает распознанный текст.
        При пустом вводе возвращает пустую строку.
        """
        if not wav_bytes:
            return ""

        if self.mode == "groq":
            return _transcribe_groq(wav_bytes)

        if self.mode == "vosk":
            return _transcribe_vosk(wav_bytes)

        # auto: groq с fallback на vosk
        try:
            return _transcribe_groq(wav_bytes)
        except Exception as e:
            logger.warning(f"Groq STT недоступен ({e}), fallback на Vosk.")
            return _transcribe_vosk(wav_bytes)
