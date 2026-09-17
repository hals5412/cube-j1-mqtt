# Cube J1 本番導入手順

このディレクトリは、Cube J1を本番用のBルートMQTTブリッジとして動かすためのUSB配置です。

## 方針

- 本番導入後はUSBメモリを抜いて構いません。
- 電源断から復旧した場合も、initサービスとしてMQTTブリッジが自動起動します。
- ADB TCPは本番運用のログ取得・復旧用に有効化を維持します。
- 初期設定用と思われる `CubeJ-xxxxxx` のP2P/APは初期設定では停止します。
- Wi-Fi設定が意図せず無効化された場合に、回数制限付きの自己復旧を行います。
- 導入時に標準rcファイル、クラウド系サービスrc、tlsdated rc、Wi-Fi設定を `/data/local/cubej1-backup/` へバックアップします。
- ロールバックは `rollback_usb/` の構成をUSBメモリへコピーして実行します。

## 設定(複数台運用)

[config.json.example](config.json.example) を `config.json` にコピーしてから編集し、Bルート認証情報とMQTT接続先を入力します(実ファイル `config.json` は認証情報を含むためGit管理対象外)。

Cube J1を複数台運用する場合(例: 自宅と別拠点のスマートメーターをそれぞれ監視する場合)は、台ごとに以下を一意に設定します。

- `device_id`: HA上のデバイス識別子(例: `cubej1_home`、`cubej1_cottage`)
- `display_name`: HA上の表示名(例: `自宅 電力メーター`)

MQTTのクライアントIDは通常 `device_id` と同じ値になります(`mqtt_client_id` で個別指定も可能)。

台ごとの設定ファイルは `config.<名前>.json` のように複製して手元で管理し、導入時に対象の内容を `config.json` へコピーすると運用しやすくなります(認証情報を含むファイルはGit管理から除外してください)。

## Wi-Fi設定

[wpa_supplicant.conf.example](wpa_supplicant.conf.example) を `wpa_supplicant.conf` にコピーしてから編集します。以下の2か所に、自宅Wi-FiのSSIDとパスワードを入力してください。

```conf
ssid="Wi-FiのSSIDを入力"
psk="Wi-Fiのパスワードを入力"
```

`p2p_disabled=1` は、Cube J1が出す `CubeJ-xxxxxx` のP2P/APを抑制するための設定です。Home Assistant用のWi-SUN→MQTTブリッジ運用では通常不要なAPなので、基本的にはそのまま残してください。

実際の `config.json` と `wpa_supplicant.conf` には秘密情報が入るため、Git管理対象外です(`.gitignore` 済み)。取り扱いに注意してください。

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

インストーラは、導入のたびにADB TCP(ポート5555)を `install_config.sh` の値どおりの状態へ必ず揃えます。過去の導入で永続化した設定が残っていても、上書き・解除されます。

| ENABLE_ADB | PERSIST_ADB | 動作 |
|---|---|---|
| 0 | - | 無効(過去の永続設定も解除) |
| 1 | 0 | 今回の起動中のみ有効(再起動で無効に戻る) |
| 1 | 1 | 有効を永続化(再起動後も維持) |

本番設定では `ENABLE_ADB=1, PERSIST_ADB=1` とし、電源再投入後もログ取得・遠隔復旧手段を維持します。永続有効はLAN内にroot権限のADBアクセスを開くため、信頼できるLAN内でのみ使用してください。

注意: `PERSIST_ADB=1` で設定される `persist.sys.usb.config`(USBケーブル側のADB)は、無効化時もそのまま残します(TCP側の閉鎖が主目的のため)。

## CubeJ-xxxxxx のP2P/AP停止

Cube J1は標準状態で、スマートフォンアプリの初期設定用と思われる `CubeJ-xxxxxx` 形式のSSIDを出す場合があります。本ツールの通常運用では不要なため、初期設定では停止します。

制御は [install_config.sh](install_config.sh) の以下で行います。

```sh
DISABLE_P2P_AP=1
```

標準アプリでの再設定など、P2P/APを残したい場合だけ `DISABLE_P2P_AP=0` に変更し、`wpa_supplicant.conf` の `p2p_disabled=1` も削除してください。

## Wi-Fi自己復旧

Cube J1の古いWi-Fi管理処理により、接続失敗後の `wpa_supplicant.conf` に `disabled=1` が保存され、電源再投入だけではWi-Fiへ戻れなくなる場合があります。既定では `ENABLE_WIFI_RECOVERY=1` とし、次の条件と制限で復旧します。

- 起動後3分間はWi-Fi初期化を待つ
- `wpa_state`、IPv4アドレス、デフォルトルートを30秒ごとに確認する
- 異常が5分間継続した場合だけ復旧を開始する
- 永続化された `disabled=1` を除去し、ネットワークの再有効化と再接続を行う
- `wpa_cli`操作には15秒の上限を設け、応答しない場合も次の復旧段階へ進む
- 通常の再接続で復旧しない場合は、Wi-Fi管理サービスを再起動して再接続する
- 最大3回失敗した場合は30分休止し、無限の復旧ループを防ぐ
- MQTTブローカーだけが停止している場合はWi-Fiを操作しない

復旧前後には `wpa_state`、IPv4、デフォルトルート、ゲートウェイ到達性をログへ記録します。

状態は `/data/local/cubej1_wifi_recovery.status`、ログは `/data/local/cubej1_wifi_recovery.log` で確認できます。正常時は状態変化がない限りファイルへ書き込まないため、フラッシュへの継続的な書き込みは行いません。無効化する場合は [install_config.sh](install_config.sh) の `ENABLE_WIFI_RECOVERY=0` に変更して再導入してください。

## NextDriveクラウド接続と時刻同期

既定では、終了済みのNextDriveクラウドへ接続を試みる常駐サービスを停止・無効化します。また、`tlsdated` の時刻同期先を `www.google.com` へ向け直します。

- 標準のクラウド挙動を残したい場合は `install_config.sh` の `DISABLE_CLOUD=0` にしてください。
- `tlsdated` の向け直しを行わない場合は `REPOINT_TLSDATE=0` にしてください。
- `TLSDATE_HOST` を変更する場合は、ホスト名だけを指定してください。`/`、`:`, 空白などを含むURL形式は使えません。
- ロールバックUSBを実行すると、導入時にバックアップしたクラウド系サービスrcと `tlsdated.rc` も元に戻します。
