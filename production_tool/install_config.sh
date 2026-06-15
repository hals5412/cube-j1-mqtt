#!/system/bin/sh

# 本番導入時の挙動を調整します。
# ADB TCP(ポート5555)は、導入のたびにここの値どおりの状態へ必ず揃えられます
# (過去の導入で永続化した設定が残っていても上書き・解除されます)。
#   ENABLE_ADB=0                : 無効(永続設定も解除)
#   ENABLE_ADB=1, PERSIST_ADB=0 : 今回の起動中のみ有効(再起動で無効に戻る)
#   ENABLE_ADB=1, PERSIST_ADB=1 : 有効を永続化(再起動後も維持)
ENABLE_ADB=0
PERSIST_ADB=0

# Wi-Fi設定を本体へ反映します。
APPLY_WIFI=1

# 導入完了後にMQTTブリッジをすぐ起動します。
START_BRIDGE=1

# 終了済みNextDriveクラウドへ接続を試み大量のDNSクエリを発生させる
# 常駐デーモン群を停止・無効化します。オフライン電力監視には不要です。
# 0にすると無効化をスキップします(標準のクラウド挙動を残す場合)。
DISABLE_CLOUD=1
