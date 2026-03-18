"""
VRS — Voice Radio Station
Главный цикл приложения.

Поток выполнения:
  1. WakeWordDetector слушает микрофон в фоновом потоке.
  2. При активации → запись команды (VAD) → STT → NLU.
  3. По Intent:
       play_track / play_artist → YandexMusicClient.find_track() → MpvPlayer.play()
       my_wave                  → YandexMusicClient.my_wave()    → MpvPlayer.play()
                                  + автоподгрузка следующего батча когда трек заканчивается
       unknown                  → игнорируем / логируем
  4. Во время воспроизведения детектор продолжает слушать:
       новая команда → прерывает текущий трек и запускает новый.

Запуск:
    python main.py
"""

import logging
import signal
import sys
import threading
import time

import config
from audio.recorder import VoiceRecorder
from music.client import YandexMusicClient, TrackMeta
from music.player import MpvPlayer
from nlu.intent import Intent
from nlu.parser import CommandParser
from stt.recognizer import SpeechRecognizer
from wake_word.detector import WakeWordDetector

# ── Логирование ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vrs.main")


# =============================================================================
# Основная логика
# =============================================================================

class VRS:
    def __init__(self) -> None:
        self.recorder   = VoiceRecorder()
        self.recognizer = SpeechRecognizer()
        self.parser     = CommandParser()
        self.music      = YandexMusicClient()
        self.player     = MpvPlayer()

        # Блокировка: не обрабатываем новую команду пока идёт предыдущая
        self._busy = threading.Lock()

        # Очередь треков для режима "Моя волна"
        self._wave_queue: list[tuple[str, TrackMeta]] = []
        self._wave_mode  = False

        # Фоновый поток для автоподгрузки "Моей волны"
        self._wave_thread: threading.Thread | None = None
        self._shutdown = threading.Event()

    # ── Точка входа ───────────────────────────────────────────────────────────

    def run(self) -> None:
        logger.info("VRS запускается...")
        print(f"\n{'='*50}")
        print("  VRS — Voice Radio Station")
        print(f"  Фраза активации: {config.WAKE_WORDS[0]!r}")
        print(f"{'='*50}\n")

        # Запускаем поток автоперехода к следующему треку
        self._wave_thread = threading.Thread(
            target=self._wave_watchdog, daemon=True, name="wave-watchdog"
        )
        self._wave_thread.start()

        with WakeWordDetector(on_detected=self._on_wake_word):
            print("Слушаю... (Ctrl+C для выхода)\n")
            try:
                while not self._shutdown.is_set():
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass

        self._shutdown.set()
        self.player.stop()
        print("\nVRS остановлен.")

    # ── Wake word callback ────────────────────────────────────────────────────

    def _on_wake_word(self) -> None:
        """Вызывается детектором в его потоке при каждой активации."""
        if not self._busy.acquire(blocking=False):
            # Уже обрабатываем команду — игнорируем повторное срабатывание
            return
        try:
            self._handle_command()
        finally:
            self._busy.release()

    # ── Обработка команды ─────────────────────────────────────────────────────

    def _handle_command(self) -> None:
        print("[!] Активация! Говори команду...")

        # 1. Запись
        wav = self.recorder.record_to_wav_bytes()
        if not wav:
            print("    [тишина]\n")
            return

        # 2. STT
        text = self.recognizer.transcribe(wav)
        if not text:
            print("    [не распознано]\n")
            return
        print(f"    Команда: «{text}»")

        # 3. NLU
        intent = self.parser.parse(text)
        logger.info(f"Intent: {intent}")

        # 4. Выполнение
        self._execute(intent)

    # ── Выполнение интента ────────────────────────────────────────────────────

    def _execute(self, intent: Intent) -> None:
        if intent.action == "my_wave":
            self._start_wave()

        elif intent.action in ("play_track", "play_artist"):
            self._play_from_intent(intent)

        else:
            print("    [команда не распознана]\n")

    def _play_from_intent(self, intent: Intent) -> None:
        self._wave_mode = False
        self._wave_queue.clear()

        print("    Ищу в Яндекс Музыке...")
        url, meta = self.music.find_track(
            track=intent.track,
            artist=intent.artist,
        )

        if not url:
            print("    [трек не найден]\n")
            return

        print(f"    ▶  {meta.artist} — {meta.title}\n")
        self.player.play(url, meta)

    def _start_wave(self) -> None:
        print("    Загружаю Мою волну...")
        tracks = self.music.my_wave()

        if not tracks:
            print("    [Моя волна недоступна]\n")
            return

        self._wave_mode = True
        self._wave_queue = list(tracks)
        self._play_next_from_queue()

    def _play_next_from_queue(self) -> None:
        if not self._wave_queue:
            return

        url, meta = self._wave_queue.pop(0)
        print(f"    ▶  {meta.artist} — {meta.title}\n")
        self.player.play(url, meta)

    # ── Watchdog: автопереход к следующему треку в режиме волны ───────────────

    def _wave_watchdog(self) -> None:
        """
        Фоновый поток: следит за окончанием трека в режиме "Моя волна"
        и переключает на следующий.
        """
        while not self._shutdown.is_set():
            time.sleep(1)

            if not self._wave_mode:
                continue

            if not self.player.is_finished():
                continue

            # Трек закончился — берём следующий из очереди
            if not self._wave_queue:
                # Очередь пуста — подгружаем новый батч
                logger.info("Wave: подгружаем следующий батч...")
                tracks = self.music.next_wave_batch()
                self._wave_queue = list(tracks)

            if self._wave_queue:
                self._play_next_from_queue()
            else:
                logger.warning("Wave: батч пустой, воспроизведение остановлено.")
                self._wave_mode = False


# =============================================================================
# Точка запуска
# =============================================================================

def _handle_sigterm(signum, frame):
    """Корректное завершение по SIGTERM (systemd stop)."""
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    VRS().run()
