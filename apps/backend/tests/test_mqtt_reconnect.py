"""Restart only the disposable test broker and verify actual client recovery."""
from pathlib import Path
from threading import Event
from queue import Queue
from datetime import datetime,UTC
import subprocess
import json
import paho.mqtt.client as mqtt
from publishers.mqtt_publisher import MqttPublisher
from src.core.config import Config

def test_publisher_recovers_after_disposable_broker_restart():
    root=Path(__file__).resolve().parents[3]
    # This integration case must never stop the shared development broker.
    assert Config.MQTT_PORT==18884, 'Use scripts/test_backend.sh and its isolated test broker'
    inbox=Queue();subscribed=Event();connected=Event()
    subscriber=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    subscriber.reconnect_delay_set(min_delay=1,max_delay=2)
    subscriber.on_connect=lambda client,*args: client.subscribe('solar/reconnect-home/#',qos=1)
    subscriber.on_subscribe=lambda *args: subscribed.set()
    subscriber.on_message=lambda client,userdata,message: inbox.put(json.loads(message.payload))
    subscriber.connect(Config.MQTT_HOST,Config.MQTT_PORT);subscriber.loop_start()
    publisher=MqttPublisher(Config.MQTT_HOST,Config.MQTT_PORT,client_id='restart-test-publisher')
    publisher._client.on_connect=lambda *args: connected.set()
    def payload(sequence):return dict(schema_version='1.0',home_id='reconnect-home',device_id='reconnect-meter',sensor_type='smart_meter',sequence_number=sequence,measured_at=datetime.now(UTC).isoformat(),data={'voltage_v':120})
    topic='solar/reconnect-home/reconnect-meter/telemetry'
    try:
        assert subscribed.wait(10)
        publisher.publish(topic,payload(1));assert inbox.get(timeout=10)['sequence_number']==1
        connected.clear();subscribed.clear()
        subprocess.run(['docker','compose','-f',str(root/'infrastructure/docker/compose.tests.yml'),'restart','mqtt'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30)
        assert connected.wait(15) and subscribed.wait(15)
        publisher.publish(topic,payload(2));assert inbox.get(timeout=10)['sequence_number']==2
    finally:
        publisher.close();subscriber.disconnect();subscriber.loop_stop()
