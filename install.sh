#!/bin/bash
# =============================================================================
# VRS — скрипт установки на Raspberry Pi
# Запуск: bash install.sh
# =============================================================================

set -e  # остановиться при любой ошибке

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # no color

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# 0. Проверки
# =============================================================================

info "Проверка окружения..."

# Должны быть под обычным пользователем (не root), sudo запросим сами
if [ "$EUID" -eq 0 ]; then
    error "Не запускай от root. Запусти как обычный пользователь: bash install.sh"
fi

# Python 3.9+
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
    error "python3 не найден. Установи: sudo apt install python3"
fi

PY_VERSION=$($PYTHON -c "import sys; print(sys.version_info.major * 10 + sys.version_info.minor)")
if [ "$PY_VERSION" -lt 39 ]; then
    error "Нужен Python 3.9+. Текущая версия: $($PYTHON --version)"
fi
info "Python: $($PYTHON --version)"

# =============================================================================
# 1. Системные зависимости
# =============================================================================

info "Установка системных зависимостей (apt)..."
sudo apt-get update -qq
sudo apt-get install -y \
    portaudio19-dev \
    libportaudio2 \
    libsndfile1 \
    wget \
    unzip \
    ffmpeg \
    mpv \
    python3-pip \
    python3-venv

# =============================================================================
# 2. Виртуальное окружение
# =============================================================================

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    info "Создание виртуального окружения в $VENV_DIR ..."
    $PYTHON -m venv "$VENV_DIR"
else
    info "Виртуальное окружение уже существует, пропускаем создание."
fi

# Активируем venv для всех последующих команд
source "$VENV_DIR/bin/activate"
info "venv активирован: $(which python)"

# =============================================================================
# 3. Python-зависимости
# =============================================================================

info "Установка Python-зависимостей..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt"

# =============================================================================
# 4. Vosk модель русского языка
# =============================================================================

MODEL_DIR="$SCRIPT_DIR/models"
MODEL_NAME="vosk-model-ru-0.42"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"

mkdir -p "$MODEL_DIR"

if [ -d "$MODEL_PATH" ]; then
    info "Vosk-модель уже скачана: $MODEL_PATH"
else
    info "Скачивание Vosk-модели (~1.8 GB), это займёт время..."
    wget -q --show-progress -O "$MODEL_DIR/${MODEL_NAME}.zip" "$MODEL_URL"
    info "Распаковка модели..."
    unzip -q "$MODEL_DIR/${MODEL_NAME}.zip" -d "$MODEL_DIR"
    rm "$MODEL_DIR/${MODEL_NAME}.zip"
    info "Vosk-модель готова: $MODEL_PATH"
fi

# =============================================================================
# 5. Проверка USB-микрофона
# =============================================================================

info "Проверка аудиоустройств..."
python - <<'EOF'
import sounddevice as sd
devices = sd.query_devices()
mics = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
if not mics:
    print("\033[1;33m[WARN]\033[0m Микрофоны не найдены! Подключи USB-микрофон.")
else:
    print("Найдены микрофоны:")
    for i, d in mics:
        print(f"  [{i}] {d['name']}")
EOF

# =============================================================================
# 6. Конфигурация — напомнить про ключи
# =============================================================================

echo ""
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  Осталось сделать вручную:${NC}"
echo ""
echo -e "  1. Получи бесплатный Groq API ключ:"
echo -e "     https://console.groq.com → API Keys"
echo ""
echo -e "  2. Вставь ключ в config.py:"
echo -e "     ${GREEN}GROQ_API_KEY = \"gsk_...\"${NC}"
echo ""
echo -e "  3. Если USB-микрофон не определяется автоматически,"
echo -e "     укажи его индекс (из списка выше) в config.py:"
echo -e "     ${GREEN}MIC_DEVICE_INDEX = 1${NC}  # пример"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# =============================================================================
# 7. Тестовый запуск
# =============================================================================

read -r -p "Запустить test_stt.py прямо сейчас? [y/N] " answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
    info "Запускаем тест..."
    python "$SCRIPT_DIR/test_stt.py"
else
    echo ""
    info "Установка завершена."
    echo ""
    echo "Для запуска теста:"
    echo "  source .venv/bin/activate"
    echo "  python test_stt.py"
fi
