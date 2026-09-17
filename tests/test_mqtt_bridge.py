#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MQTTブリッジの副作用が小さい制御処理を確認します。"""

from __future__ import print_function

import os
import sys
import struct
import unittest

# mqtt_bridge runs on Linux/Android and imports POSIX-only modules.
# For unit tests on Windows, provide only the small surface needed by tests.
if os.name == "nt":
    import types

    termios_stub = types.ModuleType("termios")
    termios_stub.TCIFLUSH = 0
    termios_stub.tcflush = lambda _fd, _mode: None
    sys.modules.setdefault("termios", termios_stub)

    sys.modules.setdefault("fcntl", types.ModuleType("fcntl"))


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "production_tool"))

import mqtt_bridge as bridge


class PollControlTests(unittest.TestCase):
    def test_poll_interval_has_30_second_floor(self):
        self.assertEqual(bridge.normalize_poll_interval(10), 30)
        self.assertEqual(bridge.normalize_poll_interval("60"), 60)

    def test_next_poll_sleep_uses_previous_start_time(self):
        self.assertEqual(bridge.compute_next_poll_sleep(100, 115, 60), 45)
        self.assertEqual(bridge.compute_next_poll_sleep(100, 170, 60), 0)

    def test_rejoin_uses_normal_threshold_without_session_expiry(self):
        self.assertFalse(bridge.should_force_wisun_rejoin(2, False))
        self.assertTrue(bridge.should_force_wisun_rejoin(3, False))

    def test_rejoin_is_immediate_after_session_expiry_timeout(self):
        self.assertTrue(bridge.should_force_wisun_rejoin(1, True))


class SkscanControlTests(unittest.TestCase):
    def setUp(self):
        self.original_serial_write = bridge.serial_write
        self.original_serial_readline = bridge.serial_readline
        self.original_tcflush = bridge.termios.tcflush
        self.original_scan_retry_limit = bridge.SCAN_RETRY_LIMIT
        self.original_scan_timeout = bridge.scan_timeout_for_duration
        self.original_time = bridge.time.time
        self.writes = []
        bridge.serial_write = lambda _fd, value: self.writes.append(value)
        bridge.termios.tcflush = lambda _fd, _mode: None

    def tearDown(self):
        bridge.serial_write = self.original_serial_write
        bridge.serial_readline = self.original_serial_readline
        bridge.termios.tcflush = self.original_tcflush
        bridge.SCAN_RETRY_LIMIT = self.original_scan_retry_limit
        bridge.scan_timeout_for_duration = self.original_scan_timeout
        bridge.time.time = self.original_time

    def test_scan_timeout_accounts_for_duration_not_seconds(self):
        self.assertGreater(bridge.scan_timeout_for_duration(6), 6)
        self.assertGreater(bridge.scan_timeout_for_duration(7),
                           bridge.scan_timeout_for_duration(6))

    def test_event22_completion_prefers_matching_pair_id(self):
        lines = [
            "OK",
            "EVENT 20 FE80::1 0",
            "EPANDESC",
            "  Channel:21",
            "  Pan ID:1111",
            "  Addr:AAAAAAAAAAAAAAAA",
            "  LQI:F0",
            "  PairID:DEADBEEF",
            "EVENT 20 FE80::1 0",
            "EPANDESC",
            "  Channel:22",
            "  Pan ID:2222",
            "  Addr:BBBBBBBBBBBBBBBB",
            "  LQI:80",
            "  PairID:CCDDEEFF",
            "EVENT 22 FE80::1 0",
        ]
        bridge.serial_readline = (
            lambda _fd, timeout=2: lines.pop(0) if lines else None)
        bridge.SCAN_RETRY_LIMIT = 4
        pan = bridge.skscan(1, "00112233445566778899AABBCCDDEEFF")
        self.assertEqual(pan["Addr"], "BBBBBBBBBBBBBBBB")
        self.assertEqual(len(self.writes), 1)

    def test_partial_scan_is_discarded_without_event22(self):
        lines = [
            "EVENT 20 FE80::1 0",
            "EPANDESC",
            "  Channel:21",
            "  Pan ID:1111",
            "  Addr:AAAAAAAAAAAAAAAA",
            "  LQI:F0",
            "  PairID:CCDDEEFF",
        ]
        clock = [0.0]

        def fake_readline(_fd, timeout=2):
            if lines:
                return lines.pop(0)
            clock[0] += 1.0
            return None

        bridge.serial_readline = fake_readline
        bridge.SCAN_RETRY_LIMIT = 4
        bridge.scan_timeout_for_duration = lambda _duration: 0.01
        bridge.time.time = lambda: clock[0]
        self.assertEqual(
            bridge.skscan(1, "00112233445566778899AABBCCDDEEFF"), {})

    def test_incomplete_pan_is_ignored(self):
        pans = [
            {"Channel": "21", "Pan ID": "1111", "LQI": "FF",
             "PairID": "CCDDEEFF"},
            {"Channel": "22", "Pan ID": "2222", "Addr": "BBBB",
             "LQI": "80", "PairID": "CCDDEEFF"},
        ]
        self.assertEqual(
            bridge.select_pan(pans, "00112233445566778899AABBCCDDEEFF")["Addr"],
            "BBBB")


class MeasurementDecodeTests(unittest.TestCase):
    def test_no_data_sentinels_are_not_exposed_as_measurements(self):
        props = {
            0xE7: bytearray(struct.pack(">I", bridge.MISSING_INSTANT_POWER)),
            0xE0: bytearray(struct.pack(">I", bridge.MISSING_CUMULATIVE_ENERGY)),
            0xE3: bytearray(struct.pack(">I", bridge.MISSING_CUMULATIVE_ENERGY)),
            0xE8: bytearray(struct.pack(">HH", bridge.MISSING_INSTANT_CURRENT, 123)),
        }
        values = bridge.decode_measurements(props)
        self.assertNotIn("power_w", values)
        self.assertNotIn("energy_forward_raw", values)
        self.assertNotIn("energy_reverse_raw", values)
        self.assertNotIn("current_r_a", values)
        self.assertEqual(values["current_t_a"], 12.3)

    def test_normal_measurements_keep_existing_decoding(self):
        props = {
            0xE7: bytearray(struct.pack(">i", -123)),
            0xE0: bytearray(struct.pack(">I", 1000)),
            0xE3: bytearray(struct.pack(">I", 500)),
            0xE8: bytearray(struct.pack(">hh", 123, -45)),
        }
        values = bridge.decode_measurements(props)
        self.assertEqual(values["power_w"], -123)
        self.assertEqual(values["energy_forward_raw"], 1000)
        self.assertEqual(values["energy_reverse_raw"], 500)
        self.assertEqual(values["current_r_a"], 12.3)
        self.assertEqual(values["current_t_a"], -4.5)


class WoptControlTests(unittest.TestCase):
    def setUp(self):
        self.original_read = bridge.read_wopt_mode
        self.original_command = bridge.skcommand
        self.original_serial_write = bridge.serial_write
        self.original_serial_readline = bridge.serial_readline
        self.commands = []

    def tearDown(self):
        bridge.read_wopt_mode = self.original_read
        bridge.skcommand = self.original_command
        bridge.serial_write = self.original_serial_write
        bridge.serial_readline = self.original_serial_readline

    def _record_command(self, fd, command, timeout=10):
        self.commands.append(command)
        return ["OK"]

    def test_ropt_response_is_parsed(self):
        lines = ["ROPT", "OK 01"]
        written = []
        bridge.serial_write = lambda _fd, value: written.append(value)
        bridge.serial_readline = (
            lambda _fd, timeout=10: lines.pop(0) if lines else None)
        self.assertEqual(bridge.read_wopt_mode(1), 0x01)
        self.assertEqual(written, ["ROPT\r\n"])

    def test_wopt_is_skipped_when_ascii_hex_mode_is_already_enabled(self):
        bridge.read_wopt_mode = lambda fd: 0x01
        bridge.skcommand = self._record_command
        self.assertFalse(bridge.ensure_ascii_hex_mode(1))
        self.assertEqual(self.commands, [])

    def test_wopt_is_applied_when_mode_is_disabled(self):
        bridge.read_wopt_mode = lambda fd: 0x00
        bridge.skcommand = self._record_command
        self.assertTrue(bridge.ensure_ascii_hex_mode(1))
        self.assertEqual(self.commands, ["WOPT 1"])

    def test_wopt_falls_back_when_ropt_is_unavailable(self):
        def fail(_fd):
            raise RuntimeError("unsupported")
        bridge.read_wopt_mode = fail
        bridge.skcommand = self._record_command
        self.assertTrue(bridge.ensure_ascii_hex_mode(1))
        self.assertEqual(self.commands, ["WOPT 1"])


class EventHandlingTests(unittest.TestCase):
    def setUp(self):
        self.original_readline = bridge.serial_readline

    def tearDown(self):
        bridge.serial_readline = self.original_readline

    def test_event_29_reserves_reconnect_and_keeps_waiting(self):
        lines = [
            "EVENT 29 FE80::1",
            "ERXUDP 0 0 0 0 0 0 0 0 " + "1081000102880105FF017201E70400000064",
        ]

        def fake_readline(_fd, timeout=10):
            return lines.pop(0) if lines else None

        state = {"session_expired": False}
        bridge.serial_readline = fake_readline
        data = bridge.read_erxudp(1, timeout=1, expected_tid=1,
                                  event_state=state)
        self.assertIsNotNone(data)
        self.assertTrue(state["session_expired"])


if __name__ == "__main__":
    unittest.main()
