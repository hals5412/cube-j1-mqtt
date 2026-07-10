#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MQTTブリッジの副作用が小さい制御処理を確認します。"""

from __future__ import print_function

import os
import sys
import unittest


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
