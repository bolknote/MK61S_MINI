#!/usr/bin/env python3
import os
import pty
import unittest
from unittest.mock import patch
from hil_multi_device_identity import Identity, wait_for_identity
from hil_rtc_alarm import Port


class IdentityIsolationTests(unittest.TestCase):
    def test_macos_reconnect_only_probes_pinned_serial(self):
        target = Identity('AEB505B6E0067623', 'E0067623', '2068336B4731',
                          'AED647EB', '12345678', 'classic-v3-uc1609')
        wanted = '/dev/cu.usbmodem2068336B47311'
        other = '/dev/cu.usbmodem3688388E32331'
        with patch('hil_multi_device_identity.sys.platform', 'darwin'), \
             patch('hil_multi_device_identity.candidate_ports', return_value=[other, wanted]), \
             patch('hil_multi_device_identity.read_identity', return_value=target) as read:
            self.assertEqual(wait_for_identity(target, 1), (wanted, target))
            read.assert_called_once_with(wanted, timeout=1.5)

    def test_exclusive_terminal_releases_on_close(self):
        master, slave = pty.openpty()
        path = os.ttyname(slave)
        os.close(slave)
        try:
            with Port(path):
                with self.assertRaises(OSError):
                    Port(path)
            with Port(path):
                pass
        finally:
            os.close(master)


if __name__ == '__main__':
    unittest.main()
