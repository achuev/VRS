# VRS — Voice Radio Station

Голосовая колонка на базе Raspberry Pi 3 + USB-микрофон + любые проводные колонки.
Аналог Яндекс Станции: скажи фразу-активатор — и она найдёт и включит музыку из Яндекс Музыки.

---

## Содержание

- [Как это работает](#как-это-работает)
- [Структура проекта](#структура-проекта)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [Модули](#модули)
- [Тесты по частям](#тесты-по-частям)
- [Голосовые команды](#голосовые-команды)
- [Автозапуск](#автозапуск)
- [Зависимости](#зависимости)

---

## Как это работает

```
[USB Микрофон]
      │
      ▼
[Wake Word Detection]   ← постоянно слушает фоновым потоком
      │  "привет, станция"
      ▼
[Запись команды + VAD]  ← пишет до тишины (~900ms)
      │
      ▼
[Speech-to-Text]        ← Groq Whisper (облако) или Vosk (офлайн)
      │  "включи кукушку группы кино"
      ▼
[NLU / Парсер]          ← regex → если не понял → Groq LLM
      │  {action: play_track, track: "Кукушка", artist: "Кино"}
      ▼
[Yandex Music API]      ← поиск трека, получение прямой ссылки
      │
      ▼
[mpv плеер]             ← воспроизведение на колонках
```

---

## Структура проекта

```
vrs/
│
├── main.py                 # Точка входа — главный цикл приложения
├── config.py               # Все настройки в одном месте
├── requirements.txt        # Python-зависимости
├── install.sh              # Автоматическая установка на Raspberry Pi
│
├── audio/
│   └── recorder.py         # Захват звука с USB-микрофона + VAD
│
├── wake_word/
│   └── detector.py         # Детектор фразы-активатора (Vosk grammar mode)
│
├── stt/
│   └── recognizer.py       # Speech-to-Text: Groq Whisper + Vosk fallback
│
├── nlu/
│   ├── intent.py           # Датакласс Intent (результат разбора команды)
│   ├── parser.py           # Двухуровневый парсер: regex + Groq LLM
│   └── prompts.py          # Системный промпт для LLM
│
├── music/
│   ├── client.py           # Клиент Яндекс Музыки: поиск, волна
│   └── player.py           # Плеер на базе mpv с IPC-управлением
│
├── models/                 # Vosk-модель русского языка (скачивается install.sh)
│   └── vosk-model-ru-0.42/
│
├── test_stt.py             # Тест микрофона и STT
├── test_wake_word.py       # Тест фразы-активатора
├── test_nlu.py             # Тест разбора команд
└── test_music.py           # Тест Яндекс Музыки + плеера
```

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/achuev/VRS.git
cd VRS
```

### 2. Запустить установку

```bash
bash install.sh
```

Скрипт сам:
- Установит системные зависимости (`portaudio`, `ffmpeg`, `mpv` и др.)
- Создаст виртуальное окружение `.venv`
- Установит Python-зависимости
- Скачает Vosk-модель русского языка (~1.8 ГБ)
- Покажет список найденных микрофонов
- Предложит настроить автозапуск через systemd

### 3. Получить API-ключи и вписать в `config.py`

**Groq API** (бесплатно, для STT и LLM):
1. Зарегистрируйся на [console.groq.com](https://console.groq.com)
2. Создай API Key
3. Вставь в `config.py`: `GROQ_API_KEY = "gsk_..."`

**Яндекс Музыка** (токен аккаунта):
```bash
source .venv/bin/activate
python -c "
from yandex_music import Client
c = Client.from_credentials('your@yandex.ru', 'your_password')
print('Токен:', c.token)
"
```
Вставь токен в `config.py`: `YANDEX_MUSIC_TOKEN = "..."`

### 4. Запустить

```bash
source .venv/bin/activate
python main.py
```

---

## Конфигурация

Все параметры находятся в `config.py`. Менять нужно только этот файл.

### Микрофон

```python
# None = системный по умолчанию
# Число = индекс устройства (узнать: python -c "import sounddevice as sd; print(sd.query_devices())")
MIC_DEVICE_INDEX = None
```

### VAD (определение конца фразы)

```python
VAD_AGGRESSIVENESS = 2    # 0–3: чем выше, тем агрессивнее фильтрация шума
VAD_SILENCE_FRAMES = 30   # 30 фреймов × 30ms = 900ms тишины → конец записи
MAX_RECORD_SECONDS = 10   # максимальная длина одной команды
```

### Speech-to-Text

```python
STT_MODE = "auto"   # "groq" | "vosk" | "auto" (groq с fallback на vosk)

GROQ_API_KEY = "gsk_..."
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

VOSK_MODEL_PATH = "models/vosk-model-ru-0.42"
```

### Wake Word

```python
# Все варианты фразы-активатора (нижний регистр)
WAKE_WORDS = ["привет станция", "привет, станция", "станция"]

WAKE_PAUSE_SEC = 0.3   # пауза после активации перед записью команды
```

### Яндекс Музыка и плеер

```python
YANDEX_MUSIC_TOKEN = "..."
YANDEX_SEARCH_LIMIT = 5    # кол-во результатов поиска
YANDEX_WAVE_BATCH = 5      # треков за раз в режиме "Моя волна"

MPV_BINARY = "mpv"
MPV_IPC_SOCKET = "/tmp/vrs-mpv.sock"
```

---

## Модули

### `audio/recorder.py` — Запись голоса

Захватывает аудио с микрофона через `sounddevice`. Использует `webrtcvad` для автоматического определения конца фразы по тишине.

Алгоритм:
1. Читает поток чанками по 30ms
2. Хранит преамбулу в кольцевом буфере (10 чанков = 300ms) — чтобы не обрезать начало слова
3. Как только >60% буфера содержат речь — начинает запись
4. Как только 30 подряд тихих чанков — останавливается

```python
from audio.recorder import VoiceRecorder

recorder = VoiceRecorder()
wav_bytes = recorder.record_to_wav_bytes()   # возвращает WAV в памяти
```

---

### `wake_word/detector.py` — Фраза-активатор

Использует Vosk в режиме **ограниченной грамматики**: вместо полного словаря русского языка передаёт только список фраз-активаторов. В таком режиме нагрузка на CPU минимальна (~5–10% на Pi 3).

Работает в фоновом потоке, вызывает колбэк при срабатывании.

```python
from wake_word.detector import WakeWordDetector

def on_activation():
    print("Активирован!")

with WakeWordDetector(on_detected=on_activation):
    time.sleep(60)   # слушает 60 секунд
```

Чтобы поменять фразу-активатор — просто измени `WAKE_WORDS` в `config.py`.

---

### `stt/recognizer.py` — Распознавание речи

Поддерживает два движка, переключаемых через `STT_MODE`:

| Режим | Движок | Скорость | Требования |
|---|---|---|---|
| `groq` | Groq Whisper Large v3 Turbo | ~1–2 сек | интернет + ключ |
| `vosk` | Vosk `vosk-model-ru-0.42` | ~3–5 сек на Pi 3 | только модель на диске |
| `auto` | groq → vosk при ошибке | зависит от сети | оба |

```python
from stt.recognizer import SpeechRecognizer

recognizer = SpeechRecognizer()
text = recognizer.transcribe(wav_bytes)   # → "включи кукушку группы кино"
```

---

### `nlu/parser.py` — Разбор команды

Двухуровневый парсер:

**Уровень 1 — Regex** (мгновенно, офлайн):
Покрывает стандартные формулировки через регулярные выражения.

**Уровень 2 — Groq LLM** (если regex не справился):
Отправляет текст в `llama-3.3-70b-versatile` с системным промптом, получает структурированный JSON.

```python
from nlu.parser import CommandParser

parser = CommandParser()
intent = parser.parse("включи кукушку группы кино")
# Intent(action='play_track', track='Кукушку', artist='Кино', source='regex')

print(intent.action)   # "play_track"
print(intent.track)    # "Кукушку"
print(intent.artist)   # "Кино"
print(intent.source)   # "regex" или "llm"
```

Возможные значения `intent.action`:

| Значение | Смысл |
|---|---|
| `play_track` | Включить конкретный трек |
| `play_artist` | Включить музыку исполнителя |
| `my_wave` | Режим "Моя волна" |
| `unknown` | Команда не распознана |

---

### `music/client.py` — Яндекс Музыка

Обёртка над неофициальным Python API Яндекс Музыки.

```python
from music.client import YandexMusicClient

client = YandexMusicClient()

# Найти трек
url, meta = client.find_track(track="Кукушка", artist="Кино")
# meta.title, meta.artist, meta.duration_sec

# Только по исполнителю
url, meta = client.find_track(artist="Ария")

# Моя волна — список треков
tracks = client.my_wave()   # [(url, meta), ...]
```

---

### `music/player.py` — Плеер

Запускает `mpv` как дочерний процесс, управляет им через Unix IPC сокет.

```python
from music.player import MpvPlayer

player = MpvPlayer()
player.play(url, meta)    # воспроизвести
player.pause()            # пауза / продолжить
player.stop()             # остановить
player.is_playing()       # → True/False
player.is_finished()      # → True если трек закончился
```

---

## Тесты по частям

Каждый модуль можно проверить отдельно, не запуская всё приложение целиком.

### `python test_stt.py`
Проверяет микрофон и распознавание речи. Показывает список устройств, записывает каждую фразу и выводит распознанный текст. Работает в цикле до Ctrl+C.

### `python test_wake_word.py`
Проверяет фразу-активатор вместе с записью и STT. Скажи `"привет станция"` — должно выводиться `"[!] Активация!"` и начаться запись команды.

### `python test_nlu.py`
Прогоняет набор тестовых фраз через парсер и показывает таблицу результатов. Не требует микрофона и интернета (regex-уровень работает офлайн). После тестов — интерактивный режим: вводи команды с клавиатуры.

### `python test_music.py`
Интерактивное меню: поиск трека по названию/исполнителю или запуск "Моей волны". Требует `YANDEX_MUSIC_TOKEN` и установленный `mpv`.

---

## Голосовые команды

### Конкретный трек

```
"включи кукушку группы кино"
"поставь песню highway to hell от ac dc"
"сыграй кино — кукушка"
"включи нирвана — smells like teen spirit"
```

### Исполнитель

```
"включи группу ария"
"поставь исполнителя моргенштерн"
"включи металлику"
```

### Моя волна

```
"включи мою волну"
"поставь мою волну"
"включи персональное радио"
```

---

## Автозапуск

`install.sh` предлагает настроить автозапуск через systemd. Если согласился — VRS стартует автоматически при каждой загрузке Pi.

```bash
# Управление сервисом
sudo systemctl start   vrs      # запустить
sudo systemctl stop    vrs      # остановить
sudo systemctl restart vrs      # перезапустить
sudo systemctl status  vrs      # статус

# Логи в реальном времени
journalctl -u vrs -f
```

Файл сервиса: `/etc/systemd/system/vrs.service`

---

## Зависимости

### Системные (apt)

| Пакет | Назначение |
|---|---|
| `portaudio19-dev`, `libportaudio2` | Аудиоввод для sounddevice |
| `mpv` | Аудиоплеер |
| `ffmpeg` | Аудиокодеки |
| `python3-venv` | Виртуальное окружение |

### Python (pip)

| Пакет | Назначение |
|---|---|
| `sounddevice` | Захват с микрофона |
| `webrtcvad` | Voice Activity Detection |
| `vosk` | Офлайн STT (русский) |
| `groq` | Groq Whisper API + LLM |
| `yandex-music` | Яндекс Музыка API |
| `python-dotenv` | Переменные окружения |

### Внешние сервисы

| Сервис | Для чего | Стоимость |
|---|---|---|
| [Groq](https://console.groq.com) | STT (Whisper) + NLU (Llama) | Бесплатно (лимит: 14 400 мин/мес для Whisper, 14 400 запр/день для LLM) |
| Яндекс Музыка | Стриминг музыки | Требуется подписка Яндекс Музыки |
