"""
Структура результата разбора голосовой команды.
"""

from dataclasses import dataclass, field


@dataclass
class Intent:
    """
    Результат NLU-разбора.

    action:
        "play_track"   — включить конкретный трек (track и/или artist заполнены)
        "play_artist"  — включить случайное от исполнителя (только artist)
        "my_wave"      — режим "Моя волна"
        "unknown"      — команда не распознана

    track:   название трека или None
    artist:  исполнитель / группа или None
    raw:     исходный текст команды
    source:  "regex" или "llm" — какой уровень парсера сработал
    """

    action: str
    raw: str
    track: str | None = None
    artist: str | None = None
    source: str = "regex"

    def is_valid(self) -> bool:
        """Команда пригодна для запроса в Яндекс Музыку."""
        if self.action == "my_wave":
            return True
        if self.action in ("play_track", "play_artist"):
            return bool(self.track or self.artist)
        return False

    def __str__(self) -> str:
        parts = [f"action={self.action!r}"]
        if self.track:
            parts.append(f"track={self.track!r}")
        if self.artist:
            parts.append(f"artist={self.artist!r}")
        parts.append(f"source={self.source!r}")
        return f"Intent({', '.join(parts)})"
