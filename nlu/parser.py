"""
NLU-парсер голосовых команд — двухуровневый.

Уровень 1 — Regex:
  Покрывает ~80% типовых команд мгновенно и без интернета.
  Учитывает падежи, порядок слов, типичные формулировки на русском.

Уровень 2 — Groq LLM (llama-3.3-70b):
  Подключается только если regex ничего не нашёл.
  Возвращает структурированный JSON, понимает любые формулировки.

Использование:
    parser = CommandParser()
    intent = parser.parse("включи кукушку группы кино")
    # Intent(action='play_track', track='Кукушка', artist='Кино', source='regex')
"""

import json
import logging
import re

import config
from nlu.intent import Intent
from nlu.prompts import SYSTEM_PROMPT, make_user_message

logger = logging.getLogger(__name__)


# =============================================================================
# Уровень 1: Regex
# =============================================================================

# Слова-триггеры для команды воспроизведения
_PLAY_VERBS = r"(?:включи|поставь|запусти|сыграй|воспроизведи|хочу послушать|поставь(?:те)?)"

# Маркеры исполнителя
_ARTIST_MARKERS = r"(?:группы|группа|исполнителя|исполнитель|артиста|артист|певца|певец|певицы|певица|от|by)"

# Маркеры трека
_TRACK_MARKERS = r"(?:песню|песня|трек|композицию|композиция|называется|под названием)"

# Захватывающая группа: всё до конца строки или до следующего маркера
_CAPTURE = r"(.+?)(?:\s+(?:" + _ARTIST_MARKERS[4:-1] + r")\s|\s*$)"  # non-greedy до маркера или конца

# ── Паттерны "Моя волна" ───────────────────────────────────────────────────

_MY_WAVE_RE = re.compile(
    r"(?:включи|запусти|поставь|хочу)?\s*"
    r"(?:мою\s+волну|мо[её]\s+волн[ыу]|мою\s+волну|персональн\w+\s+(?:радио|музык\w+)|"
    r"моя\s+волна|рекомендации)",
    re.IGNORECASE,
)

# ── Паттерны с явными маркерами трека И исполнителя ───────────────────────
# "включи песню X группы Y" / "включи X от Y"
_TRACK_AND_ARTIST_RE = re.compile(
    _PLAY_VERBS + r"\s+"
    + r"(?:" + _TRACK_MARKERS + r"\s+)?"    # необязательное "песню"
    + r"(.+?)\s+"                            # трек
    + _ARTIST_MARKERS + r"\s+"
    + r"(.+?)$",                             # исполнитель
    re.IGNORECASE,
)

# "включи Y — X" / "включи Y: X" (исполнитель — трек)
_ARTIST_DASH_TRACK_RE = re.compile(
    _PLAY_VERBS + r"\s+(.+?)\s+[-–—:]\s+(.+?)$",
    re.IGNORECASE,
)

# ── Только исполнитель ─────────────────────────────────────────────────────
# "включи группу Кино" / "включи Моргенштерна"
_ARTIST_ONLY_RE = re.compile(
    _PLAY_VERBS + r"\s+(?:" + _ARTIST_MARKERS + r"\s+)?(.+?)$",
    re.IGNORECASE,
)

# ── Только трек (fallback) ─────────────────────────────────────────────────
# "включи Кукушку"
_TRACK_ONLY_RE = re.compile(
    _PLAY_VERBS + r"\s+" + r"(?:" + _TRACK_MARKERS + r"\s+)?" + r"(.+?)$",
    re.IGNORECASE,
)


def _clean(s: str) -> str:
    """Убрать лишние пробелы и привести к Title Case."""
    return " ".join(s.strip().split()).strip("\"'«»")


def _regex_parse(text: str) -> Intent | None:
    """
    Попытаться распознать команду через регулярные выражения.
    Возвращает Intent или None если не удалось.
    """
    t = text.strip()

    # 1. Моя волна
    if _MY_WAVE_RE.search(t):
        return Intent(action="my_wave", raw=text, source="regex")

    # 2. Трек + исполнитель ("включи Кукушку группы Кино")
    m = _TRACK_AND_ARTIST_RE.search(t)
    if m:
        return Intent(
            action="play_track",
            raw=text,
            track=_clean(m.group(1)),
            artist=_clean(m.group(2)),
            source="regex",
        )

    # 3. "Исполнитель — Трек" (с тире)
    m = _ARTIST_DASH_TRACK_RE.search(t)
    if m:
        return Intent(
            action="play_track",
            raw=text,
            artist=_clean(m.group(1)),
            track=_clean(m.group(2)),
            source="regex",
        )

    # 4. Явный маркер исполнителя без трека ("включи группу Кино")
    artist_marker_re = re.compile(
        _PLAY_VERBS + r"\s+" + _ARTIST_MARKERS + r"\s+(.+?)$",
        re.IGNORECASE,
    )
    m = artist_marker_re.search(t)
    if m:
        return Intent(
            action="play_artist",
            raw=text,
            artist=_clean(m.group(1)),
            source="regex",
        )

    # 5. Явный маркер трека без исполнителя ("включи песню Кукушка")
    track_marker_re = re.compile(
        _PLAY_VERBS + r"\s+" + _TRACK_MARKERS + r"\s+(.+?)$",
        re.IGNORECASE,
    )
    m = track_marker_re.search(t)
    if m:
        return Intent(
            action="play_track",
            raw=text,
            track=_clean(m.group(1)),
            source="regex",
        )

    # 6. Просто "включи [что-то]" — считаем треком (неоднозначно, но LLM уточнит)
    m = _TRACK_ONLY_RE.search(t)
    if m:
        return Intent(
            action="play_track",
            raw=text,
            track=_clean(m.group(1)),
            source="regex",
        )

    return None


# =============================================================================
# Уровень 2: Groq LLM
# =============================================================================

def _llm_parse(text: str) -> Intent:
    """
    Разобрать команду через Groq LLM. Возвращает Intent (action может быть "unknown").
    """
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Установи groq: pip install groq")

    client = Groq(api_key=config.GROQ_API_KEY)

    response = client.chat.completions.create(
        model=config.GROQ_LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": make_user_message(text)},
        ],
        temperature=0,          # детерминированный вывод
        max_tokens=100,
        response_format={"type": "json_object"},
    )

    raw_json = response.choices[0].message.content
    logger.debug(f"LLM raw response: {raw_json}")

    data = json.loads(raw_json)
    return Intent(
        action=data.get("action", "unknown"),
        raw=text,
        track=data.get("track") or None,
        artist=data.get("artist") or None,
        source="llm",
    )


# =============================================================================
# Публичный интерфейс
# =============================================================================

class CommandParser:
    """
    Двухуровневый NLU-парсер голосовых команд.

    Пример:
        parser = CommandParser()
        intent = parser.parse("включи кукушку группы кино")
        print(intent)
        # Intent(action='play_track', track='Кукушку', artist='Кино', source='regex')
    """

    def parse(self, text: str) -> Intent:
        """Разобрать голосовую команду и вернуть Intent."""
        if not text or not text.strip():
            return Intent(action="unknown", raw=text)

        logger.info(f"NLU: разбираем «{text}»")

        # Уровень 1: regex (быстро, офлайн)
        intent = _regex_parse(text)
        if intent and intent.is_valid():
            logger.info(f"NLU regex: {intent}")
            return intent

        # Уровень 2: LLM (если regex не справился или нет GROQ_API_KEY)
        if not config.GROQ_API_KEY or config.GROQ_API_KEY == "YOUR_GROQ_API_KEY":
            logger.warning("NLU: GROQ_API_KEY не задан, LLM-уровень пропущен.")
            return intent or Intent(action="unknown", raw=text)

        try:
            intent = _llm_parse(text)
            logger.info(f"NLU LLM: {intent}")
            return intent
        except Exception as e:
            logger.error(f"NLU LLM ошибка: {e}")
            return Intent(action="unknown", raw=text)
