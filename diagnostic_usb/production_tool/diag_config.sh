#!/system/bin/sh

# Cube J1 diagnostic settings.
# Keep all credentials out of git when using real values.

# ADB is useful for reading /data/local/cube_diag.log after the run.
# ENABLE_ADB=1 enables ADB over TCP for the current boot.
# PERSIST_ADB=1 also writes persist.* properties; leave it 0 for diagnostics.
ENABLE_ADB=0
PERSIST_ADB=0

# APPLY_WIFI=1 copies wpa_supplicant.conf from this USB package to the device.
# This changes the Cube J1 Wi-Fi config, so leave it 0 unless you are ready.
APPLY_WIFI=0

# Temporarily stop stock services that may hold /dev/ttyS1 while testing BP35C0.
# They are restarted at the end; init rc files are not modified.
STOP_WISUN_SERVICES=1

# Serial / Wi-SUN diagnostics.
SERIAL_PORT=/dev/ttyS1
RUN_SERIAL_TEST=1
RUN_SKSCAN=0
SKSCAN_DURATION=4

# Optional MQTT publish test. This does not require B-route credentials.
RUN_MQTT_TEST=0
MQTT_HOST=
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
MQTT_TOPIC=cubej/diagnostic/status
DEVICE_ID=cubej1_diag

