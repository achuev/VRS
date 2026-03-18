"""
Модуль записи голосовых команд с USB-микрофона.

Принцип работы:
  1. Слушаем поток с микрофона чанками по VAD_FRAME_MS миллисекунд.
  2. webrtcvad определяет, есть ли в чанке речь.
  3. Как только появилась речь — начинаем копить буфер.
  4. Когда VAD_SILENCE_FRAMES подряд тихих чанков — считаем фразу законченной.
  5. Возвращаем сырые PCM-байты (16-bit, mono, 16000 Hz) — готово для STT.
"""

import collections
import logging

import numpy as np
import sounddevice as sd
import webrtcvad

import config

logger = logging.getLogger(__name__)


def list_microphones() -> None:
    """Вывести список доступных аудиоустройств (для диагностики)."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"  [{i}] {dev['name']}  (вход: {dev['max_input_channels']} каналов)")


def _frame_generator(stream: sd.RawInputStream, frame_bytes: int):
    """
    Генератор: бесконечно читает из потока и отдаёт чанки ровно frame_bytes байт.
    sounddevice может вернуть меньше байт чем нужно — буферизируем.
    """
    buf = b""
    while True:
        data, _ = stream.read(frame_bytes // 2)   # read принимает кол-во фреймов
        buf += bytes(data)
        while len(buf) >= frame_bytes:
            yield buf[:frame_bytes]
            buf = buf[frame_bytes:]


class VoiceRecorder:
    """
    Записывает одну голосовую команду с VAD.

    Использование:
        recorder = VoiceRecorder()
        pcm_bytes = recorder.record()   # блокирует до конца фразы
    """

    def __init__(self) -> None:
        self.sample_rate = config.SAMPLE_RATE
        self.frame_ms = config.VAD_FRAME_MS
        self.silence_frames = config.VAD_SILENCE_FRAMES
        self.max_seconds = config.MAX_RECORD_SECONDS
        self.device = config.MIC_DEVICE_INDEX

        # Размер одного чанка в байтах: sample_rate * frame_ms/1000 * 2 байта (int16)
        self.frame_bytes = int(self.sample_rate * self.frame_ms / 1000) * 2

        self._vad = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)

    def record(self) -> bytes:
        """
        Записать одну голосовую команду и вернуть PCM-байты.

        Алгоритм с кольцевым буфером:
          - ring_buffer хранит последние N чанков до начала речи (преамбула)
          - triggered=True: речь идёт, копим voiced_frames
          - После triggered: считаем тихие чанки; при превышении порога — конец
        """
        max_frames = int(self.max_seconds * 1000 / self.frame_ms)

        # Преамбула: сохраняем последние 10 чанков до начала речи,
        # чтобы не обрезать начало слова
        ring_buffer: collections.deque = collections.deque(maxlen=10)

        voiced_frames: list[bytes] = []
        triggered = False
        silence_count = 0
        frame_count = 0

        logger.info("Recorder: ожидание речи...")

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
            blocksize=self.frame_bytes // 2,  # frames, не байты
        ) as stream:
            for frame in _frame_generator(stream, self.frame_bytes):
                frame_count += 1

                is_speech = self._vad.is_speech(frame, self.sample_rate)

                if not triggered:
                    ring_buffer.append((frame, is_speech))
                    # Если больше половины преамбулы — речь, начинаем запись
                    num_voiced = sum(1 for _, s in ring_buffer if s)
                    if num_voiced > len(ring_buffer) * 0.6:
                        triggered = True
                        silence_count = 0
                        logger.info("Recorder: речь обнаружена, запись...")
                        # Добавляем преамбулу в буфер (чтобы не потерять начало)
                        for f, _ in ring_buffer:
                            voiced_frames.append(f)
                        ring_buffer.clear()
                else:
                    voiced_frames.append(frame)
                    if not is_speech:
                        silence_count += 1
                        if silence_count >= self.silence_frames:
                            logger.info(
                                "Recorder: тишина — конец фразы. "
                                f"Записано {len(voiced_frames)} чанков."
                            )
                            break
                    else:
                        silence_count = 0

                    if frame_count >= max_frames:
                        logger.warning("Recorder: достигнут лимит записи.")
                        break

        if not voiced_frames:
            logger.warning("Recorder: речь не обнаружена, возвращаем пустые байты.")
            return b""

        return b"".join(voiced_frames)

    def record_to_wav(self, path: str) -> str:
        """
        Записать команду и сохранить в WAV-файл.
        Возвращает путь к файлу. Используется для передачи в Groq API.
        """
        import io
        import wave

        pcm = self.record()
        if not pcm:
            return ""

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)   # int16 = 2 байта
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm)

        logger.info(f"Recorder: WAV сохранён → {path}")
        return path

    def record_to_wav_bytes(self) -> bytes:
        """
        Записать команду и вернуть WAV-байты (без сохранения на диск).
        Используется для потоковой передачи в Groq API.
        """
        import io
        import wave

        pcm = self.record()
        if not pcm:
            return b""

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()
