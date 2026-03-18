"""
Модуль обнаружения wake word — кодовой фразы-активатора.

Принцип работы:
  Используем Vosk в режиме ограниченной грамматики: вместо полного словаря
  передаём JSON-список из наших фраз-активаторов + "[unk]" для всего остального.
  В таком режиме Vosk игнорирует неизвестные слова и тратит минимум CPU,
  что критично для Raspberry Pi 3.

  Поток:
    Микрофон → чанки по 30ms → Vosk (grammar mode) → совпадение? → callback()

Использование:
    detector = WakeWordDetector(on_detected=my_callback)
    detector.start()        # запускает фоновый поток
    ...
    detector.stop()

  Или как контекстный менеджер:
    with WakeWordDetector(on_detected=my_callback):
        time.sleep(60)
"""

import json
import logging
import threading
import time

import sounddevice as sd

import config

logger = logging.getLogger(__name__)

# Размер чанка для детектора: 30ms при 16000 Hz = 480 фреймов = 960 байт (int16)
_CHUNK_FRAMES = int(config.SAMPLE_RATE * 0.03)


def _load_vosk_model():
    """Загрузить Vosk-модель (та же что для STT, переиспользуем)."""
    from pathlib import Path
    from vosk import Model

    model_path = Path(config.VOSK_MODEL_PATH)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Vosk модель не найдена: {model_path}\n"
            "Скачай с https://alphacephei.com/vosk/models (vosk-model-ru-0.42)"
        )
    logger.info(f"WakeWord: загружаем Vosk-модель из {model_path}...")
    model = Model(str(model_path))
    logger.info("WakeWord: модель загружена.")
    return model


def _make_recognizer(model, wake_words: list[str]):
    """
    Создать KaldiRecognizer с грамматикой из фраз-активаторов.
    "[unk]" — специальный токен Vosk для всего что не попало в список.
    Без него Vosk пытается подобрать ближайшую фразу из грамматики,
    что даёт ложные срабатывания на случайный шум.
    """
    from vosk import KaldiRecognizer

    grammar = json.dumps([*wake_words, "[unk]"], ensure_ascii=False)
    rec = KaldiRecognizer(model, config.SAMPLE_RATE, grammar)
    rec.SetWords(False)
    return rec


class WakeWordDetector:
    """
    Детектор wake word на основе Vosk с ограниченной грамматикой.

    Параметры:
        on_detected  — функция без аргументов, вызывается при срабатывании.
        wake_words   — список фраз (по умолчанию из config.WAKE_WORDS).
    """

    def __init__(
        self,
        on_detected: callable,
        wake_words: list[str] | None = None,
    ) -> None:
        self._on_detected = on_detected
        self._wake_words = [w.lower() for w in (wake_words or config.WAKE_WORDS)]
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    def start(self) -> None:
        """Запустить детектор в фоновом потоке."""
        if self._thread and self._thread.is_alive():
            logger.warning("WakeWord: детектор уже запущен.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="wake-word")
        self._thread.start()
        logger.info(f"WakeWord: детектор запущен. Фразы: {self._wake_words}")

    def stop(self) -> None:
        """Остановить детектор."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WakeWord: детектор остановлен.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

    # ── Внутренняя логика ─────────────────────────────────────────────────────

    def _run(self) -> None:
        """Основной цикл детектора (выполняется в фоновом потоке)."""
        if self._model is None:
            self._model = _load_vosk_model()

        rec = _make_recognizer(self._model, self._wake_words)

        with sd.RawInputStream(
            samplerate=config.SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=config.MIC_DEVICE_INDEX,
            blocksize=_CHUNK_FRAMES,
        ) as stream:
            logger.info("WakeWord: слушаю...")
            while not self._stop_event.is_set():
                data, _ = stream.read(_CHUNK_FRAMES)
                pcm = bytes(data)

                if rec.AcceptWaveform(pcm):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").strip().lower()
                else:
                    # Частичный результат — реагируем немедленно, не ждём паузы
                    partial = json.loads(rec.PartialResult())
                    text = partial.get("partial", "").strip().lower()

                if text and self._is_wake_word(text):
                    logger.info(f"WakeWord: активация! ({text!r})")
                    # Сбрасываем состояние распознавателя
                    rec = _make_recognizer(self._model, self._wake_words)
                    # Небольшая пауза чтобы пользователь успел начать говорить
                    time.sleep(config.WAKE_PAUSE_SEC)
                    self._on_detected()

    def _is_wake_word(self, text: str) -> bool:
        """Проверить, содержит ли текст одну из фраз-активаторов."""
        for phrase in self._wake_words:
            if phrase in text:
                return True
        return False
