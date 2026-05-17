# Cube J1 本番導入手順

このディレクトリは、Cube J1を本番用のBルートMQTTブリッジとして動かすためのUSB配置です。

## 方針

- 本番導入後はUSBメモリを抜いて構いません。
- 電源断から復旧した場合も、initサービスとしてMQTTブリッジが自動起動します。
- ADB TCPは初期設定では有効化しません。
- 導入時に標準rcファイルとWi-Fi設定を `/data/local/cubej1-backup/` へバックアップします。
- ロールバックは `rollback_usb/` の構成をUSBメモリへコピーして実行します。

## 拠点A/拠点Bの設定

拠点A用は以下を `config.json` としてコピーしてから、認証情報を入力します。

```text
config.site_a.example.json
```

拠点B用は以下を使います。

```text
config.site_b.example.json
```

`device_id` は以下で固定する方針です。

```text
拠点A: cubej1_site_a
拠点B: cubej1_site_b
```

表示名は以下です。

```text
拠点A 電力メーター
拠点B 電力メーター
```

## Wi-Fi設定

[wpa_supplicant.conf](wpa_supplicant.conf) を直接編集します。以下の2か所に、自宅Wi-FiのSSIDとパスワードを入力してください。

```conf
ssid="Wi-FiのSSIDを入力"
psk="Wi-Fiのパスワードを入力"
```

実際の `config.json` と `wpa_supplicant.conf` には秘密情報が入るため、取り扱いに注意してください。

## USBメモリへの配置

FAT32形式のUSBメモリ直下に以下を配置します。

```text
CubeJMTS.txt
production_tool/
```

## 導入後にHome Assistantへ出る情報

主な計測値:

- 瞬時電力
- 積算電力量 正方向
- 積算電力量 逆方向
- 瞬時電流 R相
- 瞬時電流 T相

診断情報:

- availability: `online` / `offline`
- 最終取得時刻
- Wi-SUN状態
- Wi-SUN LQI
- Wi-SUNチャンネル
- Wi-SUN PAN ID
- スマートメーターIPv6
- ブリッジ稼働時間
- エラー回数
- 最終エラー
- MQTT再接続回数
- Wi-SUN再接続回数
- 積算電力量係数
- 積算電力量単位

## ADB TCP

通常は `install_config.sh` の以下を維持してください。

```sh
ENABLE_ADB=0
PERSIST_ADB=0
```

トラブル時に一時的にログを読みたい場合だけ `ENABLE_ADB=1` にします。`PERSIST_ADB=1` は、電源再投入後もADB TCPが開くため通常は使いません。
