# Cube J1 診断用USB

このディレクトリは、Bルート認証ID/パスワードを入手する前に Cube J1 を確認するための、比較的安全な診断用USB一式です。

この診断ツールは MQTT ブリッジをインストールせず、init rc ファイルを上書きせず、標準サービスを永続的に無効化しません。必要に応じて ADB の一時有効化、Wi-Fi設定の適用、BP35C0 のシリアル確認、`SKSCAN`、MQTTテスト送信を実行できます。

## USBの配置

FAT32形式のUSBメモリ直下に、このディレクトリの中身をコピーします。

```text
CubeJMTS.txt
production_tool/
```

## 初回におすすめの確認

1. `production_tool/diag_config.sh` は初期値のままにします。
2. このディレクトリの中身をUSBメモリへコピーします。
3. Cube J1 にUSBメモリを挿入し、電源を入れます。
4. 診断結果は Cube J1 側の `/data/local/cube_diag.log` に出力されます。

初期設定では、以下だけを実行します。

- ADBは有効化しない
- Wi-Fi設定は変更しない
- `wisund` と `NDEcLiteAgent` を一時停止する
- `/dev/ttyS1` に対して `SKVER`、`SKINFO`、`WOPT 1` を実行する
- 最後に標準のWi-SUN関連サービスを再起動する

## 任意の追加確認

USBメモリへコピーする前に `production_tool/diag_config.sh` を編集します。

- `ENABLE_ADB=1`: 今回の起動中だけ ADB TCP ポート5555を有効化する
- `PERSIST_ADB=1`: ADB TCP設定を永続化する。通常の診断では避けてください
- `APPLY_WIFI=1`: `wpa_supplicant.conf` を Cube J1 にコピーする
- `RUN_SKSCAN=1`: Bルート認証なしで見えるWi-SUN PANをスキャンする
- `RUN_MQTT_TEST=1`: 設定したMQTTブローカーへテストメッセージを送信する

Wi-Fiを確認する場合は、`wpa_supplicant.conf.example` を `wpa_supplicant.conf` にコピーしてから、SSIDとパスワードをローカルで編集してください。実際の認証情報はcommitしないでください。

MQTT送信を確認する場合は、以下を設定します。

```sh
RUN_MQTT_TEST=1
MQTT_HOST=192.168.0.x
MQTT_PORT=1883
MQTT_USER=MQTTユーザー名を入力
MQTT_PASS=MQTTパスワードを入力
MQTT_TOPIC=cubej/diagnostic/status
```

## ログの確認

ADBを有効化した場合は、以下でログを確認できます。

```sh
adb connect <Cube-J1-IP>:5555
adb shell cat /data/local/cube_diag.log
```

ADBを有効化していない場合は、ネットワーク上のリスクを許容できることを確認してから、`ENABLE_ADB=1` にして再実行してください。

## 補足

`RUN_SKSCAN=1` はスマートメーターへ認証しません。近くのWi-SUN PANが見えるかを確認するだけです。PANA接続と実際の電力データ取得には、Bルート認証ID/パスワードが必要です。
