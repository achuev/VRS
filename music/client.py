"""
Обёртка над Yandex Music API.

Умеет:
  - Искать трек по названию и/или исполнителю → прямая ссылка на аудио
  - Включать исполнителя (топ треков)
  - Запускать режим "Моя волна" (rotor onyourwave) → батч прямых ссылок
  - Подгружать следующий батч "Моей волны" (для бесконечного воспроизведения)

Использование:
    client = YandexMusicClient()

    # Трек
    url, meta = client.find_track(track="Кукушка", artist="Кино")

    # Исполнитель (первый топ-трек)
    url, meta = client.find_track(artist="Ария")

    # Моя волна — возвращает список (url, meta)
    tracks = client.my_wave()
"""

import logging
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)


@dataclass
class TrackMeta:
    """Мета-информация о треке для отображения."""
    title: str
    artist: str
    duration_sec: int
    track_id: int | None = None


class YandexMusicClient:

    def __init__(self) -> None:
        self._client = None   # ленивая инициализация

    def _get_client(self):
        if self._client is not None:
            return self._client

        try:
            from yandex_music import Client
        except ImportError:
            raise ImportError("Установи yandex-music: pip install yandex-music")

        token = config.YANDEX_MUSIC_TOKEN
        if not token or token == "YOUR_YANDEX_MUSIC_TOKEN":
            raise ValueError(
                "Укажи YANDEX_MUSIC_TOKEN в config.py.\n"
                "Инструкция: https://github.com/MarshalX/yandex-music-api/discussions/513"
            )

        logger.info("YandexMusic: авторизация...")
        self._client = Client(token).init()
        logger.info(f"YandexMusic: авторизован как {self._client.me.account.display_name!r}")
        return self._client

    # ── Внутренние хелперы ────────────────────────────────────────────────────

    def _get_direct_url(self, track) -> str | None:
        """Получить прямую ссылку на аудио трека."""
        try:
            info_list = track.get_download_info(get_direct_links=True)
            if not info_list:
                return None
            # Предпочитаем mp3 с максимальным битрейтом
            mp3 = [i for i in info_list if i.codec == "mp3"]
            best = max(mp3 or info_list, key=lambda i: i.bitrate_in_kbps)
            return best.direct_link
        except Exception as e:
            logger.warning(f"YandexMusic: не удалось получить ссылку: {e}")
            return None

    def _track_to_meta(self, track) -> TrackMeta:
        artists = ", ".join(a.name for a in (track.artists or []))
        return TrackMeta(
            title=track.title or "Неизвестно",
            artist=artists or "Неизвестно",
            duration_sec=(track.duration_ms or 0) // 1000,
            track_id=track.id,
        )

    # ── Публичный API ─────────────────────────────────────────────────────────

    def find_track(
        self,
        track: str | None = None,
        artist: str | None = None,
    ) -> tuple[str, TrackMeta] | tuple[None, None]:
        """
        Найти трек и вернуть (direct_url, TrackMeta).
        Если трек не найден или ссылку не удалось получить — (None, None).

        Стратегия поиска:
          1. Если задан и трек, и исполнитель — ищем "track artist", берём первый.
          2. Если только исполнитель — ищем топ-треки исполнителя.
          3. Если только трек — ищем по названию.
        """
        client = self._get_client()

        # Формируем поисковый запрос
        if track and artist:
            query = f"{track} {artist}"
        elif artist:
            query = artist
        else:
            query = track or ""

        logger.info(f"YandexMusic: поиск трека «{query}»")

        search = client.search(query, type_="track", page=0)
        if not search or not search.tracks or not search.tracks.results:
            logger.warning(f"YandexMusic: ничего не найдено по запросу «{query}»")
            return None, None

        candidates = search.tracks.results[: config.YANDEX_SEARCH_LIMIT]

        # Если задан исполнитель — попробуем найти наиболее подходящий трек
        if artist:
            artist_lower = artist.lower()
            for candidate in candidates:
                candidate_artists = [a.name.lower() for a in (candidate.artists or [])]
                if any(artist_lower in a or a in artist_lower for a in candidate_artists):
                    found = candidate
                    break
            else:
                found = candidates[0]
        else:
            found = candidates[0]

        meta = self._track_to_meta(found)
        logger.info(f"YandexMusic: найден → {meta.artist} — {meta.title}")

        url = self._get_direct_url(found)
        if not url:
            logger.warning("YandexMusic: прямая ссылка недоступна.")
            return None, meta

        return url, meta

    def my_wave(self) -> list[tuple[str, TrackMeta]]:
        """
        Получить батч треков из "Моей волны" (персональные рекомендации).
        Возвращает список (direct_url, TrackMeta).
        Пустой список если волна недоступна.
        """
        client = self._get_client()
        logger.info("YandexMusic: загружаем Мою волну...")

        try:
            station_tracks = client.rotor_station_tracks("user:onyourwave")
        except Exception as e:
            logger.error(f"YandexMusic: ошибка Моей волны: {e}")
            return []

        results = []
        for seq in station_tracks.sequence[: config.YANDEX_WAVE_BATCH]:
            track = seq.track
            url = self._get_direct_url(track)
            if url:
                results.append((url, self._track_to_meta(track)))

        logger.info(f"YandexMusic: Моя волна — загружено {len(results)} треков.")
        return results

    def next_wave_batch(self, batch_token: str | None = None) -> list[tuple[str, TrackMeta]]:
        """
        Подгрузить следующий батч для Моей волны (для бесконечного воспроизведения).
        batch_token — ответный токен от предыдущего запроса (если нужен).
        """
        # yandex-music-api при повторном вызове rotor_station_tracks
        # автоматически вернёт следующие треки благодаря серверной сессии.
        return self.my_wave()
