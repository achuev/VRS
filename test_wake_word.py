"""
Тест части 2: wake word + запись + STT вместе.

Запуск:
    python test_wake_word.py

Что происходит:
  1. Детектор запускается в фоне и непрерывно слушает микрофон.
  2. При обнаружении фразы-активатора ("привет станция") —
     записывается команда (VAD определяет конец).
  3. Команда распознаётся через STT и выводится на экран.
  4. Детектор сразу снова начинает слушать.
  Ctrl+C для выхода.
"""

import logging
import sys
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

import config
from audio.recorder import VoiceRecorder
from stt.recognizer import SpeechRecognizer
from wake_word.detector import WakeWordDetector

recorder = VoiceRecorder()
recognizer = SpeechRecognizer()

# Флаг: не запускать новую запись пока идёт предыдущая
_recording_lock = threading.Lock()


def on_wake_word():
    """Вызывается детектором при каждом срабатывании."""
    if not _recording_lock.acquire(blocking=False):
        # Уже записываем — игнорируем повторный триггер
        return

    try:
        print("\n[!] Активация! Говори команду...")
        wav_bytes = recorder.record_to_wav_bytes()

        if not wav_bytes:
            print("    [тишина, ничего не записано]")
            return

        print("    Распознаю...")
        text = recognizer.transcribe(wav_bytes)

        if text:
            print(f"    Команда: «{text}»\n")
        else:
            print("    [текст не распознан]\n")

    finally:
        _recording_lock.release()


def main() -> None:
    print("=" * 60)
    print("VRS — тест wake word")
    print("=" * 60)
    print(f"\nФразы-активаторы: {config.WAKE_WORDS}")
    print("Скажи фразу-активатор, затем голосовую команду.")
    print("Ctrl+C для выхода.\n")

    with WakeWordDetector(on_detected=on_wake_word):
        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nВыход.")
            sys.exit(0)


if __name__ == "__main__":
    main()
