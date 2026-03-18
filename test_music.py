"""
Тест части 4: Yandex Music клиент + mpv плеер.

Запуск:
    python test_music.py

Что проверяем:
  1. Авторизация в Yandex Music по токену.
  2. Поиск трека по запросу из командной строки.
  3. Воспроизведение через mpv.
  4. Режим "Моя волна".
Требует: YANDEX_MUSIC_TOKEN в config.py и установленный mpv.
"""

import logging
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from music.client import YandexMusicClient
from music.player import MpvPlayer

client = YandexMusicClient()
player = MpvPlayer()


def play_track_interactive() -> None:
    print("\n── Поиск трека ───────────────────────────────────")
    track  = input("Название трека  (Enter чтобы пропустить): ").strip() or None
    artist = input("Исполнитель     (Enter чтобы пропустить): ").strip() or None

    if not track and not artist:
        print("Укажи хотя бы что-нибудь.")
        return

    url, meta = client.find_track(track=track, artist=artist)
    if not url:
        print("Трек не найден или не удалось получить ссылку.")
        return

    print(f"\n▶  {meta.artist} — {meta.title}  ({meta.duration_sec // 60}:{meta.duration_sec % 60:02d})")
    player.play(url, meta)
    _wait_for_input()


def play_my_wave() -> None:
    print("\n── Моя волна ─────────────────────────────────────")
    tracks = client.my_wave()
    if not tracks:
        print("Не удалось загрузить Мою волну.")
        return

    for url, meta in tracks:
        if player.is_playing() or not player.is_finished():
            # Ждём конца текущего трека или команды skip
            print("  (s — следующий, q — выход)")
            _wait_or_next(player)

        print(f"\n▶  {meta.artist} — {meta.title}")
        player.play(url, meta)

    print("Батч закончился.")
    _wait_for_input()


def _wait_for_input() -> None:
    """Ждём пока играет, p — пауза, q — стоп."""
    print("  (p — пауза/продолжить, q — стоп)")
    while not player.is_finished():
        try:
            cmd = _nonblocking_input()
        except KeyboardInterrupt:
            break
        if cmd == "p":
            player.pause()
        elif cmd == "q":
            break
        time.sleep(0.3)
    player.stop()


def _wait_or_next(p: MpvPlayer) -> None:
    while not p.is_finished():
        cmd = _nonblocking_input()
        if cmd in ("s", "q"):
            p.stop()
            break
        time.sleep(0.3)


def _nonblocking_input() -> str:
    """Читаем символ без блокировки (только Unix)."""
    import select
    if select.select([sys.stdin], [], [], 0.0)[0]:
        return sys.stdin.readline().strip().lower()
    return ""


MENU = """
╔══════════════════════════════════════╗
║   VRS — тест Yandex Music + mpv     ║
╠══════════════════════════════════════╣
║  1. Найти и воспроизвести трек       ║
║  2. Моя волна                        ║
║  q. Выход                            ║
╚══════════════════════════════════════╝
"""


def main() -> None:
    print(MENU)
    while True:
        try:
            choice = input("Выбор: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "1":
            play_track_interactive()
        elif choice == "2":
            play_my_wave()
        elif choice == "q":
            break
        else:
            print("Неверный выбор.")

    player.stop()
    print("Выход.")


if __name__ == "__main__":
    main()
