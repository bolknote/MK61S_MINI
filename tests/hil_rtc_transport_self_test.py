#!/usr/bin/env python3
"""RTC/HIL transport deadline and reconnect cleanup, without devices."""
import unittest
from unittest.mock import Mock, patch
import hil_rtc_alarm as rtc


class TransportTests(unittest.TestCase):
    def test_deadline_crossing_never_passes_negative_timeout(self):
        port = rtc.Port.__new__(rtc.Port)
        port.fd = 123
        port.path = "fake-device"

        def select_no_data(_read, _write, _errors, timeout):
            self.assertGreaterEqual(timeout, 0)
            return [], [], []

        # The old loop checked .99 < 1, then calculated 1 - 1.01.
        with patch.object(rtc.time, "monotonic", side_effect=[0, .99, 1.01]), \
             patch.object(rtc.select, "select", side_effect=select_no_data) as select:
            with self.assertRaises(TimeoutError):
                port.read_prompt(1)
        self.assertEqual(select.call_count, 1)

    def test_reconnect_closes_unexpected_failure(self):
        port = Mock()
        port.command.side_effect = ValueError("transport failure")
        with patch.object(rtc, "Port", return_value=port), \
             patch.object(rtc.os.path, "exists", return_value=True), \
             patch.object(rtc.glob, "glob", return_value=[]), \
             patch.object(rtc.time, "sleep"), \
             patch.object(rtc.time, "monotonic", side_effect=[0, .1]):
            with self.assertRaisesRegex(ValueError, "transport failure"):
                rtc.reconnect("fake-device", "AEB505B6E0067623", timeout=1)
        port.close.assert_called_once_with()

    def test_reconnect_retry_closes_only_rejected_ports(self):
        rejected, accepted = Mock(), Mock()
        rejected.command.side_effect = TimeoutError("not ready")
        accepted.command.return_value = "identity public=AEB505B6E0067623"
        with patch.object(rtc, "Port", side_effect=[rejected, accepted]), \
             patch.object(rtc.os.path, "exists", return_value=True), \
             patch.object(rtc.glob, "glob", return_value=[]), \
             patch.object(rtc.time, "sleep"), \
             patch.object(rtc.time, "monotonic", side_effect=[0, .1, .2]):
            port, path = rtc.reconnect("fake-device", "AEB505B6E0067623", timeout=1)
        self.assertIs(port, accepted)
        self.assertEqual(path, "fake-device")
        rejected.close.assert_called_once_with()
        accepted.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
