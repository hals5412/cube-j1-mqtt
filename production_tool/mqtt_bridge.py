#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Wi-SUN Bルートのスマートメーター値をHome Assistant向けMQTTへ送信します。

Python 2.7標準ライブラリだけで動作する想定です。
"""

from __future__ import print_function

import os
import sys
import json
import time
import struct
import socket
import select
import binascii
import termios
import fcntl
import collections
import re
import threading

CONFIG_PATH = "/data/local/config.json"
LOG_PATH    = "/data/local/mqtt_bridge.log"
WISUN_INFO = {}

LED_R = "/sys/class/leds/red/brightness"
LED_G = "/sys/class/leds/green/brightness"
LED_B = "/sys/class/leds/blue/brightness"

def led_rgb(r, g, b):
    for path, val in ((LED_R, r), (LED_G, g), (LED_B, b)):
        try:
            with open(path, 'w') as f:
                f.write(str(val) + '\n')
        except Exception:
            pass

def led_read():
    result = []
    for path in (LED_R, LED_G, LED_B):
        try:
            with open(path) as f:
                result.append(int(f.read().strip()))
        except Exception:
            result.append(0)
    return tuple(result)

_log_file = None

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[{}] {}\n".format(ts, msg)
    global _log_file
    if _log_file:
        try:
            _log_file.write(line)
            _log_file.flush()
        except Exception:
            pass
    else:
        sys.stderr.write(line)
        sys.stderr.flush()

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# シリアルポート制御
# ---------------------------------------------------------------------------

def open_serial(port, baud=115200):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)

    attrs = list(termios.tcgetattr(fd))
    iflag, oflag, cflag, lflag = attrs[0], attrs[1], attrs[2], attrs[3]

    # BP35C0と安定してやり取りするためraw入力にします。
    iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK |
               termios.ISTRIP | termios.INLCR  | termios.IGNCR  |
               termios.ICRNL  | termios.IXON)
    oflag &= ~termios.OPOST
    cflag &= ~(termios.CSIZE | termios.PARENB)
    cflag |=  termios.CS8 | termios.CREAD | termios.CLOCAL
    lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
               termios.ISIG | termios.IEXTEN)

    baud_map = {
        9600:   termios.B9600,
        19200:  termios.B19200,
        38400:  termios.B38400,
        57600:  termios.B57600,
        115200: termios.B115200,
    }
    baud_const = baud_map.get(baud, termios.B115200)

    cc = attrs[6]
    # Cube J1上のPython 2.7ではattrs[6]がintリストで返るため、同じ型のまま戻します。
    if isinstance(cc, list):
        cc_list = list(cc)
        cc_list[termios.VMIN]  = 1
        cc_list[termios.VTIME] = 0
        attrs[6] = cc_list
    else:
        # 手元PCなど別環境での確認用経路です。
        cc_arr = bytearray(cc)
        cc_arr[termios.VMIN]  = 1
        cc_arr[termios.VTIME] = 0
        attrs[6] = bytes(cc_arr)

    attrs[0], attrs[1], attrs[2], attrs[3] = iflag, oflag, cflag, lflag
    attrs[4] = baud_const
    attrs[5] = baud_const

    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd

def serial_write(fd, data):
    if isinstance(data, bytes):
        os.write(fd, data)
    else:
        os.write(fd, data.encode("ascii"))

def serial_readline(fd, timeout=10):
    """CRLF終端の1行を読みます。タイムアウト時はNoneを返します。"""
    buf = b""
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        r, _, _ = select.select([fd], [], [], min(remaining, 0.5))
        if not r:
            continue
        ch = os.read(fd, 1)
        if not ch:
            continue
        buf += ch
        if buf.endswith(b"\r\n"):
            return buf[:-2].decode("ascii", errors="replace")
    return buf.decode("ascii", errors="replace") if buf else None

def _led_blink(stop_event, colors, interval=0.2):
    i = 0
    while not stop_event.is_set():
        led_rgb(*colors[i % len(colors)])
        i += 1
        stop_event.wait(interval)

def skcommand(fd, cmd, timeout=10):
    """SKSTACKコマンドを1つ送り、OK/FAILまでの応答行を返します。"""
    orig_led = led_read()
    stop_event = threading.Event()
    t = threading.Thread(target=_led_blink,
                         args=(stop_event, [(0, 255, 0), (0, 0, 255)]))
    t.daemon = True
    t.start()

    serial_write(fd, cmd + "\r\n")
    lines = []
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            line = serial_readline(fd, timeout=max(0.5, deadline - time.time()))
            if line is None:
                break
            lines.append(line)
            if line in ("OK", ) or line.startswith("FAIL"):
                break
    finally:
        stop_event.set()
        t.join(timeout=1)
        led_rgb(*orig_led)
    return lines

# ---------------------------------------------------------------------------
# スキャン設定
# ---------------------------------------------------------------------------

SCAN_DURATION_BASE = 4
SCAN_RETRY_LIMIT = 10

# ---------------------------------------------------------------------------
# SKSTACK-IP / Wi-SUN Bルート接続
# ---------------------------------------------------------------------------

def skscan(fd):
    """アクティブスキャンを行い、LQIが最も良いPAN情報を返します。"""
    duration = SCAN_DURATION_BASE
    
    while duration <= SCAN_RETRY_LIMIT:
        # 前回のコマンドやスキャンで残った行を捨てます。
        termios.tcflush(fd, termios.TCIFLUSH)

        log("SKSCAN try duration={}".format(duration))
        # BP35C0形式のスキャンコマンドです。
        serial_write(fd, "SKSCAN 2 FFFFFFFF {} 0\r\n".format(duration))

        pan_list  = []
        current   = {}
        scan_done = False
        deadline  = time.time() + duration
        while time.time() < deadline:
            line = serial_readline(fd, timeout=2)
            if line is None:
                continue
            if line.startswith("EVENT 20"):
                if current:
                    pan_list.append(current)
                current = {}
            elif line.startswith("EVENT 22"):
                if current:
                    pan_list.append(current)
                scan_done = True
                break
            elif ":" in line and not line.startswith("EVENT"):
                key, _, val = line.strip().partition(":")
                current[key.strip()] = val.strip()

        if pan_list:
            log("SKSCAN found {} PAN(s), selecting best LQI".format(len(pan_list)))
            pan_list.sort(key=lambda p: int(p.get("LQI", "0"), 16), reverse=True)
            return pan_list[0]

        log("SKSCAN no PAN found, retrying with longer duration")
        duration += 1

    return {}

def skll64(fd, mac):
    """MACアドレスをIPv6リンクローカルアドレスへ変換します。"""
    serial_write(fd, "SKLL64 {}\r\n".format(mac))
    deadline = time.time() + 10
    while time.time() < deadline:
        line = serial_readline(fd, timeout=2)
        if not line:
            continue
        # エコーや空行は読み飛ばします。
        if line.startswith("SKLL64") or line.strip() == "":
            continue
        # IPv6らしい文字列だけを取り出します。
        m = re.search(r'([0-9A-Fa-f:]{15,})', line)
        if not m:
            continue
        candidate = m.group(1)
        # inet_ptonでIPv6として妥当か確認します。
        try:
            socket.inet_pton(socket.AF_INET6, candidate)
            return candidate
        except Exception:
            # IPv6として不正なら、次の応答を待ちます。
            log("skll64: received candidate but validation failed: {}".format(candidate))
            continue
    return None

def wisun_connect(fd, br_id, br_pwd):
    """Wi-SUN Bルートへ接続し、スマートメーターのIPv6アドレスを返します。"""
    global WISUN_INFO
    log("SKRESET")
    skcommand(fd, "SKRESET", timeout=5)
    time.sleep(1)

    log("SKSETPWD")
    skcommand(fd, "SKSETPWD C {}".format(br_pwd))

    log("SKSETRBID")
    skcommand(fd, "SKSETRBID {}".format(br_id))

    # ERXUDPのpayloadをASCII hex形式に固定します。
    skcommand(fd, "WOPT 1")

    log("SKSCAN (may take up to 60s)")
    pan = skscan(fd)
    if not pan.get("Channel") or not pan.get("Pan ID") or not pan.get("Addr"):
        raise RuntimeError("SKSCAN: no PAN found ({})".format(pan))

    channel = pan["Channel"]
    pan_id  = pan["Pan ID"]
    mac     = pan["Addr"]
    WISUN_INFO = {
        "channel": channel,
        "pan_id": pan_id,
        "lqi": pan.get("LQI", ""),
    }
    log("PAN found: ch={} panId={} mac={}".format(channel, pan_id, mac))

    ipv6 = skll64(fd, mac)
    if not ipv6:
        raise RuntimeError("SKLL64 failed")
    log("Meter IPv6: {}".format(ipv6))
    WISUN_INFO["meter_ipv6"] = ipv6

    skcommand(fd, "SKSREG S2 {}".format(channel))
    skcommand(fd, "SKSREG S3 {}".format(pan_id))

    log("SKJOIN {}".format(ipv6))
    serial_write(fd, "SKJOIN {}\r\n".format(ipv6))

    orig_led = led_read()
    stop_event = threading.Event()
    t = threading.Thread(target=_led_blink,
                         args=(stop_event, [(0, 255, 0), (0, 0, 255)]))
    t.daemon = True
    t.start()
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            line = serial_readline(fd, timeout=2)
            if line is None:
                continue
            if "EVENT 25" in line:
                log("SKJOIN: connected")
                return ipv6
            if "EVENT 24" in line:
                raise RuntimeError("SKJOIN: PANA authentication failed (EVENT 24)")
    finally:
        stop_event.set()
        t.join(timeout=1)
        led_rgb(*orig_led)

    raise RuntimeError("SKJOIN: timeout")

# ---------------------------------------------------------------------------
# ECHONET Liteフレーム生成 / 解析
# ---------------------------------------------------------------------------

EPCS = [0xD3, 0xE1, 0xE7, 0xE0, 0xE3, 0xE8]

def build_el_get(tid, epcs):
    frame = bytearray()
    frame += b"\x10\x81"                     # EHD1, EHD2
    frame += struct.pack(">H", tid & 0xFFFF) # TID
    frame += b"\x05\xFF\x01"                 # SEOJ: コントローラー
    frame += b"\x02\x88\x01"                 # DEOJ: 低圧スマート電力量メーター
    frame += b"\x62"                         # ESV: Get
    frame += struct.pack("B", len(epcs))     # OPC
    for epc in epcs:
        frame += struct.pack("BB", epc, 0)   # EPC, PDC=0
    return bytes(frame)

def parse_el_response(data):
    """EPC番号をキーにしたプロパティ辞書を返します。"""
    if len(data) < 12:
        return {}
    esv = data[10] if isinstance(data[10], int) else ord(data[10])
    opc = data[11] if isinstance(data[11], int) else ord(data[11])
    # Get_ResまたはGet_SNAを受け付けます。
    if esv not in (0x72, 0x52):
        return {}
    result = {}
    pos = 12
    for _ in range(opc):
        if pos + 2 > len(data):
            break
        epc = data[pos] if isinstance(data[pos], int) else ord(data[pos])
        pdc = data[pos+1] if isinstance(data[pos+1], int) else ord(data[pos+1])
        pos += 2
        if pos + pdc > len(data):
            break
        result[epc] = bytearray(data[pos:pos+pdc])
        pos += pdc
    return result

def decode_measurements(props):
    result = {}

    # D3: 係数
    if 0xD3 in props and len(props[0xD3]) >= 4:
        result["coefficient"] = struct.unpack(">I", bytes(props[0xD3][:4]))[0]

    # E1: 積算電力量単位
    if 0xE1 in props and len(props[0xE1]) >= 1:
        unit_byte = props[0xE1][0]
        unit_map = {0x00: 1.0, 0x01: 0.1,  0x02: 0.01,   0x03: 0.001, 0x04: 0.0001,
                    0x0A: 10.0, 0x0B: 100.0, 0x0C: 1000.0, 0x0D: 10000.0}
        result["unit_kwh"] = unit_map.get(unit_byte, 1.0)

    # E7: 瞬時電力
    if 0xE7 in props and len(props[0xE7]) >= 4:
        result["power_w"] = struct.unpack(">i", bytes(props[0xE7][:4]))[0]

    # E0: 積算電力量 正方向
    if 0xE0 in props and len(props[0xE0]) >= 4:
        result["energy_forward_raw"] = struct.unpack(">I", bytes(props[0xE0][:4]))[0]

    # E3: 積算電力量 逆方向
    if 0xE3 in props and len(props[0xE3]) >= 4:
        result["energy_reverse_raw"] = struct.unpack(">I", bytes(props[0xE3][:4]))[0]

    # E8: 瞬時電流 R相/T相
    if 0xE8 in props and len(props[0xE8]) >= 4:
        r, t = struct.unpack(">hh", bytes(props[0xE8][:4]))
        result["current_r_a"] = r / 10.0
        result["current_t_a"] = t / 10.0

    return result

def apply_energy_scale(measurements, coeff, unit_kwh):
    c = measurements.get("coefficient", coeff)
    u = measurements.get("unit_kwh", unit_kwh)
    if "energy_forward_raw" in measurements:
        measurements["energy_forward_kwh"] = measurements["energy_forward_raw"] * c * u
    if "energy_reverse_raw" in measurements:
        measurements["energy_reverse_kwh"] = measurements["energy_reverse_raw"] * c * u
    return measurements

# ---------------------------------------------------------------------------
# SKSENDTOでECHONET Lite Getを送信
# ---------------------------------------------------------------------------

def send_el_get(fd, ipv6, tid):
    frame = build_el_get(tid, EPCS)
    # SKSENDTOは4桁hexのpayload長と、raw data後のCRLFを要求します。
    cmd = "SKSENDTO 1 {} 0E1A 1 0 {:04X} ".format(ipv6, len(frame))
    serial_write(fd, cmd)
    serial_write(fd, frame)
    serial_write(fd, b"\r\n")

def read_erxudp(fd, timeout=15):
    """ERXUDPを待ち、payloadをbytearrayで返します。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = serial_readline(fd, timeout=max(0.5, deadline - time.time()))
        if line is None:
            continue
        if line.startswith("ERXUDP"):
            parts = line.split()
            # 末尾側のフィールドは安定しています。
            if len(parts) >= 10:
                hex_data = parts[-1].strip()
                if not hex_data.startswith("1081"):
                    continue
                try:
                    return bytearray(binascii.unhexlify(hex_data))
                except Exception as e:
                    log("ERXUDP hex decode error: {}".format(e))
    return None

# ---------------------------------------------------------------------------
# 最小限のMQTT 3.1.1クライアント
# ---------------------------------------------------------------------------

def _encode_remaining(n):
    buf = b""
    while True:
        byte = n % 128
        n //= 128
        if n > 0:
            byte |= 0x80
        buf += struct.pack("B", byte)
        if n == 0:
            break
    return buf

def _encode_str(s):
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b

class MQTTClient(object):
    def __init__(self, host, port, client_id, username=None, password=None,
                 will_topic=None, will_payload=None, will_retain=False,
                 keepalive=300):
        self.host      = host
        self.port      = port
        self.client_id = client_id
        self.username  = username
        self.password  = password
        self.will_topic = will_topic
        self.will_payload = will_payload
        self.will_retain = will_retain
        self.keepalive = keepalive
        self.sock      = None
        self._out_queue = collections.deque()
        self.reconnect_count = 0

    def connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(30)
        # 利用可能な環境ではTCP keepaliveを有効化します。
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # 環境依存のTCP keepalive設定です。
            for opt_name, opt_val in (('TCP_KEEPIDLE', 60), ('TCP_KEEPINTVL', 10), ('TCP_KEEPCNT', 3)):
                if hasattr(socket, opt_name):
                    try:
                        s.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt_name), opt_val)
                    except Exception:
                        pass
        except Exception:
            pass

        s.connect((self.host, self.port))

        flags = 0x02
        if self.username: flags |= 0x80
        if self.password: flags |= 0x40
        if self.will_topic:
            flags |= 0x04
            if self.will_retain:
                flags |= 0x20

        var_hdr = (b"\x00\x04MQTT"
                   + b"\x04"
                   + struct.pack("B", flags)
                   + struct.pack(">H", int(self.keepalive)))

        payload = _encode_str(self.client_id)
        if self.will_topic:
            payload += _encode_str(self.will_topic)
            payload += _encode_str(self.will_payload or "")
        if self.username: payload += _encode_str(self.username)
        if self.password: payload += _encode_str(self.password)

        remaining = var_hdr + payload
        pkt = b"\x10" + _encode_remaining(len(remaining)) + remaining
        s.sendall(pkt)

        # CONNACKを読みます。
        s.settimeout(10)
        ack = b""
        while len(ack) < 4:
            chunk = s.recv(4 - len(ack))
            if not chunk:
                break
            ack += chunk
        s.settimeout(None)

        if len(ack) < 4 or (ack[0] if isinstance(ack[0], int) else ord(ack[0])) != 0x20:
            raise RuntimeError("MQTT: bad CONNACK ({})".format(binascii.hexlify(ack)))
        rc = ack[3] if isinstance(ack[3], int) else ord(ack[3])
        if rc != 0:
            raise RuntimeError("MQTT: connection refused code {}".format(rc))

        self.sock = s
        log("MQTT connected to {}:{}".format(self.host, self.port))

        # 再接続前に積んだメッセージがあれば送ります。
        try:
            self._flush_queue()
        except Exception as e:
            log("MQTT flush queue error: {}".format(e))

    def _make_pkt(self, topic, payload, retain=False):
        if isinstance(payload, dict):
            payload = json.dumps(payload, separators=(",", ":"))
        topic_b = topic.encode("utf-8")
        payload_b = payload.encode("utf-8") if isinstance(payload, str) else payload
        fixed = 0x30 | (0x01 if retain else 0x00)
        var_hdr = struct.pack(">H", len(topic_b)) + topic_b
        remaining = var_hdr + payload_b
        return struct.pack("B", fixed) + _encode_remaining(len(remaining)) + remaining

    def publish(self, topic, payload, retain=False):
        pkt = self._make_pkt(topic, payload, retain)
        try:
            if not self.sock:
                raise RuntimeError("No MQTT socket")
            self.sock.sendall(pkt)
            return
        except Exception as e:
            log("MQTT publish error: {}".format(e))
            # 再接続して再送します。
            try:
                self._reconnect()
            except Exception as e2:
                log("MQTT reconnect failed after publish error: {}".format(e2))
                # 送れなかったメッセージは次回接続時に送ります。
                try:
                    self._out_queue.append((topic, payload, retain))
                except Exception:
                    pass
                return

            try:
                self.sock.sendall(pkt)
                return
            except Exception as e3:
                log("MQTT publish retry failed: {}".format(e3))
                try:
                    self._out_queue.append((topic, payload, retain))
                except Exception:
                    pass

    def _flush_queue(self):
        while self._out_queue and self.sock:
            topic, payload, retain = self._out_queue[0]
            try:
                pkt = self._make_pkt(topic, payload, retain)
                self.sock.sendall(pkt)
                self._out_queue.popleft()
            except Exception as e:
                log("MQTT queued publish failed: {}".format(e))
                break

    def ping(self):
        try:
            self.sock.sendall(b"\xC0\x00")
        except Exception as e:
            log("MQTT ping error: {}".format(e))
            self._reconnect()
            return
        # PINGRESPを待ちます。
        try:
            r, _, _ = select.select([self.sock], [], [], 5)
            if r:
                resp = self.sock.recv(2)
                if not resp:
                    log("MQTT ping: no response (empty)")
                    self._reconnect()
                elif len(resp) < 2:
                    log("MQTT ping: incomplete response (len={})".format(len(resp)))
                    self._reconnect()
                else:
                    first_byte = resp[0] if isinstance(resp[0], int) else ord(resp[0])
                    if first_byte != 0xD0:
                        log("MQTT ping: unexpected response first_byte=0x{:02X}".format(first_byte))
                        self._reconnect()
            else:
                log("MQTT ping: timeout (no data within 5s)")
                self._reconnect()
        except Exception as e:
            log("MQTT ping recv error: {}".format(e))
            self._reconnect()

    def _reconnect(self):
        log("MQTT reconnecting …")
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self.reconnect_count += 1
        while True:
            try:
                self.connect()
                return
            except Exception as e:
                log("MQTT reconnect failed: {} - retry in 15s".format(e))
                time.sleep(15)

# ---------------------------------------------------------------------------
# Home Assistant MQTT自動検出
# ---------------------------------------------------------------------------

SENSOR_DEFS = [
    ("power",          "瞬時電力",              "W",   "power",   "measurement", None),
    ("energy_forward", "積算電力量 正方向",     "kWh", "energy",  "total_increasing", None),
    ("energy_reverse", "積算電力量 逆方向",     "kWh", "energy",  "total_increasing", None),
    ("current_r",      "瞬時電流 R相",          "A",   "current", "measurement", None),
    ("current_t",      "瞬時電流 T相",          "A",   "current", "measurement", None),
]

DIAGNOSTIC_SENSOR_DEFS = [
    ("last_seen", "最終取得時刻", None, None, None, "diagnostic"),
    ("wisun_status", "Wi-SUN状態", None, None, None, "diagnostic"),
    ("lqi", "Wi-SUN LQI", None, None, None, "diagnostic"),
    ("channel", "Wi-SUNチャンネル", None, None, None, "diagnostic"),
    ("pan_id", "Wi-SUN PAN ID", None, None, None, "diagnostic"),
    ("meter_ipv6", "スマートメーターIPv6", None, None, None, "diagnostic"),
    ("uptime", "ブリッジ稼働時間", "s", "duration", "measurement", "diagnostic"),
    ("error_count", "エラー回数", None, None, "total_increasing", "diagnostic"),
    ("last_error", "最終エラー", None, None, None, "diagnostic"),
    ("mqtt_reconnect_count", "MQTT再接続回数", None, None, "total_increasing", "diagnostic"),
    ("wisun_reconnect_count", "Wi-SUN再接続回数", None, None, "total_increasing", "diagnostic"),
    ("coefficient", "積算電力量係数", None, None, "measurement", "diagnostic"),
    ("energy_unit", "積算電力量単位", "kWh", None, "measurement", "diagnostic"),
]

def iso_now():
    # Cube J1本体のタイムゾーン設定に依存せず、Home Assistant表示用にJSTで出します。
    return time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.gmtime(time.time() + 9 * 60 * 60))

def publish_ha_discovery(mqtt, device_id, display_name, poll_interval):
    device = {
        "identifiers": [device_id],
        "name":         display_name,
        "model":        "Cube J1",
        "manufacturer": "NextDrive",
    }
    base = "cubej/{}".format(device_id)
    availability_topic = "{}/status".format(base)
    measurement_ids = [s[0] for s in SENSOR_DEFS]
    for sid, name, unit, dev_class, state_class, entity_category in SENSOR_DEFS + DIAGNOSTIC_SENSOR_DEFS:
        topic  = "homeassistant/sensor/{}/{}/config".format(device_id, sid)
        config = {
            "name":               name,
            "unique_id":          "{}_{}".format(device_id, sid),
            "state_topic":        "{}/{}".format(base, sid) if sid in measurement_ids else "{}/diagnostic/{}".format(base, sid),
            "availability_topic": availability_topic,
            "payload_available":  "online",
            "payload_not_available": "offline",
            "expire_after":       int(poll_interval) * 3,
            "device":             device,
        }
        if unit:
            config["unit_of_measurement"] = unit
        if dev_class:
            config["device_class"] = dev_class
        if state_class:
            config["state_class"] = state_class
        if entity_category:
            config["entity_category"] = entity_category
        mqtt.publish(topic, config, retain=True)
        log("HA discovery: {}".format(topic))

def publish_status(mqtt, device_id, status):
    mqtt.publish("cubej/{}/status".format(device_id), status, retain=True)

def publish_measurements(mqtt, device_id, m):
    base = "cubej/{}".format(device_id)
    if "power_w" in m:
        mqtt.publish("{}/power".format(base), str(m["power_w"]))
    if "energy_forward_kwh" in m:
        mqtt.publish("{}/energy_forward".format(base), "{:.3f}".format(m["energy_forward_kwh"]))
    if "energy_reverse_kwh" in m:
        mqtt.publish("{}/energy_reverse".format(base), "{:.3f}".format(m["energy_reverse_kwh"]))
    if "current_r_a" in m:
        mqtt.publish("{}/current_r".format(base), "{:.1f}".format(m["current_r_a"]))
    if "current_t_a" in m:
        mqtt.publish("{}/current_t".format(base), "{:.1f}".format(m["current_t_a"]))

def publish_diagnostic(mqtt, device_id, data):
    base = "cubej/{}/diagnostic".format(device_id)
    publish_status(mqtt, device_id, "online")
    for key, value in data.items():
        if value is None:
            continue
        mqtt.publish("{}/{}".format(base, key), str(value))

# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def main():
    global _log_file
    try:
        _log_file = open(LOG_PATH, "a")
    except Exception:
        pass

    cfg           = load_config()
    br_id         = cfg["br_id"]
    br_pwd        = cfg["br_pwd"]
    ha_host       = cfg["mqtt_host"]
    ha_port       = int(cfg.get("mqtt_port", 1883))
    ha_user       = cfg.get("mqtt_user", "")
    ha_pass       = cfg.get("mqtt_pass", "")
    device_id     = cfg.get("device_id", "cubej1")
    mqtt_client_id = cfg.get("mqtt_client_id", device_id)
    display_name  = cfg.get("display_name", "Cube J1 Smart Meter")
    serial_port   = cfg.get("serial_port", "/dev/ttyS1")
    poll_interval = int(cfg.get("poll_interval", 60))
    mqtt_keepalive = int(cfg.get("mqtt_keepalive", 300))
    start_time    = time.time()
    error_count   = 0
    last_error    = ""
    wisun_reconnect_count = 0

    log("=== mqtt_bridge start device_id={} ===".format(device_id))

    base = "cubej/{}".format(device_id)
    mqtt = MQTTClient(ha_host, ha_port, mqtt_client_id,
                      username=ha_user, password=ha_pass,
                      will_topic="{}/status".format(base),
                      will_payload="offline",
                      will_retain=True,
                      keepalive=mqtt_keepalive)
    while True:
        try:
            mqtt.connect()
            publish_status(mqtt, device_id, "online")
            break
        except Exception as e:
            log("MQTT connect failed: {} - retry in 15s".format(e))
            time.sleep(15)

    publish_ha_discovery(mqtt, device_id, display_name, poll_interval)
    publish_status(mqtt, device_id, "online")
    publish_diagnostic(mqtt, device_id, {
        "wisun_status": "starting",
        "error_count": error_count,
        "last_error": last_error,
        "mqtt_reconnect_count": mqtt.reconnect_count,
        "wisun_reconnect_count": wisun_reconnect_count,
    })

    # シリアルポートを開きます。
    log("Opening serial {}".format(serial_port))
    fd = None
    while True:
        try:
            fd = open_serial(serial_port)
            break
        except Exception as e:
            log("Serial open failed: {} - retry in 10s".format(e))
            time.sleep(10)

    # Wi-SUN Bルートへ接続します。
    ipv6 = None
    while True:
        try:
            ipv6 = wisun_connect(fd, br_id, br_pwd)
            publish_diagnostic(mqtt, device_id, {
                "wisun_status": "connected",
                "channel": WISUN_INFO.get("channel"),
                "pan_id": WISUN_INFO.get("pan_id"),
                "lqi": WISUN_INFO.get("lqi"),
                "meter_ipv6": ipv6,
            })
            break
        except Exception as e:
            error_count += 1
            last_error = "Wi-SUN join failed: {}".format(e)
            log("{} - retry in 60s".format(last_error))
            publish_diagnostic(mqtt, device_id, {
                "wisun_status": "join_failed",
                "error_count": error_count,
                "last_error": last_error,
            })
            time.sleep(60)

    log("Meter connected at {}".format(ipv6))

    tid       = 1
    coeff     = 1
    unit_kwh  = 1.0
    last_ping = time.time()

    while True:
        try:
            orig_led = led_read()
            led_rgb(0, 0, 255)
            try:
                send_el_get(fd, ipv6, tid)
                tid = (tid + 1) & 0xFFFF
                data = read_erxudp(fd, timeout=15)
                if data:
                    props = parse_el_response(data)
                    m     = decode_measurements(props)
                    m     = apply_energy_scale(m, coeff, unit_kwh)
                    if "coefficient" in m:
                        coeff = m["coefficient"]
                    if "unit_kwh" in m:
                        unit_kwh = m["unit_kwh"]
                    log("Measurements: {}".format(
                        {k: v for k, v in m.items()
                         if k in ("power_w", "energy_forward_kwh", "energy_reverse_kwh",
                                   "current_r_a", "current_t_a")}))
                    publish_measurements(mqtt, device_id, m)
                    publish_status(mqtt, device_id, "online")
                    publish_diagnostic(mqtt, device_id, {
                        "last_seen": iso_now(),
                        "wisun_status": "connected",
                        "channel": WISUN_INFO.get("channel"),
                        "pan_id": WISUN_INFO.get("pan_id"),
                        "lqi": WISUN_INFO.get("lqi"),
                        "meter_ipv6": ipv6,
                        "uptime": int(time.time() - start_time),
                        "error_count": error_count,
                        "last_error": last_error,
                        "mqtt_reconnect_count": mqtt.reconnect_count,
                        "wisun_reconnect_count": wisun_reconnect_count,
                        "coefficient": coeff,
                        "energy_unit": unit_kwh,
                    })
                else:
                    log("No ERXUDP response (timeout)")
                    error_count += 1
                    last_error = "No ERXUDP response"
                    publish_diagnostic(mqtt, device_id, {
                        "wisun_status": "timeout",
                        "uptime": int(time.time() - start_time),
                        "error_count": error_count,
                        "last_error": last_error,
                    })
            finally:
                led_rgb(*orig_led)

            if time.time() - last_ping > 50:
                mqtt.ping()
                last_ping = time.time()

            time.sleep(poll_interval)

        except Exception as e:
            error_count += 1
            last_error = "Main loop error: {}".format(e)
            log("{} - reconnecting Wi-SUN in 30s".format(last_error))
            publish_diagnostic(mqtt, device_id, {
                "wisun_status": "reconnecting",
                "error_count": error_count,
                "last_error": last_error,
            })
            time.sleep(30)
            try:
                ipv6 = wisun_connect(fd, br_id, br_pwd)
                wisun_reconnect_count += 1
                log("Wi-SUN reconnected at {}".format(ipv6))
                publish_diagnostic(mqtt, device_id, {
                    "wisun_status": "connected",
                    "wisun_reconnect_count": wisun_reconnect_count,
                    "channel": WISUN_INFO.get("channel"),
                    "pan_id": WISUN_INFO.get("pan_id"),
                    "lqi": WISUN_INFO.get("lqi"),
                    "meter_ipv6": ipv6,
                })
            except Exception as e2:
                error_count += 1
                last_error = "Wi-SUN reconnect failed: {}".format(e2)
                log(last_error)
                publish_diagnostic(mqtt, device_id, {
                    "wisun_status": "reconnect_failed",
                    "error_count": error_count,
                    "last_error": last_error,
                })


if __name__ == "__main__":
    main()
