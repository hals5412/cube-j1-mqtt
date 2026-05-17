#!/system/bin/sh

# 本番導入時の挙動を調整します。
# ADB TCPは通常無効のままにしてください。必要なときだけ一時的に1へ変更します。
ENABLE_ADB=0
PERSIST_ADB=0

# Wi-Fi設定を本体へ反映します。
APPLY_WIFI=1

# 導入完了後にMQTTブリッジをすぐ起動します。
START_BRIDGE=1
