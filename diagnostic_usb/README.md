# Cube J1 Diagnostic USB

This directory is a safer diagnostic package for checking a Cube J1 before
B-route credentials are available.

It does not install the MQTT bridge, does not overwrite init rc files, and does
not disable stock services persistently. It can optionally enable ADB, apply
Wi-Fi settings, run BP35C0 serial checks, run `SKSCAN`, and publish a test MQTT
message.

## USB Layout

Copy the contents of this directory to the root of a FAT32 USB drive:

```text
CubeJMTS.txt
production_tool/
```

## Recommended First Run

1. Leave `production_tool/diag_config.sh` with the defaults.
2. Copy this directory's contents to the USB drive.
3. Insert the USB drive into the Cube J1 and power it on.
4. The script writes `/data/local/cube_diag.log` on the Cube J1.

With the defaults, the tool:

- does not enable ADB
- does not modify Wi-Fi settings
- temporarily stops `wisund` and `NDEcLiteAgent`
- checks `/dev/ttyS1` with `SKVER`, `SKINFO`, and `WOPT 1`
- restarts the stock Wi-SUN services at the end

## Optional Checks

Edit `production_tool/diag_config.sh` before copying to USB.

- `ENABLE_ADB=1`: enable ADB TCP port 5555 for this boot
- `PERSIST_ADB=1`: persist ADB TCP settings; avoid this for normal diagnostics
- `APPLY_WIFI=1`: copy `wpa_supplicant.conf` to the Cube J1
- `RUN_SKSCAN=1`: scan for visible Wi-SUN PANs without B-route credentials
- `RUN_MQTT_TEST=1`: publish a test message to the configured MQTT broker

For Wi-Fi testing, copy `wpa_supplicant.conf.example` to
`wpa_supplicant.conf`, then edit the SSID and password locally. Do not commit
real credentials.

For MQTT testing, set:

```sh
RUN_MQTT_TEST=1
MQTT_HOST=192.168.0.x
MQTT_PORT=1883
MQTT_USER=your_mqtt_user
MQTT_PASS=your_mqtt_password
MQTT_TOPIC=cubej/diagnostic/status
```

## Reading The Log

If ADB is enabled:

```sh
adb connect <Cube-J1-IP>:5555
adb shell cat /data/local/cube_diag.log
```

If ADB is not enabled, run again with `ENABLE_ADB=1` after deciding that is
acceptable for your network.

## Notes

`RUN_SKSCAN=1` does not authenticate to the smart meter. It only checks whether
the Wi-SUN module can see PANs nearby. B-route ID/password are still required for
PANA join and actual meter readings.
