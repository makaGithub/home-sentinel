# mqtt_client.py
"""
MQTT клиент для интеграции с Home Assistant.

Возможности:
- MQTT Discovery: автоматическая регистрация устройства и сенсоров в HA
- device_tracker по списку PRESENCE_TRACKING_PERSONS, разрегистрация по PRESENCE_TRACKING_PERSONS_REMOVE
- Отправка событий: face_recognized, sound_detected, person_arrived, person_left
"""

import json
import re
import time
import threading
from datetime import datetime

import config
from utils import log

_client = None
_connected = False
_last_events: dict[str, float] = {}
_registered_trackers: set[str] = set()
_lock = threading.Lock()

DEVICE_VERSION = "1.0.0"
DEVICE_MANUFACTURER = "Home Sentinel"
DEVICE_MODEL = "AI Vision System"
DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = config.MQTT_DEVICE_ID
DEVICE_NAME = config.MQTT_DEVICE_NAME


def _get_device_info() -> dict:
    return {
        "identifiers": [DEVICE_ID],
        "name": DEVICE_NAME,
        "manufacturer": DEVICE_MANUFACTURER,
        "model": DEVICE_MODEL,
        "sw_version": DEVICE_VERSION,
    }


def _publish_discovery_config(component: str, object_id: str, config_payload: dict):
    global _client
    if not _client:
        return
    topic = f"{DISCOVERY_PREFIX}/{component}/{DEVICE_ID}/{object_id}/config"
    _client.publish(topic, json.dumps(config_payload, ensure_ascii=False), qos=1, retain=True)


# Кириллица → латиница (транслит)
_CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh',
    'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _transliterate(text: str) -> str:
    result = []
    for c in text.lower():
        result.append(_CYRILLIC_TO_LATIN.get(c, c))
    return ''.join(result)


def _sanitize_name(name: str) -> str:
    transliterated = _transliterate(name)
    sanitized = re.sub(r'[^a-z0-9]+', '_', transliterated)
    return sanitized.strip('_').lower() or 'person'


def _unregister_device_tracker(safe_name: str):
    global _client
    if not _client:
        return
    topic = f"{DISCOVERY_PREFIX}/device_tracker/{DEVICE_ID}/tracker_{safe_name}/config"
    _client.publish(topic, "", qos=1, retain=True)


def _ensure_device_tracker_registered(name: str):
    global _client, _connected, _registered_trackers
    if not _client or not _connected:
        return
    safe_name = _sanitize_name(name)
    if safe_name in _registered_trackers:
        return
    device = _get_device_info()
    tracker_id = f"tracker_{safe_name}"
    state_topic = f"{DEVICE_ID}/device_tracker/{safe_name}/state"
    _publish_discovery_config("device_tracker", tracker_id, {
        "name": f"{name}",
        "unique_id": f"{DEVICE_ID}_{tracker_id}",
        "state_topic": state_topic,
        "payload_home": "home",
        "payload_not_home": "not_home",
        "source_type": "router",
        "icon": "mdi:account",
        "device": device,
    })
    _registered_trackers.add(safe_name)
    if config.DEBUG:
        log(f"🏠 device_tracker registered: {name} → state_topic={state_topic}")


def _update_device_tracker(name: str, is_home: bool):
    global _client, _connected
    if not _client or not _connected:
        return
    _ensure_device_tracker_registered(name)
    safe_name = _sanitize_name(name)
    topic = f"{DEVICE_ID}/device_tracker/{safe_name}/state"
    state = "home" if is_home else "not_home"
    _client.publish(topic, state, qos=1, retain=True)
    if config.DEBUG:
        log(f"🏠 device_tracker: {topic} → {state}")


def publish_discovery():
    global _client, _connected
    if not _client or not _connected:
        return

    device = _get_device_info()
    base_topic = DEVICE_ID

    # ===== Разрегистрация device_tracker (PRESENCE_TRACKING_PERSONS_REMOVE) =====
    if config.PRESENCE_TRACKING_PERSONS_REMOVE:
        for name in config.PRESENCE_TRACKING_PERSONS_REMOVE:
            safe_name = _sanitize_name(name)
            _unregister_device_tracker(safe_name)
            _registered_trackers.discard(safe_name)
        log(f"📡 MQTT: разрегистрировано device_tracker: {', '.join(_sanitize_name(n) for n in config.PRESENCE_TRACKING_PERSONS_REMOVE)}")

    # ===== СЕНСОРЫ =====
    _publish_discovery_config("sensor", "last_face", {
        "name": "Последнее лицо",
        "unique_id": f"{DEVICE_ID}_last_face",
        "state_topic": f"{base_topic}/sensor/last_face",
        "value_template": "{{ value_json.name }}",
        "json_attributes_topic": f"{base_topic}/sensor/last_face",
        "icon": "mdi:face-recognition",
        "device": device,
    })
    _publish_discovery_config("sensor", "last_sound", {
        "name": "Последний звук",
        "unique_id": f"{DEVICE_ID}_last_sound",
        "state_topic": f"{base_topic}/sensor/last_sound",
        "value_template": "{{ value_json.sound }}",
        "json_attributes_topic": f"{base_topic}/sensor/last_sound",
        "icon": "mdi:ear-hearing",
        "device": device,
    })
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
    _publish_discovery_config("binary_sensor", "person_detected", {
        "name": "Человек в кадре",
        "unique_id": f"{DEVICE_ID}_person_detected",
        "state_topic": f"{base_topic}/binary_sensor/person",
        "payload_on": "ON",
        "payload_off": "OFF",
        "device_class": "occupancy",
        "device": device,
    })

    # ===== ИЗОБРАЖЕНИЯ =====
    if config.SCREENSHOTS_WEB_URL:
        _publish_discovery_config("image", "latest", {
            "name": "Последний кадр",
            "unique_id": f"{DEVICE_ID}_image_latest",
            "url_topic": f"{base_topic}/image/latest/url",
            "device": device,
        })
        _publish_discovery_config("image", "arrived", {
            "name": "Последний приход",
            "unique_id": f"{DEVICE_ID}_image_arrived",
            "url_topic": f"{base_topic}/image/arrived/url",
            "device": device,
        })
        _publish_discovery_config("image", "left", {
            "name": "Последний уход",
            "unique_id": f"{DEVICE_ID}_image_left",
            "url_topic": f"{base_topic}/image/left/url",
            "device": device,
        })

    # ===== DEVICE TRIGGERS =====
    for trigger_type in ("face_recognized", "sound_detected", "person_arrived", "person_left"):
        _publish_discovery_config("device_automation", trigger_type, {
            "automation_type": "trigger",
            "type": trigger_type,
            "subtype": trigger_type,
            "topic": f"{base_topic}/trigger/{trigger_type}",
            "device": device,
        })

    # ===== DEVICE TRACKERS (PRESENCE_TRACKING_PERSONS) =====
    if config.PRESENCE_TRACKING_ENABLED and config.PRESENCE_TRACKING_PERSONS:
        for person_name in config.PRESENCE_TRACKING_PERSONS:
            _ensure_device_tracker_registered(person_name)
        log(f"📡 MQTT: зарегистрировано device_tracker для {len(config.PRESENCE_TRACKING_PERSONS)} человек")

    _client.publish(f"{base_topic}/status", "online", qos=1, retain=True)
    log("📡 MQTT Discovery: устройство зарегистрировано в Home Assistant")


def _update_sensor(sensor_id: str, payload: dict):
    global _client
    if not _client or not _connected:
        return
    _client.publish(f"{DEVICE_ID}/sensor/{sensor_id}", json.dumps(payload, ensure_ascii=False), qos=1, retain=True)


def _update_binary_sensor(sensor_id: str, state: bool):
    global _client
    if not _client or not _connected:
        return
    _client.publish(f"{DEVICE_ID}/binary_sensor/{sensor_id}", "ON" if state else "OFF", qos=1, retain=True)


def _update_image_url(image_id: str, screenshot_url: str):
    global _client
    if not _client or not _connected or not screenshot_url:
        return
    url_with_cache = f"{screenshot_url}?t={int(time.time())}"
    _client.publish(f"{DEVICE_ID}/image/{image_id}/url", url_with_cache, qos=1, retain=True)


def _fire_trigger(trigger_type: str, payload: dict):
    global _client
    if not _client or not _connected:
        return
    _client.publish(f"{DEVICE_ID}/trigger/{trigger_type}", json.dumps(payload, ensure_ascii=False), qos=1)


def _should_send(event_key: str) -> bool:
    now = time.time()
    with _lock:
        if now - _last_events.get(event_key, 0) < config.MQTT_EVENT_COOLDOWN:
            return False
        _last_events[event_key] = now
        return True


def init_mqtt():
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
                publish_discovery()
                log("✅ Интеграция с Home Assistant активна")
            else:
                _connected = False
                log(f"❌ MQTT ошибка подключения: код {rc}")

        def on_disconnect(client, userdata, rc, properties=None):
            global _connected
            _connected = False
            if rc != 0:
                log(f"⚠️ MQTT отключен неожиданно: код {rc}")

        _client = mqtt.Client(client_id=config.MQTT_CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        _client.on_connect = on_connect
        _client.on_disconnect = on_disconnect
        _client.will_set(f"{DEVICE_ID}/status", "offline", qos=1, retain=True)
        if config.MQTT_USERNAME:
            _client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
        log(f"🏠 Подключение к Home Assistant (MQTT {config.MQTT_BROKER}:{config.MQTT_PORT})...")
        _client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
        _client.loop_start()
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


def send_face_recognized(name: str, confidence: float = 0.0, frame: int = 0, screenshot_url: str = None):
    global _client, _connected
    if not _client or not _connected:
        return
    if not _should_send(f"face:{name}"):
        return
    timestamp = datetime.now().isoformat()
    _update_sensor("last_face", {"name": name, "confidence": round(confidence, 3), "frame": frame, "timestamp": timestamp})
    _fire_trigger("face_recognized", {"name": name, "confidence": round(confidence, 3), "frame": frame})
    _client.publish(f"{config.MQTT_TOPIC}/face_recognized", json.dumps({
        "event_type": "face_recognized", "timestamp": timestamp, "source": "home-sentinel",
        "name": name, "confidence": round(confidence, 3), "frame": frame,
    }, ensure_ascii=False), qos=1)
    if screenshot_url:
        _update_image_url("latest", screenshot_url)
    log(f"📤 MQTT → Home Assistant: лицо {name}")


def send_sound_detected(sound: str, confidence: float = 0.0, frame: int = 0):
    global _client, _connected
    if not _client or not _connected:
        return
    if not _should_send(f"sound:{sound}"):
        return
    timestamp = datetime.now().isoformat()
    _update_sensor("last_sound", {"sound": sound, "confidence": round(confidence, 3), "frame": frame, "timestamp": timestamp})
    _fire_trigger("sound_detected", {"sound": sound, "confidence": round(confidence, 3), "frame": frame})
    _client.publish(f"{config.MQTT_TOPIC}/sound_detected", json.dumps({
        "event_type": "sound_detected", "timestamp": timestamp, "source": "home-sentinel",
        "sound": sound, "confidence": round(confidence, 3), "frame": frame,
    }, ensure_ascii=False), qos=1)
    log(f"📤 MQTT → Home Assistant: звук {sound}")


def send_person_arrived(name: str, screenshot_path: str = None):
    global _client, _connected
    if not _client or not _connected:
        return
    _update_device_tracker(name, is_home=True)
    timestamp = datetime.now().isoformat()
    payload = {"event": "arrived", "name": name, "timestamp": timestamp}
    if screenshot_path:
        payload["screenshot"] = screenshot_path
    _update_sensor("last_presence", payload)
    _fire_trigger("person_arrived", {"name": name, "screenshot": screenshot_path})
    _client.publish(f"{config.MQTT_TOPIC}/person_arrived", json.dumps({
        "event_type": "person_arrived", "timestamp": timestamp, "source": "home-sentinel",
        "name": name, "screenshot": screenshot_path,
    }, ensure_ascii=False), qos=1)
    if screenshot_path:
        _update_image_url("arrived", screenshot_path)
    log(f"📤 MQTT → Home Assistant: {name} пришёл")


def send_person_left(name: str, screenshot_path: str = None):
    global _client, _connected
    if not _client or not _connected:
        return
    _update_device_tracker(name, is_home=False)
    timestamp = datetime.now().isoformat()
    payload = {"event": "left", "name": name, "timestamp": timestamp}
    if screenshot_path:
        payload["screenshot"] = screenshot_path
    _update_sensor("last_presence", payload)
    _fire_trigger("person_left", {"name": name, "screenshot": screenshot_path})
    _client.publish(f"{config.MQTT_TOPIC}/person_left", json.dumps({
        "event_type": "person_left", "timestamp": timestamp, "source": "home-sentinel",
        "name": name, "screenshot": screenshot_path,
    }, ensure_ascii=False), qos=1)
    if screenshot_path:
        _update_image_url("left", screenshot_path)
    log(f"📤 MQTT → Home Assistant: {name} ушёл")


def update_person_detected(detected: bool):
    _update_binary_sensor("person", detected)


def stop_mqtt():
    global _client, _connected
    if _client:
        _client.publish(f"{DEVICE_ID}/status", "offline", qos=1, retain=True)
        time.sleep(0.1)
        _client.loop_stop()
        _client.disconnect()
        _connected = False
        log("🔌 MQTT отключен")
