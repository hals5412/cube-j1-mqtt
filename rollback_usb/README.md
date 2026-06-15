# Cube J1 ロールバックUSB

本番導入後に標準状態へ戻すためのUSB構成です。

実USBを常時作っておく必要はありません。必要になったときに、このディレクトリの中身をFAT32 USBメモリ直下へコピーします。

```text
CubeJMTS.txt
production_tool/
```

ロールバックツールは、本番導入時にCube J1本体へ保存した以下のバックアップを使います。

```text
/data/local/cubej1-backup/latest
```

復元対象は主に以下です。

- `/system/etc/init/wisund.rc`
- `/system/etc/init/ndeclite_agent.rc`
- `/system/etc/init/mqtt_ha_bridge.rc`
- `/system/etc/init/sessiond.rc`
- `/system/etc/init/fms.rc`
- `/system/etc/init/fmssecman.rc`
- `/system/etc/init/NDCloudDaemon.rc`
- `/system/etc/init/rds.rc`
- `/system/etc/init/iijschedule.rc`
- `/system/etc/init/transman.rc`
- `/system/etc/init/tlsdated.rc`
- `/data/misc/wifi/wpa_supplicant.conf`

MQTTブリッジ関連の `/data/local/config.json`、`/data/local/mqtt_bridge.py`、`/data/local/led_effect.sh` は削除します。

結果ログは以下に残ります。

```text
/data/local/cubej1_rollback.log
```
