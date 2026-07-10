#!/system/bin/sh

# Wi-Fi自己復旧処理です。
# MQTTブローカーの障害だけでは動作せず、wlan0の接続・IPv4・
# デフォルトルートが継続して失われた場合だけ限定的に再接続します。

LOG=/data/local/cubej1_wifi_recovery.log
STATUS_FILE=/data/local/cubej1_wifi_recovery.status
PID_FILE=/data/local/cubej1_wifi_recovery.pid
WPA_CONF=/data/misc/wifi/wpa_supplicant.conf
WPA_CLI="/system/bin/wpa_cli -p /data/misc/wifi/sockets -i wlan0"

# 起動直後のWi-Fi初期化と競合しないよう3分待ちます。
STARTUP_GRACE_SEC=${STARTUP_GRACE_SEC:-180}
# 30秒間隔で確認し、実時間で5分継続した場合に障害と判定します。
CHECK_INTERVAL_SEC=${CHECK_INTERVAL_SEC:-30}
FAILURE_TRIGGER_SEC=${FAILURE_TRIGGER_SEC:-300}
# 1回の復旧操作後に接続完了を待つ時間です。
RECOVERY_WAIT_SEC=${RECOVERY_WAIT_SEC:-90}
MAX_RECOVERY_ATTEMPTS=${MAX_RECOVERY_ATTEMPTS:-3}
# 連続失敗時は再試行を止め、復旧ループを防ぎます。
COOLDOWN_SEC=${COOLDOWN_SEC:-1800}
LOG_MAX_BYTES=${LOG_MAX_BYTES:-131072}

LAST_STATUS=""
WIFI_REASON=""

rotate_log_if_needed() {
    [ -f "$LOG" ] || return 0
    size="$(wc -c < "$LOG" 2>/dev/null)"
    case "$size" in
        ''|*[!0-9]*) return 0 ;;
    esac
    if [ "$size" -ge "$LOG_MAX_BYTES" ]; then
        rm -f "$LOG.1"
        mv "$LOG" "$LOG.1"
    fi
}

log() {
    rotate_log_if_needed
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

set_status() {
    state="$1"
    detail="$2"
    key="$state|$detail"
    [ "$key" = "$LAST_STATUS" ] && return 0
    LAST_STATUS="$key"
    echo "timestamp=$(date '+%Y-%m-%d %H:%M:%S') state=$state detail=$detail" > "$STATUS_FILE"
}

cleanup() {
    if [ -f "$PID_FILE" ] && [ "$(cat "$PID_FILE" 2>/dev/null)" = "$$" ]; then
        rm -f "$PID_FILE"
    fi
}

stop_by_signal() {
    cleanup
    exit 0
}

if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null)"
    case "$old_pid" in
        ''|*[!0-9]*) ;;
        *)
            if kill -0 "$old_pid" 2>/dev/null; then
                old_cmd="$(tr '\0' ' ' < "/proc/$old_pid/cmdline" 2>/dev/null)"
                case "$old_cmd" in
                    *wifi_recovery.sh*)
                        log "既存のWi-Fi自己復旧処理が動作中です: pid=$old_pid"
                        exit 0
                        ;;
                esac
            fi
            ;;
    esac
fi

echo "$$" > "$PID_FILE"
trap cleanup EXIT
trap stop_by_signal HUP INT TERM

wifi_is_healthy() {
    has_ipv4=0
    /system/bin/ip -4 addr show dev wlan0 2>/dev/null | grep -q 'inet ' && has_ipv4=1
    /system/bin/ifconfig wlan0 2>/dev/null | grep -q 'inet addr:' && has_ipv4=1

    route_line="$(/system/bin/ip route 2>/dev/null | grep '^default .*dev wlan0' | head -n 1)"
    has_default_route=0
    [ -n "$route_line" ] && has_default_route=1

    if [ "$has_ipv4" -eq 1 ] && [ "$has_default_route" -eq 1 ]; then
        gateway="$(echo "$route_line" | sed -n 's/^default via \([^ ]*\).*/\1/p')"
        if [ -n "$gateway" ] && /system/bin/ping -c 1 -W 2 "$gateway" >/dev/null 2>&1; then
            WIFI_REASON="healthy"
            return 0
        fi

        # ICMP応答を返さないルーターもあるため、IPと経路がある場合だけ
        # wpa_cliを補助確認に使います。切断中は呼ばず、長い応答待ちを避けます。
        status="$($WPA_CLI status 2>/dev/null)"
        if echo "$status" | grep -q '^wpa_state=COMPLETED$'; then
            WIFI_REASON="healthy_wpa_fallback"
            return 0
        fi
    fi

    if [ "$has_ipv4" -ne 1 ]; then
        WIFI_REASON="no_ipv4"
        return 1
    fi
    if [ "$has_default_route" -ne 1 ]; then
        WIFI_REASON="no_default_route"
        return 1
    fi
    WIFI_REASON="gateway_unreachable"
    return 1
}

remove_persisted_disabled() {
    [ -f "$WPA_CONF" ] || return 0
    if grep -q '^[[:space:]]*disabled=1[[:space:]]*$' "$WPA_CONF"; then
        if [ ! -f /data/local/wpa_supplicant.conf.before-wifi-recovery ]; then
            cp "$WPA_CONF" /data/local/wpa_supplicant.conf.before-wifi-recovery
            chmod 600 /data/local/wpa_supplicant.conf.before-wifi-recovery
        fi
        sed -i '/^[[:space:]]*disabled=1[[:space:]]*$/d' "$WPA_CONF"
        chmod 660 "$WPA_CONF"
        chown system:wifi "$WPA_CONF"
        log "永続化された disabled=1 を除去しました"
        $WPA_CLI reconfigure >> "$LOG" 2>&1
        sleep 5
    fi
}

recover_wifi() {
    attempt="$1"
    log "Wi-Fi復旧を実行します: attempt=$attempt reason=$WIFI_REASON"
    set_status "recovering" "attempt_$attempt"

    remove_persisted_disabled
    /system/bin/ifconfig wlan0 up >> "$LOG" 2>&1
    $WPA_CLI enable_network all >> "$LOG" 2>&1
    $WPA_CLI reassociate >> "$LOG" 2>&1
}

log "Wi-Fi自己復旧処理を開始します"
set_status "startup_grace" "waiting"
sleep "$STARTUP_GRACE_SEC"

failure_started_at=0
was_unhealthy=0

while true; do
    if wifi_is_healthy; then
        if [ "$was_unhealthy" -eq 1 ]; then
            log "Wi-Fi接続が正常になりました"
        fi
        failure_started_at=0
        was_unhealthy=0
        set_status "healthy" "connected"
        sleep "$CHECK_INTERVAL_SEC"
        continue
    fi

    now="$(date +%s)"
    if [ "$was_unhealthy" -eq 0 ]; then
        failure_started_at="$now"
        log "Wi-Fi異常を検出しました: reason=$WIFI_REASON"
    fi
    was_unhealthy=1
    failure_elapsed=$((now - failure_started_at))
    set_status "waiting" "${WIFI_REASON}_${failure_elapsed}s_of_${FAILURE_TRIGGER_SEC}s"

    if [ "$failure_elapsed" -lt "$FAILURE_TRIGGER_SEC" ]; then
        sleep "$CHECK_INTERVAL_SEC"
        continue
    fi

    attempt=1
    recovered=0
    while [ "$attempt" -le "$MAX_RECOVERY_ATTEMPTS" ]; do
        recover_wifi "$attempt"
        sleep "$RECOVERY_WAIT_SEC"
        if wifi_is_healthy; then
            log "Wi-Fi自己復旧に成功しました: attempt=$attempt"
            set_status "healthy" "recovered"
            failure_started_at=0
            was_unhealthy=0
            recovered=1
            break
        fi
        log "Wi-Fi復旧後も接続できません: attempt=$attempt reason=$WIFI_REASON"
        attempt=$((attempt + 1))
    done

    if [ "$recovered" -eq 0 ]; then
        log "Wi-Fi自己復旧を一時停止します: cooldown=${COOLDOWN_SEC}s"
        set_status "cooldown" "recovery_failed"
        sleep "$COOLDOWN_SEC"
        failure_started_at=0
    fi

    sleep "$CHECK_INTERVAL_SEC"
done
