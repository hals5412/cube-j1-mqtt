#!/system/bin/sh

# Cube J1 診断設定。
# 実際の認証情報を入れたファイルはgitに含めないでください。

# ADBは、実行後に /data/local/cube_diag.log を読むときに便利です。
# ENABLE_ADB=1 にすると、今回の起動中だけ ADB over TCP を有効化します。
# PERSIST_ADB=1 にすると persist.* プロパティにも書き込みます。診断時は0のままにしてください。
ENABLE_ADB=0
PERSIST_ADB=0

# APPLY_WIFI=1 にすると、このUSB内の wpa_supplicant.conf を本体へコピーします。
# Cube J1 のWi-Fi設定を変更するため、準備ができるまでは0のままにしてください。
APPLY_WIFI=0

# BP35C0確認中に /dev/ttyS1 を使用している可能性がある標準サービスを一時停止します。
# 最後に再起動します。init rcファイルは変更しません。
STOP_WISUN_SERVICES=1

# シリアル / Wi-SUN 診断。
SERIAL_PORT=/dev/ttyS1
RUN_SERIAL_TEST=1
RUN_SKSCAN=0
SKSCAN_DURATION=4

# 任意のMQTT送信テスト。Bルート認証情報は不要です。
RUN_MQTT_TEST=0
MQTT_HOST=
MQTT_PORT=1883
MQTT_USER=
MQTT_PASS=
MQTT_TOPIC=cubej/diagnostic/status
DEVICE_ID=cubej1_diag
