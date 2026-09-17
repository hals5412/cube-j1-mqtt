#!/system/bin/sh

# 本番導入時の挙動を調整します。
# ADB TCP(ポート5555)は、導入のたびにここの値どおりの状態へ必ず揃えられます
# (過去の導入で永続化した設定が残っていても上書き・解除されます)。
#   ENABLE_ADB=0                : 無効(永続設定も解除)
#   ENABLE_ADB=1, PERSIST_ADB=0 : 今回の起動中のみ有効(再起動で無効に戻る)
#   ENABLE_ADB=1, PERSIST_ADB=1 : 有効を永続化(再起動後も維持)
# ADB TCPは設定で切り替えます。既定では今回の起動中だけ有効にします。
ENABLE_ADB=1
PERSIST_ADB=0

# Wi-Fi設定を本体へ反映します。
APPLY_WIFI=1

# 導入完了後にMQTTブリッジをすぐ起動します。
START_BRIDGE=1

# 終了済みNextDriveクラウドへ接続を試み大量のDNSクエリを発生させる
# 常駐デーモン群を停止・無効化します。オフライン電力監視には不要です。
# 0にすると無効化をスキップします(標準のクラウド挙動を残す場合)。
DISABLE_CLOUD=1

# tlsdated(TLS時刻同期)の同期先を生きた公開TLSホストへ向け直します。
# 既定の同期先は newsignaling.nextdrive.io(終了済み)で同期不能なため、
# 向け直すと時刻同期が復活し、同時にnextdriveへのDNSクエリもなくなります。
# 0にすると向け直しをスキップします(標準のtlsdated挙動を残す場合)。
REPOINT_TLSDATE=1
TLSDATE_HOST="www.google.com"

# Cube J1標準の初期設定用と思われるWi-Fi Direct/P2P AP(CubeJ-xxxxxx)を停止します。
# オフラインのWi-SUN→MQTT電力監視では不要なため、既定で無効化します。
# 0にすると無効化をスキップします(標準のP2P/AP挙動を残す場合)。
DISABLE_P2P_AP=1

# Wi-Fiプロファイルが無効化された場合に、状態確認・回数制限付きで復旧します。
# MQTTブローカーの停止だけでは動作せず、wlan0の接続・IPv4・
# デフォルトルートが5分継続して失われた場合だけ再接続を試みます。
ENABLE_WIFI_RECOVERY=1
