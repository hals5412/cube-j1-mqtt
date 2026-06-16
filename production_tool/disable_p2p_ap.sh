#!/system/bin/sh

# Cube J1の初期設定用と思われるWi-Fi Direct/P2P APを停止します。
# 通常の自宅Wi-Fi接続(wlan0)は止めず、p2p-wlan0-0 と
# P2P/AP用dnsmasqだけを対象にします。

LOG=/data/local/cubej1_p2p_ap.log
WPA_CONF=/data/misc/wifi/wpa_supplicant.conf
WPA_CLI="wpa_cli -p /data/misc/wifi/sockets"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

ensure_p2p_disabled_config() {
    if [ -f "$WPA_CONF" ] && ! grep -q '^p2p_disabled=1' "$WPA_CONF"; then
        log "wpa_supplicant.confへ p2p_disabled=1 を追加します"
        echo "p2p_disabled=1" >> "$WPA_CONF"
        chmod 660 "$WPA_CONF"
        chown system:wifi "$WPA_CONF"
        $WPA_CLI -i wlan0 reconfigure >/dev/null 2>&1
    fi
}

stop_p2p_once() {
    $WPA_CLI -i p2p-wlan0-0 p2p_group_remove p2p-wlan0-0 >/dev/null 2>&1
    $WPA_CLI -i wlan0 p2p_group_remove p2p-wlan0-0 >/dev/null 2>&1
    $WPA_CLI -i wlan0 p2p_stop_find >/dev/null 2>&1
    $WPA_CLI -i wlan0 p2p_flush >/dev/null 2>&1

    ifconfig p2p-wlan0-0 down >/dev/null 2>&1
    stop_p2p_dnsmasq
}

p2p_dnsmasq_pids() {
    ps | grep '[d]nsmasq' | while read user pid rest; do
        cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)"
        case "$cmd" in
            *"--dhcp-range=192.168.100."*|*"p2p-wlan0-0"*)
                echo "$pid"
                ;;
        esac
    done
}

stop_p2p_dnsmasq() {
    for pid in $(p2p_dnsmasq_pids); do
        log "P2P/AP用dnsmasqを停止します: pid=$pid"
        kill "$pid" >/dev/null 2>&1
    done
}

p2p_dnsmasq_is_active() {
    [ -n "$(p2p_dnsmasq_pids)" ]
}

p2p_is_active() {
    ip addr show p2p-wlan0-0 >/dev/null 2>&1 && return 0
    p2p_dnsmasq_is_active && return 0
    return 1
}

log "P2P/AP停止処理を開始します"
ensure_p2p_disabled_config

i=0
while [ "$i" -lt 30 ]; do
    stop_p2p_once
    if ! p2p_is_active; then
        log "P2P/APは停止しています"
        exit 0
    fi
    i=$((i + 1))
    sleep 2
done

log "P2P/AP停止処理がタイムアウトしました"
exit 1
