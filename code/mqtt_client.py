# mqtt_client.py
"""
MQTT клиент для интеграции с Home Assistant.

Возможности:
- MQTT Discovery: автоматическая регистрация устройства и сенсоров в HA
- Отправка событий: face_recognized, sound_detected, person_arrived, person_left
- Обновление состояний сенсоров в реальном времени
"""

import json
import time
import threading
from datetime import datetime

import config
from utils import log

# Глобальный клиент MQTT
_client = None
_connected = False
_last_events: dict[str, float] = {}  # {event_key: timestamp} для cooldown
_lock = threading.Lock()

# Версия для Home Assistant
DEVICE_VERSION = "1.0.0"
DEVICE_MANUFACTURER = "Home Sentinel"
DEVICE_MODEL = "AI Vision System"

# Discovery prefix (стандартный для HA)
DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = config.MQTT_DEVICE_ID
DEVICE_NAME = config.MQTT_DEVICE_NAME


def _get_device_info() -> dict:
    """Возвращает информацию об устройстве для MQTT Discovery."""
    return {
        "identifiers": [DEVICE_ID],
        "name": DEVICE_NAME,
        "manufacturer": DEVICE_MANUFACTURER,
        "model": DEVICE_MODEL,
        "sw_version": DEVICE_VERSION,
    }


def _publish_discovery_config(component: str, object_id: str, config_payload: dict):
    """Публикует конфигурацию для MQTT Discovery."""
    global _client
    if not _client:
        return
    
    topic = f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}/{object_id}/config"
    _client.publish(topic, json.dumps(config_payload, ensure_ascii=False), qos=1, retain=True)


def publish_discovery():
    """
    Публикует конфигурацию MQTT Discovery для Home Assistant.
    Вызывается после успешного подключения к MQTT.
    """
    global _client, _connected
    if not _client or not _connected:
        return
    
    device = _get_device_info()
    base_topic = f"{DEVICE_ID}"
    
    # ===== СЕНСОРЫ =====
    
    # 1. Последнее распознанное лицо
    _publish_discovery_config("sensor", "last_face", {
        "name": "Последнее лицо",
        "unique_id": f"{DEVICE_ID}_last_face",
        "state_topic": f"{base_topic}/sensor/last_face",
        "value_template": "{{ value_json.name }}",
        "json_attributes_topic": f"{base_topic}/sensor/last_face",
        "icon": "mdi:face-recognition",
        "device": device,
    })
    
    # 2. Последний обнаруженный звук
    _publish_discovery_config("sensor", "last_sound", {
        "name": "Последний звук",
        "unique_id": f"{DEVICE_ID}_last_sound",
        "state_topic": f"{base_topic}/sensor/last_sound",
        "value_template": "{{ value_json.sound }}",
        "json_attributes_topic": f"{base_topic}/sensor/last_sound",
        "icon": "mdi:ear-hearing",
        "device": device,
    })
    
    # 3. Последнее событие присутствия
    _publish_discovery_config("sensor", "last_presence", {
        "name": "Последнее событие",
        "unique_id": f"{DEVICE_ID}_last_presence",
        "state_topic": f"{base_topic}/sensor/last_presence",
        "value_template": "{{ value_json.event }}",
        "json_attributes_topic": f"{base_topic}/sensor/last_presence",
        "icon": "mdi:home-account",
        "device": device,
    })
    
    # ===== BINARY SENSORS =====
    
    # 5. Статус подключения
    _publish_discovery_config("binary_sensor", "status", {
        "name": "Статус",
        "unique_id": f"{DEVICE_ID}_status",
        "state_topic": f"{base_topic}/status",
        "payload_on": "online",
        "payload_off": "offline",
        "device_class": "connectivity",
        "device": device,
        "entity_category": "diagnostic",
    })
    
    # 6. Человек в кадре
    _publish_discovery_config("binary_sensor", "person_detected", {
        "name": "Человек в кадре",
        "unique_id": f"{DEVICE_ID}_person_detected",
        "state_topic": f"{base_topic}/binary_sensor/person",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "occupancy",
        "device": device,
    })
    
    # ===== ИЗОБРАЖЕНИЯ (если есть URL скриншотов) =====
    
    if config.SCREENSHOTS_WEB_URL:
        # Последний кадр с распознанным лицом
        _publish_discovery_config("image", "latest", {
            "name": "Последний кадр",
            "unique_id": f"{DEVICE_ID}_image_latest",
            "url_topic": f"{base_topic}/image/latest/url",
            "device": device,
        })
        
        # Скриншот последнего прихода
        _publish_discovery_config("image", "arrived", {
            "name": "Последний приход",
            "unique_id": f"{DEVICE_ID}_image_arrived",
            "url_topic": f"{base_topic}/image/arrived/url",
            "device": device,
        })
        
        # Скриншот последнего ухода
        _publish_discovery_config("image", "left", {
            "name": "Последний уход",
            "unique_id": f"{DEVICE_ID}_image_left",
            "url_topic": f"{base_topic}/image/left/url",
            "device": device,
        })
    
    # ===== DEVICE TRIGGERS (для автоматизаций) =====
    
    triggers = [
        ("face_recognized", "Распознано лицо"),
        ("sound_detected", "Обнаружен звук"),
        ("person_arrived", "Человек пришёл"),
        ("person_left", "Человек ушёл"),
    ]
    
    for trigger_type, trigger_name in triggers:
        _publish_discovery_config("device_automation", trigger_type, {
            "automation_type": "trigger",
            "type": trigger_type,
            "subtype": trigger_type,
            "topic": f"{base_topic}/trigger/{trigger_type}",
            "device": device,
        })
    
    # Публикуем статус online
    _client.publish(f"{base_topic}/status", "online", qos=1, retain=True)
    
    log("📡 MQTT Discovery: устройство зарегистрировано в Home Assistant")


def _update_sensor(sensor_id: str, payload: dict):
    """Обновляет состояние сенсора."""
    global _client
    if not _client or not _connected:
        return
    
    topic = f"{DEVICE_ID}/sensor/{sensor_id}"
    _client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1, retain=True)


def _update_binary_sensor(sensor_id: str, state: bool):
    """Обновляет состояние binary sensor."""
    global _client
    if not _client or not _connected:
        return
    
    topic = f"{DEVICE_ID}/binary_sensor/{sensor_id}"
    _client.publish(topic, "ON" if state else "OFF", qos=1, retain=True)


def _update_image_url(image_id: str, screenshot_url: str):
    """Обновляет URL изображения."""
    global _client
    if not _client or not _connected or not screenshot_url:
        return
    
    # Добавляем timestamp для сброса кеша браузера
    cache_bust = int(time.time())
    url_with_cache = f"{screenshot_url}?t={cache_bust}"
    
    topic = f"{DEVICE_ID}/image/{image_id}/url"
    _client.publish(topic, url_with_cache, qos=1, retain=True)


def _fire_trigger(trigger_type: str, payload: dict):
    """Отправляет device trigger."""
    global _client
    if not _client or not _connected:
        return
    
    topic = f"{DEVICE_ID}/trigger/{trigger_type}"
    _client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)


def init_mqtt():
    """Инициализирует MQTT клиент. Вызывать при старте приложения."""
    global _client, _connected
    
    if not config.MQTT_BROKER:
        log("⚠️ MQTT_BROKER не задан, интеграция с Home Assistant пропущена")
        return False
    
    try:
        import paho.mqtt.client as mqtt
        
        def on_connect(client, userdata, flags, rc, properties=None):
            global _connected
            if rc == 0:
                _connected = True
                # Публикуем Discovery после подключения
                publish_discovery()
                log(f"✅ Интеграция с Home Assistant активна")
            else:
                _connected = False
                log(f"❌ MQTT ошибка подключения: код {rc}")
        
        def on_disconnect(client, userdata, rc, properties=None):
            global _connected
            _connected = False
            if rc != 0:
                log(f"⚠️ MQTT отключен неожиданно: код {rc}")
        
        _client = mqtt.Client(
            client_id=config.MQTT_CLIENT_ID,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        _client.on_connect = on_connect
        _client.on_disconnect = on_disconnect
        
        # Last Will: статус offline при отключении
        _client.will_set(f"{DEVICE_ID}/status", "offline", qos=1, retain=True)
        
        if config.MQTT_USERNAME:
            _client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
        
        log(f"🏠 Подключение к Home Assistant (MQTT {config.MQTT_BROKER}:{config.MQTT_PORT})...")
        _client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        _client.loop_start()
        
        # Ждём подтверждения подключения (макс 3 сек)
        for _ in range(30):
            if _connected:
                break
            time.sleep(0.1)
        
        if not _connected:
            log("⚠️ MQTT: подключение не подтверждено, продолжаю...")
        
        return True
        
    except ImportError:
        log("❌ paho-mqtt не установлен, MQTT отключен")
        return False
    except Exception as e:
        log(f"❌ Ошибка инициализации MQTT: {e}")
        return False


def _should_send(event_key: str) -> bool:
    """Проверяет cooldown для события."""
    now = time.time()
    with _lock:
        last_time = _last_events.get(event_key, 0)
        if now - last_time < config.MQTT_EVENT_COOLDOWN:
            return False
        _last_events[event_key] = now
        return True


def send_face_recognized(name: str, confidence: float = 0.0, frame: int = 0, screenshot_url: str = None):
    """Отправляет событие распознания лица."""
    global _client, _connected
    if not _client or not _connected:
        return
    
    event_key = f"face:{name}"
    if not _should_send(event_key):
        return
    
    timestamp = datetime.now().isoformat()
    
    # Обновляем сенсор
    _update_sensor("last_face", {
        "name": name,
        "confidence": round(confidence, 3),
        "frame": frame,
        "timestamp": timestamp,
    })
    
    # Отправляем trigger
    _fire_trigger("face_recognized", {
        "name": name,
        "confidence": round(confidence, 3),
        "frame": frame,
    })
    
    # Отправляем событие в legacy топик (для совместимости)
    topic = f"{config.MQTT_TOPIC}/face_recognized"
    _client.publish(topic, json.dumps({
        "event_type": "face_recognized",
        "timestamp": timestamp,
        "source": "home-sentinel",
        "name": name,
        "confidence": round(confidence, 3),
        "frame": frame,
    }, ensure_ascii=False), qos=1)
    
    # Обновляем изображение "Последний кадр"
    if screenshot_url:
        _update_image_url("latest", screenshot_url)
    
    log(f"📤 MQTT → Home Assistant: лицо {name}")


def send_sound_detected(sound: str, confidence: float = 0.0, frame: int = 0):
    """Отправляет событие обнаружения звука."""
    global _client, _connected
    if not _client or not _connected:
        return
    
    event_key = f"sound:{sound}"
    if not _should_send(event_key):
        return
    
    timestamp = datetime.now().isoformat()
    
    # Обновляем сенсор
    _update_sensor("last_sound", {
        "sound": sound,
        "confidence": round(confidence, 3),
        "frame": frame,
        "timestamp": timestamp,
    })
    
    # Отправляем trigger
    _fire_trigger("sound_detected", {
        "sound": sound,
        "confidence": round(confidence, 3),
        "frame": frame,
    })
    
    # Legacy топик
    topic = f"{config.MQTT_TOPIC}/sound_detected"
    _client.publish(topic, json.dumps({
        "event_type": "sound_detected",
        "timestamp": timestamp,
        "source": "home-sentinel",
        "sound": sound,
        "confidence": round(confidence, 3),
        "frame": frame,
    }, ensure_ascii=False), qos=1)
    
    log(f"📤 MQTT → Home Assistant: звук {sound}")


def send_person_arrived(name: str, screenshot_path: str = None):
    """Отправляет событие 'человек пришёл домой'."""
    global _client, _connected
    if not _client or not _connected:
        return
    
    timestamp = datetime.now().isoformat()
    
    # Обновляем сенсор присутствия
    payload = {
        "event": "arrived",
        "name": name,
        "timestamp": timestamp,
    }
    if screenshot_path:
        payload["screenshot"] = screenshot_path
    
    _update_sensor("last_presence", payload)
    
    # Отправляем trigger
    _fire_trigger("person_arrived", {"name": name, "screenshot": screenshot_path})
    
    # Legacy топик
    topic = f"{config.MQTT_TOPIC}/person_arrived"
    _client.publish(topic, json.dumps({
        "event_type": "person_arrived",
        "timestamp": timestamp,
        "source": "home-sentinel",
        "name": name,
        "screenshot": screenshot_path,
    }, ensure_ascii=False), qos=1)
    
    # Обновляем изображение "Последний приход"
    if screenshot_path:
        _update_image_url("arrived", screenshot_path)
    
    log(f"📤 MQTT → Home Assistant: {name} пришёл")


def send_person_left(name: str, screenshot_path: str = None):
    """Отправляет событие 'человек ушёл из дома'."""
    global _client, _connected
    if not _client or not _connected:
        return
    
    timestamp = datetime.now().isoformat()
    
    # Обновляем сенсор присутствия
    payload = {
        "event": "left",
        "name": name,
        "timestamp": timestamp,
    }
    if screenshot_path:
        payload["screenshot"] = screenshot_path
    
    _update_sensor("last_presence", payload)
    
    # Отправляем trigger
    _fire_trigger("person_left", {"name": name, "screenshot": screenshot_path})
    
    # Legacy топик
    topic = f"{config.MQTT_TOPIC}/person_left"
    _client.publish(topic, json.dumps({
        "event_type": "person_left",
        "timestamp": timestamp,
        "source": "home-sentinel",
        "name": name,
        "screenshot": screenshot_path,
    }, ensure_ascii=False), qos=1)
    
    # Обновляем изображение "Последний уход"
    if screenshot_path:
        _update_image_url("left", screenshot_path)
    
    log(f"📤 MQTT → Home Assistant: {name} ушёл")


def update_person_detected(detected: bool):
    """Обновляет статус 'человек в кадре'."""
    _update_binary_sensor("person", detected)


def stop_mqtt():
    """Останавливает MQTT клиент."""
    global _client, _connected
    if _client:
        # Публикуем статус offline
        _client.publish(f"{DEVICE_ID}/status", "offline", qos=1, retain=True)
        time.sleep(0.1)
        _client.loop_stop()
        _client.disconnect()
        _connected = False
        log("🔌 MQTT отключен")
