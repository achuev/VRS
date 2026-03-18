"""
Конфигурация проекта VRS (Voice Radio Station).
Скопируй этот файл и заполни свои токены.
"""

# ── Микрофон ──────────────────────────────────────────────────────────────────
# None = системный по умолчанию. Укажи индекс устройства если нужно конкретное.
# Узнать индекс: python -c "import sounddevice as sd; print(sd.query_devices())"
MIC_DEVICE_INDEX = None

# Частота дискретизации. webrtcvad требует 8000, 16000, 32000 или 48000.
SAMPLE_RATE = 16000

# Размер чанка в миллисекундах (10, 20 или 30 — требование webrtcvad)
VAD_FRAME_MS = 30

# Агрессивность VAD: 0 (мягкий) — 3 (агрессивный). На шумном фоне — 2 или 3.
VAD_AGGRESSIVENESS = 2

# Сколько подряд "тихих" фреймов считать концом фразы
VAD_SILENCE_FRAMES = 30   # 30 * 30ms = 900ms тишины → конец записи

# Максимальная длина записи в секундах (защита от зависания)
MAX_RECORD_SECONDS = 10

# ── Vosk (локальный STT) ──────────────────────────────────────────────────────
# Скачать модель: https://alphacephei.com/vosk/models → vosk-model-ru-0.42
# Распаковать рядом с проектом или указать абсолютный путь.
VOSK_MODEL_PATH = "models/vosk-model-ru-0.42"

# ── Groq API (облачный STT + LLM) ─────────────────────────────────────────────
# Зарегистрироваться: https://console.groq.com → API Keys
GROQ_API_KEY = "YOUR_GROQ_API_KEY"

# Модель Whisper на Groq
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

# Модель LLM на Groq (для NLU в части 4)
GROQ_LLM_MODEL = "llama-3.3-70b-versatile"

# Язык распознавания
LANGUAGE = "ru"

# ── Режим STT ─────────────────────────────────────────────────────────────────
# "groq"  — облако (быстро, требует интернет и ключ)
# "vosk"  — локально (медленнее, работает офлайн)
# "auto"  — groq с fallback на vosk при ошибке
STT_MODE = "auto"
