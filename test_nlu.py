"""
Тест части 3: NLU-парсер команд.

Запуск:
    python test_nlu.py

Прогоняет набор тестовых фраз через парсер и показывает результат.
Не требует микрофона или интернета (regex-уровень работает офлайн).
"""

from nlu.parser import CommandParser

CASES = [
    # (команда, ожидаемый action)
    ("включи кукушку группы кино",              "play_track"),
    ("поставь песню highway to hell от ac dc",  "play_track"),
    ("включи группу ария",                      "play_artist"),
    ("сыграй исполнителя моргенштерн",          "play_artist"),
    ("включи мою волну",                        "my_wave"),
    ("поставь мою волну пожалуйста",            "my_wave"),
    ("включи персональное радио",               "my_wave"),
    ("включи queen — bohemian rhapsody",        "play_track"),
    ("поставь песню нежность",                  "play_track"),
    ("включи чайф",                             "play_track"),   # неоднозначно — regex скорее всего play_track
    ("привет как дела",                         "unknown"),      # не музыкальная команда → LLM
]

def main() -> None:
    parser = CommandParser()

    print(f"{'Команда':<45} {'Ожидание':<14} {'Результат':<14} {'source':<6}  Детали")
    print("─" * 110)

    passed = 0
    for text, expected in CASES:
        intent = parser.parse(text)
        ok = "OK" if intent.action == expected else "FAIL"
        if intent.action == expected:
            passed += 1

        details = []
        if intent.track:
            details.append(f"track={intent.track!r}")
        if intent.artist:
            details.append(f"artist={intent.artist!r}")

        print(
            f"{text:<45} {expected:<14} {intent.action:<14} {intent.source:<6}  "
            f"{', '.join(details) or '—'}  [{ok}]"
        )

    print("─" * 110)
    print(f"Итого: {passed}/{len(CASES)} тестов прошли\n")

    # Интерактивный режим
    print("Введи свою команду (Enter для выхода):")
    while True:
        try:
            text = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        intent = parser.parse(text)
        print(f"   {intent}\n")


if __name__ == "__main__":
    main()
