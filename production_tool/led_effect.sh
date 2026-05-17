#!/system/bin/sh
# Cube J1のRGB LEDをsysfs経由で制御します。
#
# 使い方:
#   led_effect rainbow [cycles] [step_deg] [delay_ms]
#   led_effect pulse   [color_name] [cycles]
#   led_effect blink   [color_name] [count]
#   led_effect set     <r> <g> <b>
#
# 各コマンドは実行前のLED状態を保存し、終了時に復元します。

LED_R=/sys/class/leds/red/brightness
LED_G=/sys/class/leds/green/brightness
LED_B=/sys/class/leds/blue/brightness

led_rgb() {
    echo "$1" > "$LED_R"
    echo "$2" > "$LED_G"
    echo "$3" > "$LED_B"
}

led_save() {
    orig_r=$(cat "$LED_R")
    orig_g=$(cat "$LED_G")
    orig_b=$(cat "$LED_B")
}

led_restore() {
    led_rgb "$orig_r" "$orig_g" "$orig_b"
}

# 整数演算でHSVをRGBへ変換します。
# 出力形式: R G B
hsv_to_rgb() {
    h=$1 s=$2 v=$3
    if [ "$s" -eq 0 ]; then
        printf '%d %d %d\n' "$v" "$v" "$v"
        return
    fi
    i=$((h / 60))
    f=$((h % 60))
    p=$(( v * (255 - s) / 255 ))
    q=$(( v * (255 - s * f / 60) / 255 ))
    t=$(( v * (255 - s * (60 - f) / 60) / 255 ))
    case $i in
        0) printf '%d %d %d\n' "$v" "$t" "$p" ;;
        1) printf '%d %d %d\n' "$q" "$v" "$p" ;;
        2) printf '%d %d %d\n' "$p" "$v" "$t" ;;
        3) printf '%d %d %d\n' "$p" "$q" "$v" ;;
        4) printf '%d %d %d\n' "$t" "$p" "$v" ;;
        *) printf '%d %d %d\n' "$v" "$p" "$q" ;;
    esac
}

cmd_rainbow() {
    cycles=${1:-3}
    step=${2:-5}      # 1フレームあたりの角度
    delay_ms=${3:-40} # 1フレームあたりの待機時間

    led_save

    total=$(( cycles * 360 / step ))
    i=0
    while [ $i -lt $total ]; do
        h=$(( (i * step) % 360 ))
        rgb=$(hsv_to_rgb "$h" 255 255)
        led_rgb $rgb
        usleep $(( delay_ms * 1000 ))
        i=$(( i + 1 ))
    done

    led_restore
}

cmd_pulse() {
    color=${1:-white}
    cycles=${2:-3}

    case "$color" in
        red)     br=255; bg=0;   bb=0   ;;
        green)   br=0;   bg=255; bb=0   ;;
        blue)    br=0;   bg=0;   bb=255 ;;
        cyan)    br=0;   bg=255; bb=255 ;;
        magenta) br=255; bg=0;   bb=255 ;;
        yellow)  br=255; bg=180; bb=0   ;;
        *)       br=255; bg=255; bb=255 ;;
    esac

    led_save

    for i in $(seq 1 "$cycles"); do
        v=0
        while [ $v -le 255 ]; do
            led_rgb $(( br * v / 255 )) $(( bg * v / 255 )) $(( bb * v / 255 ))
            usleep 20000
            v=$(( v + 5 ))
        done
        v=255
        while [ $v -ge 0 ]; do
            led_rgb $(( br * v / 255 )) $(( bg * v / 255 )) $(( bb * v / 255 ))
            usleep 20000
            v=$(( v - 5 ))
        done
    done

    led_restore
}

cmd_blink() {
    color=${1:-white}
    count=${2:-6}

    case "$color" in
        red)     br=255; bg=0;   bb=0   ;;
        green)   br=0;   bg=255; bb=0   ;;
        blue)    br=0;   bg=0;   bb=255 ;;
        cyan)    br=0;   bg=255; bb=255 ;;
        magenta) br=255; bg=0;   bb=255 ;;
        yellow)  br=255; bg=180; bb=0   ;;
        *)       br=255; bg=255; bb=255 ;;
    esac

    led_save

    for i in $(seq 1 "$count"); do
        led_rgb "$br" "$bg" "$bb"
        usleep 300000
        led_rgb 0 0 0
        usleep 300000
    done

    led_restore
}

case "${1:-rainbow}" in
    rainbow) shift; cmd_rainbow "$@" ;;
    pulse)   shift; cmd_pulse   "$@" ;;
    blink)   shift; cmd_blink   "$@" ;;
    set)     led_rgb "${2:-0}" "${3:-0}" "${4:-0}" ;;
    *)
        echo "使い方: led_effect {rainbow|pulse|blink|set} [引数...]" >&2
        exit 1
        ;;
esac
