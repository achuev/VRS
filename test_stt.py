"""
Тест части 1: запись с микрофона + STT.

Запуск:
    python test_stt.py

Что происходит:
  1. Выводится список микрофонов (чтобы проверить, что USB-mic виден).
  2. Ждём голоса, записываем команду (VAD определит конец автоматически).
  3. Распознаём речь и выводим текст.
"""

import logging
import sys

# Настройка логов: INFO чтобы видеть шаги работы recorder/recognizer
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

import config
from audio.recorder import VoiceRecorder, list_microphones
from stt.recognizer import SpeechRecognizer


def main() -> None:
    print("=" * 60)
    print("VRS — тест записи и распознавания речи")
    print("=" * 60)

    # 1. Показать доступные микрофоны
    print("\nДоступные микрофоны:")
    list_microphones()
    print(
        f"\nИспользуется устройство: "
        f"{'по умолчанию' if config.MIC_DEVICE_INDEX is None else config.MIC_DEVICE_INDEX}"
    )
    print(f"Режим STT: {config.STT_MODE}")
    print()

    recorder = VoiceRecorder()
    recognizer = SpeechRecognizer()

    # 2. Цикл тестирования (Ctrl+C для выхода)
    print("Скажи что-нибудь (Ctrl+C для выхода)...\n")
    try:
        while True:
            print(">> Говори:")
            wav_bytes = recorder.record_to_wav_bytes()

            if not wav_bytes:
                print("   [ничего не записано]\n")
                continue

            print("   Распознаю...")
            text = recognizer.transcribe(wav_bytes)

            if text:
                print(f"   Результат: «{text}»\n")
            else:
                print("   [текст не распознан]\n")

    except KeyboardInterrupt:
        print("\nВыход.")
        sys.exit(0)


if __name__ == "__main__":
    main()
