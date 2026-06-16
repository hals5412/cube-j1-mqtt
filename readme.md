# Cube J1 MQTT

本プロジェクトは、2025年3月31日にサービスを終了した「NextDrive Cube J1」を活用し、Home Assistant の MQTT デバイスとして利用するためのツールです。

> [!NOTE]
> 本リポジトリは [tsuyopon123/cube-j1-mqtt](https://github.com/tsuyopon123/cube-j1-mqtt) を大元とするフォークです。
> オリジナルに対して、長期運用向けの自己復旧・診断センサー・ログ管理に加え、終了済み NextDrive クラウドへの接続停止（DNS クエリ削減）と時刻同期の復活などの機能を追加しています。詳細は「[本家からの変更点](#本家からの変更点)」を参照してください。

Cube J1 に内蔵されている Wi-SUN モジュール（BP35C0）を利用して、スマートメーター（B ルート）から各種計測値を定期的に取得し、MQTT 経由で Home Assistant へ送信します。

> [!WARNING]
> 本ツールの利用により、機器の動作不良、ネットワーク上のセキュリティリスク等が生じる可能性があります。
> 内容を十分に理解したうえで、利用者ご自身の責任で管理・運用してください。
> 本ツールの利用によって生じたいかなる損害についても、作成者および関係者は責任を負いません。

## 概要

Cube J1 上で専用の MQTT ブリッジプログラム（`mqtt_bridge.py`）が常駐稼働し、スマートメーターのデータを継続的に取得・送信します。
また、Home Assistant の「MQTT 自動検出（MQTT Auto Discovery）」に対応しているため、接続設定を済ませるだけでダッシュボードにセンサーが自動的に登録されます。

> [!NOTE]
> 本ツールを利用する前に、Home Assistant 側で MQTT ブローカー（Mosquitto broker など）の導入および MQTT 統合の設定を完了させておいてください。
> 参考: [MQTT 統合 — Home Assistant ドキュメント](https://www.home-assistant.io/integrations/mqtt/)

<img width="1032" height="504" alt="image" src="https://github.com/user-attachments/assets/daefc3f2-6c8a-416e-b433-1b45349d5f4f" />


## 取得できるセンサー

Home Assistant 上で以下のセンサーとしてデータを取り扱うことができます。

| センサー名 | ECHONET Lite EPC | 単位 | HA device_class |
|---|---|---|---|
| 瞬時電力 | E7 | W | power |
| 積算電力量（正方向） | E0 | kWh | energy (total_increasing) |
| 積算電力量（逆方向） | E3 | kWh | energy (total_increasing) |
| 瞬時電流 R相 | E8（上位2バイト） | A | current |
| 瞬時電流 T相 | E8（下位2バイト） | A | current |

※ 係数（EPC: D3）および積算電力量単位（EPC: E1）も自動で取得し、積算電力量の正確な kWh 換算に適用します。

さらに、起動時にメーターのプロパティマップ（EPC: 9F）を取得し、**そのメーターが対応する場合のみ**以下を追加でポーリングします（適応ポーリング）。

| センサー名 | ECHONET Lite EPC | 単位 | HA device_class |
|---|---|---|---|
| 定時積算電力量（正方向） | EA | kWh | energy (total_increasing) |
| 定時積算電力量（逆方向） | EB | kWh | energy (total_increasing) |
| メーター異常状態 | 88 | - | - |
| メーター日付 / 時刻 | 98 / 97 | - | - |

定時積算電力量（EA/EB）は、メーター自身のタイムスタンプ付きで30分境界の積算値を取得でき、エネルギー集計の精度に役立ちます。

上記に加えて、診断用センサー（最終取得時刻、Wi-SUN状態、LQI、チャンネル、PAN ID、スマートメーターIPv6、ブリッジ稼働時間、エラー回数、最終エラー、MQTT/Wi-SUN再接続回数、積算電力量係数・単位）も自動登録されます。availability（LWT）に対応しており、ブリッジ停止時は各エンティティが unavailable になります。

## 導入方法

Cube J1 は USB メモリ内の特定ファイル構成を検出すると自動的にスクリプトを実行する仕組みを持っています。
リポジトリの内容をそのまま USB メモリ直下へコピーし起動するだけでセットアップが完了します。

> [!TIP]
> B ルート認証 ID / パスワードを入手する前に本体・Wi-Fi・Wi-SUN モジュール・MQTT 到達性だけを確認したい場合は、`diagnostic_usb/` を利用してください。
> 診断用ツールは MQTT ブリッジのインストール、init rc の上書き、標準サービスの永続無効化を行いません。

> [!TIP]
> 本番導入前の設定ファイル作成、バックアップ、ロールバックについては `production_tool/README_本番導入手順.md` を参照してください。

### 手順

1. 本リポジトリをダウンロード（Clone）する。
2. `production_tool/config.json.example` を `production_tool/config.json` にコピーし、認証情報やネットワークの接続先を設定する（詳細は[config.json の設定](#configjson-の設定)を参照）。
3. `production_tool/wpa_supplicant.conf.example` を `production_tool/wpa_supplicant.conf` にコピーし、Wi-Fi の SSID とパスワードを設定する。

> [!IMPORTANT]
> `config.json` と `wpa_supplicant.conf` は認証情報を含むため Git 管理対象外（`.gitignore` 済み）です。各 `.example` ファイルをコピーして作成してください。
4. **FAT32 形式**でフォーマットされた USB メモリを用意し、`CubeJMTS.txt` と `production_tool/` ディレクトリを、USB メモリの直下（ルートディレクトリ）にコピーする。
5. Cube J1 に USB メモリを挿入し、電源を入れる。
6. 自動的にスクリプトが実行されます。セットアップが完了すると、**本体の LED が白色に 10 回点滅**します。また、Wi-Fi 接続が成功すると、LED は緑色に点灯します。

以降は自動的に MQTT ブリッジが起動し、スマートメーターからのデータ取得と Home Assistant への送信が開始されます。
※ 設定を再度変更したい場合は、USB メモリ内のファイルを編集して Cube J1 に挿入し、電源を再投入してください。

### config.json の設定

設定ファイル（`config.json`）の記入例および各項目の説明です。

```json
{
    "br_id":          "（スマートメーター B ルート認証 ID）",
    "br_pwd":         "（スマートメーター B ルートパスワード）",
    "mqtt_host":      "（MQTT ブローカーの IP アドレス）",
    "mqtt_port":      1883,
    "mqtt_user":      "（MQTT ユーザー名）",
    "mqtt_pass":      "（MQTT パスワード）",
    "device_id":      "cubej1",
    "display_name":   "Cube J1 Smart Meter",
    "serial_port":    "/dev/ttyS1",
    "poll_interval":  60,
    "log_enabled":    true,
    "log_max_bytes":  10485760
}
```

| キー | 説明 |
|---|---|
| `br_id` | スマートメーターの B ルート認証 ID（32 文字） |
| `br_pwd` | スマートメーターの B ルートパスワード（12 文字） |
| `mqtt_host` | MQTT ブローカーの IP アドレス（Mosquitto アドオン利用時など、Home Assistant と同居している場合はその IP） |
| `mqtt_port` | MQTT ブローカーのポート番号（デフォルトは `1883`） |
| `mqtt_user` / `mqtt_pass` | MQTT ブローカーの認証情報（設定していない場合は空文字 `""` で可） |
| `device_id` | HA 上のデバイス識別子。複数台運用時は一意にする |
| `display_name` | HA 上のデバイス表示名（省略可） |
| `mqtt_client_id` | MQTT クライアント ID（省略時は `device_id` と同じ） |
| `mqtt_keepalive` | MQTT keepalive 秒（省略時は `300`） |
| `serial_port` | Wi-SUN モジュールのシリアルデバイス指定。通常は変更不要（`/dev/ttyS1`） |
| `poll_interval` | スマートメーターへデータを取得しに行くポーリング間隔（秒） |
| `log_enabled` | `false` で動作ログのファイル書き込みを無効化（省略時は `true`） |
| `log_max_bytes` | 動作ログのローテーションサイズ（省略時は `10485760` = 10MB） |

## LED のステータス表示

Cube J1 の RGB LED は、動作状態に応じて以下のように発光・点滅します。

| 状態 | LED の動き |
|---|---|
| セットアップ完了時 | 白色で点滅（10回） |
| Wi-SUN コマンド送信中（SKSTACK） | 緑色と青色が交互に点滅（0.2 秒間隔） |
| PANA 接続待機中（SKJOIN） | 緑色と青色が交互に点滅（0.2 秒間隔） |
| データ取得・MQTTパブリッシュ中 | 青色で点灯 |

## システムの内部動作・仕様

技術要件等をメモとしてまとめます。

### セットアップ時の動作

USB メモリ挿入時に Cube J1 が自動実行するメインスクリプト（`production_tool`）は、以下の処理を順に行っています。

1. **ADB の TCP 有効化(オプション、既定は無効)**: `production_tool/install_config.sh` で `ENABLE_ADB=1` とした場合のみ、ポート `5555` で ADB 接続を受け付けるように設定。`PERSIST_ADB=1` を併用すると電源再投入後も維持される
2. **Wi-Fi 設定**: `wpa_supplicant.conf` をシステムに配置してネットワークを再起動
3. **ブリッジプログラムの配置**: `config.json` と `mqtt_bridge.py` を `/data/local/` ディレクトリへコピー
4. **競合サービスの停止**: Wi-SUN モジュール（`/dev/ttyS1`）を占有してしまう既存サービス（`wisund`、`NDEcLiteAgent`）を停止し、以後の起動を無効化
5. **クラウド系サービスの無効化(既定で有効)**: 終了済みの NextDrive クラウドへ延々と接続を試み大量の DNS クエリを発生させる常駐デーモン（`sessiond`、`fms`、`fmssecman`、`NDCloudDaemon`、`rds`、`iijschedule`、`transman`）を停止・無効化する。`install_config.sh` の `DISABLE_CLOUD=0` で無効化をスキップできる
6. **時刻同期先の向け直し(既定で有効)**: `tlsdated`（TLS 時刻同期）の同期先は既定で `newsignaling.nextdrive.io`（終了済み）にハードコードされ同期不能なため、生きた公開 TLS ホスト（既定 `www.google.com`）へ向け直す。これにより時刻同期が復活し、同時に NextDrive への DNS クエリもなくなる。`install_config.sh` の `REPOINT_TLSDATE` / `TLSDATE_HOST` で変更・無効化できる
7. **init サービスの登録**: 再起動後もプログラムが自動起動するよう、`mqtt_ha_bridge.rc` を `/system/etc/init/` へ配置
8. **ブリッジ即時起動**: `mqtt_ha_bridge` サービスとして `mqtt_bridge.py` を起動開始
9. **完了通知**: `led_effect.sh` を呼び出し、LED を点滅させてセットアップ完了を通知

### ファイル構成

```text
production_tool/
├── production_tool          # メインとなる自動実行セットアップスクリプト
├── mqtt_bridge.py           # Wi-SUN ↔ ECHONET Lite ↔ MQTT のブリッジプログラム本体
├── led_effect.sh            # RGB LED の点灯・点滅を制御するスクリプト
├── config.json.example      # 接続先などのひな形（コピーして config.json を作成・編集）
├── wpa_supplicant.conf.example  # Wi-Fi 設定のひな形（コピーして wpa_supplicant.conf を作成）
├── mqtt_ha_bridge.rc        # ブート時にブリッジを自動起動させるための init スクリプト
├── wisund_disabled.rc       # 標準の wisund サービスを無効化するための RC ファイル
├── ndeclite_disabled.rc     # 標準の NDEcLiteAgent を無効化するための RC ファイル
├── tlsdated_timesync.rc     # tlsdated の時刻同期先を公開ホストへ向け直す RC ファイル
└── cloud_disabled/          # NextDrive クラウド系サービスを無効化する RC ファイル群
    ├── sessiond.rc          #   session.nextdrive.io への接続元
    ├── fms.rc               #   cube-agent.nextdrive.io への接続元
    ├── fmssecman.rc
    ├── NDCloudDaemon.rc     #   pubsub/newsignaling.nextdrive.io への接続元
    ├── rds.rc
    ├── iijschedule.rc
    └── transman.rc
```

### 技術仕様詳細

- **実行環境**: Cube J1 上の Android 系 Linux（Python 2.7 にて動作）
- **依存ライブラリ**: Python 2.7 標準ライブラリのみを使用（`termios`, `socket`, `struct`, `select`, `json`, `threading` など）。`pyserial` や `paho-mqtt` 等の外部ライブラリは不要です。
- **シリアル通信**: `termios` にて raw モードを設定し、115200 bps で通信します。
- **MQTT 実装**: MQTT 3.1.1 の仕様に基づきソケット通信を用いて独自実装（QoS 0、TCP keepalive 対応、自動再接続機能あり）。
- **Wi-SUN 接続**: PAN スキャンを実行し、最も LQI（リンク品質）の良い PAN を自動選択します。
- **動作ログ**: ブリッジの動作ログは本体内の `/data/local/mqtt_bridge.log` に記録されます。既定 10MB で `.1` へ世代交代（合計最大約 20MB）し、正常時の計測ログは 1 時間に 1 回へ間引かれます（エラー・状態変化は常時記録）。`config.json` の `log_enabled` / `log_max_bytes` で調整できます。
- **自己復旧**: ERXUDP 無応答が 3 回連続すると Wi-SUN を再 join します。再 join はバックオフ付き（30〜300 秒）で成功までリトライし、失敗が 5 回続くたびにシリアルポートを開き直します。PANA 認証失敗（EVENT 24）も再 join の契機になります。

### MQTT トピック構造

| 用途 | トピック |
|---|---|
| HA auto-discovery | `homeassistant/sensor/{device_id}/{sensor_id}/config` |
| 瞬時電力 | `cubej/{device_id}/power` |
| 積算電力量（正方向） | `cubej/{device_id}/energy_forward` |
| 積算電力量（逆方向） | `cubej/{device_id}/energy_reverse` |
| 瞬時電流 R相 | `cubej/{device_id}/current_r` |
| 瞬時電流 T相 | `cubej/{device_id}/current_t` |

## 本家からの変更点

大元の [tsuyopon123/cube-j1-mqtt](https://github.com/tsuyopon123/cube-j1-mqtt) に対する、本フォークの主な変更・追加点です。

### 自己復旧（Wi-SUN）

- ERXUDP 無応答が 3 回連続したらポーリングを打ち切り、Wi-SUN 再 join へ移行
- 再 join はバックオフ付き（30〜300 秒）で成功までリトライし、死んだセッションへのポーリングに戻らない
- join / 再 join の失敗が 5 回連続するたびにシリアルポートを開き直す
- ポーリング中の EVENT 24（PANA 認証失敗）で即再 join、EVENT 29（セッション失効）は自動再認証を待つ

### クラウド接続の停止・DNS クエリ削減

NextDrive のクラウドサービスは 2025 年 3 月で終了しているが、Cube J1 標準のクラウド系常駐デーモンは終了済みクラウドへ接続を試み続け、大量の DNS クエリ（`session.nextdrive.io` / `cube-agent.nextdrive.io` / `newsignaling.nextdrive.io` など）を発生させる。オフラインの Wi-SUN → MQTT 電力監視には不要なため、以下を行う。

- クラウド系デーモン（`sessiond`、`fms`、`fmssecman`、`NDCloudDaemon`、`rds`、`iijschedule`、`transman`）を停止・無効化（`DISABLE_CLOUD`）
- `tlsdated`（TLS 時刻同期）の同期先は既定で `newsignaling.nextdrive.io`（終了済み）にハードコードされ同期不能だったため、生きた公開 TLS ホスト（既定 `www.google.com`）へ向け直し、時刻同期を復活させつつ NextDrive へのクエリをなくす（`REPOINT_TLSDATE` / `TLSDATE_HOST`）
- 元の `.rc` は導入時に `/data/local/cubej1-backup/` へ自動バックアップされ、ロールバックUSBで復元できる

### 取得項目の拡張（プロパティマップ適応ポーリング）

別フォーク [nanamitm/cube-j1-mqtt](https://github.com/nanamitm/cube-j1-mqtt) のプロパティマップ適応ポーリングを参考に、以下を取り込んだ。

- 起動時にメーターのプロパティマップ（EPC: 9F）を取得し、**対応する EPC だけ**を追加ポーリング対象にする
- 追加取得: 定時積算電力量（EA/EB、タイムスタンプ付き）、メーター異常状態（88）、メーター日付・時刻（97/98）
- 独自の堅牢化を追加:
  - プロパティマップ取得は join 直後の自発 INF を取り違えることがあるため数回リトライ（`PROPERTY_MAP_ATTEMPTS`）
  - 1 リクエストで返すプロパティ数を制限するメーター（超過分を黙って切り捨てる個体を実機で確認）に対応するため、Get を最大 6 EPC ずつにバッチ分割（`POLL_BATCH_SIZE`）して応答をマージ

### 診断・監視

- 診断センサー 13 種（最終取得時刻、Wi-SUN 状態、LQI、エラー回数、再接続回数など）を HA へ追加
- availability（LWT + expire_after）対応: ブリッジ停止時にエンティティが unavailable になり、HA 側で取得停止を検知できる
- discovery 設定を MQTT 再接続後と 24 時間ごとに再 publish（ブローカーの retain データ消失対策）

### ログ管理

- サイズ上限つきローテーション（既定 10MB、`.1` へ世代交代）
- 正常時の計測ログは 1 時間に 1 回へ間引き（エラー・状態変化・復旧後初回は常時記録）
- `config.json` の `log_enabled` / `log_max_bytes` で無効化・サイズ変更が可能

### インストーラ

- 導入ログ（`/data/local/cubej1_install.log`）、必須ファイル検証、失敗時の赤 LED 通知
- 導入前に既存ファイルを `/data/local/cubej1-backup/` へ自動バックアップし、`rollback_usb/` でロールバック可能
- ADB TCP は `install_config.sh` の設定どおりに必ず状態を揃える（既定は無効。本家は無条件で永続有効化）
- B ルート認証情報なしで本体・Wi-Fi・MQTT 到達性を確認できる診断用 USB（`diagnostic_usb/`）を追加

### その他

- MQTT keepalive の設定化（既定 300 秒）、Will（LWT）対応、再送キュー上限
- `display_name` / `mqtt_client_id` の設定化（複数台運用向け）
- センサー名・ログ・コメントの日本語化

## 参考記事

Cube J1 のソフトウェア内部構造や、USB メモリを用いたスクリプト自動実行の仕組みについては、以下の記事で詳しく解説しています。

- [NextDrive Cube J1を分解せずにrootを取りたい！ - Zenn](https://zenn.dev/tsuyopon123/articles/cube-j1-root)

## トラブルシューティング

システムの状態や不具合の原因は、ADB 経由でログを確認することでデバッグが可能です。
ADB は既定で無効のため、事前に `production_tool/install_config.sh` の `ENABLE_ADB=1` を設定した USB で再セットアップしておく必要があります。

```sh
# Cube J1 の IP アドレスに対し、ポート 5555 で ADB 接続
adb connect <Cube-J1 の IP アドレス>:5555

# 最新の動作ログを出力
adb shell cat /data/local/mqtt_bridge.log

# 実行中の Python プロセスを確認 (mqtt_bridge.py が動いているかどうか)
adb shell ps | grep python
```
