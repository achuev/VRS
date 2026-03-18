"""
Аудиоплеер на базе mpv с управлением через IPC-сокет.

mpv запускается как дочерний процесс; команды (пауза, следующий трек,
получение статуса) отправляются через Unix-сокет в формате JSON.

Поддерживаемые команды:
  player.play(url, meta)   — воспроизвести трек по URL
  player.pause()           — пауза / снятие паузы
  player.stop()            — остановить воспроизведение
  player.is_playing()      — True если mpv сейчас играет
  player.current_meta      — TrackMeta текущего трека или None
"""

import json
import logging
import os
import socket
import subprocess
import time

import config
from music.client import TrackMeta

logger = logging.getLogger(__name__)

_IPC_TIMEOUT = 2.0      # секунд ждать ответа от mpv
_MPV_STARTUP  = 0.5     # секунд ждать после запуска mpv


class MpvPlayer:

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self.current_meta: TrackMeta | None = None

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    def play(self, url: str, meta: TrackMeta | None = None) -> None:
        """Воспроизвести аудио по прямой ссылке."""
        self.stop()   # убиваем предыдущий экземпляр если был

        self.current_meta = meta
        if meta:
            logger.info(f"Player: ▶ {meta.artist} — {meta.title}")
        else:
            logger.info(f"Player: ▶ {url[:60]}...")

        # Удаляем старый сокет если остался
        _remove_socket()

        cmd = [
            config.MPV_BINARY,
            "--no-video",
            "--quiet",
            f"--input-ipc-server={config.MPV_IPC_SOCKET}",
            url,
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(_MPV_STARTUP)   # ждём поднятия IPC-сокета

    def pause(self) -> None:
        """Переключить паузу."""
        self._ipc_command({"command": ["cycle", "pause"]})

    def stop(self) -> None:
        """Остановить воспроизведение и завершить mpv."""
        if self._proc and self._proc.poll() is None:
            self._ipc_command({"command": ["quit"]})
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self.current_meta = None
        _remove_socket()

    def is_playing(self) -> bool:
        """True если mpv процесс жив и не на паузе."""
        if not self._proc or self._proc.poll() is not None:
            return False
        resp = self._ipc_command({"command": ["get_property", "pause"]})
        if resp is None:
            return False
        return not resp.get("data", True)

    def is_finished(self) -> bool:
        """True если mpv завершил воспроизведение (процесс вышел)."""
        return self._proc is not None and self._proc.poll() is not None

    # ── IPC ───────────────────────────────────────────────────────────────────

    def _ipc_command(self, payload: dict) -> dict | None:
        """
        Отправить JSON-команду в mpv через Unix IPC сокет.
        Возвращает ответ mpv или None при ошибке.
        """
        sock_path = config.MPV_IPC_SOCKET
        if not os.path.exists(sock_path):
            return None

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(_IPC_TIMEOUT)
                s.connect(sock_path)
                s.sendall((json.dumps(payload) + "\n").encode())
                data = s.recv(4096)
                return json.loads(data.decode().strip().splitlines()[-1])
        except Exception as e:
            logger.debug(f"Player IPC error: {e}")
            return None


def _remove_socket() -> None:
    try:
        if os.path.exists(config.MPV_IPC_SOCKET):
            os.remove(config.MPV_IPC_SOCKET)
    except OSError:
        pass
