#!/usr/bin/python
# -*- coding: utf-8 -*-
"""BP35C0シリアル確認と任意のMQTT送信を行うCube J1診断スクリプト。

Python 2.7標準ライブラリだけで動作します。USB上のproduction_toolから起動される想定です。
"""

from __future__ import print_function

import binascii
import json
import os
import select
import socket
import struct
import sys
import termios
import time

try:
    text_type = unicode
except NameError:
    text_type = str


def log(msg):
    print("[diag_check] {}".format(msg))


def env(name, default=""):
    value = os.environ.get(name)
    return default if value is None else value


def open_serial(port, baud=115200):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY)
    attrs = list(termios.tcgetattr(fd))
    iflag, oflag, cflag, lflag = attrs[0], attrs[1], attrs[2], attrs[3]
    iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK |
               termios.ISTRIP | termios.INLCR | termios.IGNCR |
               termios.ICRNL | termios.IXON)
    oflag &= ~termios.OPOST
    cflag &= ~(termios.CSIZE | termios.PARENB)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
    lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON |
               termios.ISIG | termios.IEXTEN)
    baud_const = getattr(termios, "B{}".format(baud), termios.B115200)
    cc = attrs[6]
    if isinstance(cc, list):
        cc_list = list(cc)
        cc_list[termios.VMIN] = 1
        cc_list[termios.VTIME] = 0
        attrs[6] = cc_list
    else:
        cc_arr = bytearray(cc)
        cc_arr[termios.VMIN] = 1
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


def readline(fd, timeout=5):
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        r, _, _ = select.select([fd], [], [], min(remaining, 0.5))
        if not r:
            continue
        ch = os.read(fd, 1)
        if not ch:
            continue
        buf += ch
        if buf.endswith(b"\r\n"):
            return buf[:-2].decode("ascii", "replace")
    if buf:
        return buf.decode("ascii", "replace")
    return None


def command(fd, cmd, timeout=8):
    log("serial > {}".format(cmd))
    serial_write(fd, cmd + "\r\n")
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = readline(fd, timeout=max(0.5, deadline - time.time()))
        if line is None:
            break
        lines.append(line)
        log("serial < {}".format(line))
        if line == "OK" or line.startswith("FAIL"):
            break
    return lines


def serial_diag():
    port = env("SERIAL_PORT", "/dev/ttyS1")
    run_scan = env("RUN_SKSCAN", "0") == "1"
    scan_duration = env("SKSCAN_DURATION", "4")
    log("シリアルポートを開きます: {}".format(port))
    fd = open_serial(port)
    try:
        command(fd, "SKVER", timeout=5)
        command(fd, "SKINFO", timeout=5)
        command(fd, "WOPT 1", timeout=5)
        if run_scan:
            log("SKSCANを開始します duration={}".format(scan_duration))
            termios.tcflush(fd, termios.TCIFLUSH)
            serial_write(fd, "SKSCAN 2 FFFFFFFF {} 0\r\n".format(scan_duration))
            deadline = time.time() + int(scan_duration) + 20
            while time.time() < deadline:
                line = readline(fd, timeout=2)
                if line is None:
                    continue
                log("scan < {}".format(line))
                if line.startswith("EVENT 22"):
                    log("スキャンが完了しました")
                    break
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def mqtt_encode_remaining(n):
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


def mqtt_encode_str(s):
    if isinstance(s, text_type):
        b = s.encode("utf-8")
    else:
        b = str(s).encode("utf-8")
    return struct.pack(">H", len(b)) + b


def byte_value(b):
    return b if isinstance(b, int) else ord(b)


def mqtt_publish(host, port, username, password, topic, payload):
    client_id = "cubej1_diag_{}".format(int(time.time()))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect((host, int(port)))
    flags = 0x02
    if username:
        flags |= 0x80
    if password:
        flags |= 0x40
    var_hdr = b"\x00\x04MQTT" + b"\x04" + struct.pack("B", flags) + b"\x00\x3C"
    body = mqtt_encode_str(client_id)
    if username:
        body += mqtt_encode_str(username)
    if password:
        body += mqtt_encode_str(password)
    pkt = b"\x10" + mqtt_encode_remaining(len(var_hdr + body)) + var_hdr + body
    sock.sendall(pkt)
    ack = sock.recv(4)
    log("mqtt CONNACK {}".format(binascii.hexlify(ack)))
    if len(ack) < 4 or byte_value(ack[0]) != 0x20 or byte_value(ack[3]) != 0:
        raise RuntimeError("MQTT接続に失敗しました: {}".format(binascii.hexlify(ack)))
    topic_b = topic.encode("utf-8")
    payload_b = payload.encode("utf-8")
    msg = struct.pack(">H", len(topic_b)) + topic_b + payload_b
    sock.sendall(b"\x30" + mqtt_encode_remaining(len(msg)) + msg)
    sock.sendall(b"\xE0\x00")
    sock.close()


def mqtt_diag():
    host = env("MQTT_HOST", "")
    if not host:
        raise RuntimeError("MQTT_HOSTが空です")
    payload = {
        "device_id": env("DEVICE_ID", "cubej1_diag"),
        "status": "diagnostic",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    topic = env("MQTT_TOPIC", "cubej/diagnostic/status")
    log("MQTTテスト送信を実行します: topic={} host={}:{}".format(topic, host, env("MQTT_PORT", "1883")))
    mqtt_publish(host, int(env("MQTT_PORT", "1883")),
                 env("MQTT_USER", ""), env("MQTT_PASS", ""),
                 topic, json.dumps(payload, separators=(",", ":")))
    log("MQTT送信が完了しました")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("使い方: diag_check.py serial|mqtt")
    if sys.argv[1] == "serial":
        serial_diag()
    elif sys.argv[1] == "mqtt":
        mqtt_diag()
    else:
        raise SystemExit("不明なモードです: {}".format(sys.argv[1]))


if __name__ == "__main__":
    main()
