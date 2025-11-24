#!/usr/bin/env python3
"""
Временный скрипт для генерации симулированных логов home-sentinel
Показывает все основные функции системы: загрузку, синхронизацию, детекцию, распознавание и т.д.
Формат логов соответствует реальному выводу системы.
"""

import time
import random
import sys
from datetime import datetime, timedelta

# Список имен людей из Immich
PEOPLE_NAMES = [
    "Максим Жижин", "Никита Жижин", "Наталья Жижина", "Александр Жижин"
]

# Типы объектов для детекции (только собаки из животных)
OBJECT_TYPES = ["person", "dog", "tv", "bed", "chair", "laptop", "phone"]

# Звуки для аудио анализа
SOUND_TYPES = ["speech", "dog_bark", "door_knock"]

# Фиксированная дата - середина ноября
BASE_DATE = datetime(2025, 11, 16)  # 16 ноября 2025
BASE_TIME = datetime(2025, 11, 16, 18, 30, 0)  # 18:30 вечер
current_time = BASE_TIME

def log(message, time_offset=0):
    """Выводит лог с временной меткой в формате реальной системы"""
    global current_time
    try:
        if time_offset > 0:
            current_time = current_time + timedelta(seconds=time_offset)
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)
        time.sleep(random.uniform(0.02, 0.08))  # Быстрее для компактности
    except (BrokenPipeError, IOError):
        # Игнорируем ошибки при перенаправлении вывода (head, tail и т.д.)
        sys.exit(0)

def simulate_startup():
    """Симуляция загрузки системы - компактная версия"""
    log("🚀 home-sentinel (RTSP video + RTSP audio) стартует", 0)
    log("📊 Инициализация таблиц статистики...", 1)
    log("✅ Таблицы статистики готовы", 1)
    log("🎤 Запуск ffmpeg аудиопотока для rtsp://raspberry-pi:8554/stream...", 1)
    log("🎧 AudioDetector запущен в фоновом потоке", 1)
    log("🔄 Загрузка векторных представлений лиц из Immich...", 2)
    log("📡 Подключение к PostgreSQL: immich_db@192.168.1.10:5432", 1)
    log("✅ Подключено к базе данных Immich", 1)
    log("🤖 Инициализация YOLOv11...", 1)
    log("📦 Загрузка модели: yolo11n.pt", 1)
    log("✅ YOLOv11 модель загружена", 1)
    log("👤 Инициализация InsightFace...", 1)
    log("📦 Загрузка модели: antelopev2", 2)
    log("✅ InsightFace запущен с CUDA, det_size=(1280, 1280)", 2)
    log("📹 Подключение к RTSP потоку: rtsp://raspberry-pi:8554/stream", 1)
    log("✅ RTSP поток подключен (1920x1080 @ 30fps)", 1)
    log("🏠 Подключение к Home Assistant API...", 1)
    log("✅ Home Assistant API подключен", 1)
    log("📨 Подключение к MQTT брокеру...", 1)
    log("✅ MQTT брокер подключен", 1)

def simulate_face_sync():
    """Симуляция синхронизации face embeddings из Immich - компактная"""
    num_faces = random.randint(95, 105)
    log(f"📥 Найдено {num_faces} векторных представлений лиц в Immich", 2)
    log("💾 Загрузка эмбеддингов в память...", 1)
    log(f"   Загружено {num_faces}/{num_faces} эмбеддингов...", 2)
    log("🔍 Построение индекса для быстрого поиска...", 1)
    log(f"✅ Синхронизировано {num_faces} векторных представлений из Immich", 1)
    log("👥 Загружено имён людей: " + ", ".join(PEOPLE_NAMES), 1)

def simulate_object_detection():
    """Симуляция детекции объектов - компактная версия"""
    log("📹 Обработка видеопотока начата", 2)
    detected_objects_history = []
    
    # Показываем 3 ключевых детекции
    for frame_num in range(1, 4):
        detected_objects = []
        num_objects = random.randint(1, 2)
        
        for _ in range(num_objects):
            obj_type = random.choice(OBJECT_TYPES)
            detected_objects.append(obj_type)
        
        unique_objects = list(set(detected_objects))
        
        if unique_objects:
            objects_str = ", ".join(unique_objects)
            log(f"➕ Появились: {objects_str}", random.randint(4, 7))
            current_frame = ', '.join(detected_objects_history[-2:] + unique_objects) if detected_objects_history else objects_str
            log(f"📸 Сейчас в кадре: {current_frame}", 1)
            detected_objects_history.extend(unique_objects)
            detected_objects_history = detected_objects_history[-3:]

def simulate_face_recognition():
    """Симуляция распознавания лиц - компактная версия"""
    recognized_people = []
    
    # Показываем 2 успешных распознавания
    for i in range(1, 3):
        person_name = random.choice(PEOPLE_NAMES)
        similarity = random.uniform(0.87, 0.94)
        face_size = random.randint(105, 130)
        
        log(f"👤 Распознан: {person_name} (сходство: {similarity:.3f}, размер лица: {face_size}px)", random.randint(6, 10))
        recognized_people.append(person_name)
        log(f"📨 Отправка в MQTT: homeassistant/binary_sensor/home-sentinel/{person_name.lower().replace(' ', '_')}", 1)
        log(f"💾 Запись в статистику: {person_name}", 1)

def simulate_audio_detection():
    """Симуляция анализа аудио - компактная версия"""
    # Показываем 1-2 ключевых аудио события
    sound_type = "dog_bark"
    confidence = random.uniform(0.85, 0.93)
    log(f"🐕 Обнаружен лай собаки (уверенность: {confidence:.2f})", random.randint(8, 15))
    log(f"📨 Отправка в MQTT: homeassistant/sensor/home-sentinel/dog_bark", 1)
    log(f"🏠 Автоматизация Home Assistant: 'Уведомление о лае собаки'", 1)
    log(f"💾 Запись в статистику: {sound_type}", 1)

def simulate_statistics():
    """Симуляция записи статистики - компактная"""
    log("📊 Статистика за сегодня:", random.randint(5, 10))
    log("   👥 Распознано людей: 4", 1)
    log("   📹 Обнаружено объектов: 23", 1)
    log("   🔊 Аудио событий: 5", 1)
    log("   ⚡ Среднее время обработки: 32ms на кадр", 1)

def simulate_mqtt_events():
    """Симуляция MQTT событий - уже интегрировано в другие функции"""
    pass  # MQTT события уже показываются в других функциях

def simulate_running():
    """Симуляция работы системы в реальном времени - компактная"""
    log("⚙️ Система работает в штатном режиме", random.randint(4, 8))
    
    # Показываем 1 финальное событие
    person = random.choice(PEOPLE_NAMES)
    log(f"➕ Появились: person, dog", random.randint(6, 10))
    log(f"📸 Сейчас в кадре: person, dog", 1)
    log(f"👤 Распознан: {person} (сходство: {random.uniform(0.89, 0.93):.3f})", random.randint(2, 4))
    log(f"📨 Отправка в MQTT: homeassistant/binary_sensor/home-sentinel/{person.lower().replace(' ', '_')}", 1)

def main():
    """Основная функция - генерирует компактный лог на один экран"""
    global current_time
    current_time = BASE_TIME  # Сброс времени
    
    try:
        # Загрузка системы
        simulate_startup()
        
        # Синхронизация face embeddings
        simulate_face_sync()
        
        # Детекция объектов
        simulate_object_detection()
        
        # Распознавание лиц
        simulate_face_recognition()
        
        # Анализ аудио
        simulate_audio_detection()
        
        # Статистика
        simulate_statistics()
        
        # Работа в реальном времени
        simulate_running()
        
        log("✅ Система работает нормально", random.randint(3, 8))
        log("📊 Все компоненты операционны", 1)
        
    except KeyboardInterrupt:
        log("\n⚠️ Остановка home-sentinel...", 0)
        log("🛑 Остановка видеопотока...", 1)
        log("🔌 Закрытие подключений к БД...", 1)
        log("📨 Отключение от MQTT...", 1)
        log("✅ Завершение работы", 1)
        sys.exit(0)

if __name__ == "__main__":
    main()

