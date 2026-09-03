#!/usr/bin/env python3

import unittest
from unittest.mock import patch

from hil_multi_device_identity import Identity
from hil_usb_disk_transaction import (
    CDC_PID,
    MSC_PID,
    STM32_VID,
    console_locked,
    find_cdc_location,
    find_msc_node,
    listing_entries,
    msc_configured,
    posix_cksum,
    require_file_contents,
    validate_new_disk,
    wait_for_msc_disk,
)


IDENTITY = Identity(
    "6FF33152484A4488", "484A4488", "3688388E3233",
    "0A24B723", "12345678", "mini-v3-ws0010",
)


def usb_node(pid: int, serial: str, location: int, configured: bool = True):
    node = {
        "idVendor": STM32_VID,
        "idProduct": pid,
        "USB Serial Number": serial,
        "locationID": location,
    }
    if configured:
        node["kUSBCurrentConfiguration"] = 1
    return node


class UsbDiskTransactionTest(unittest.TestCase):
    def test_file_readback_checksum_matches_posix_vectors(self):
        self.assertEqual(posix_cksum(b""), 4294967295)
        self.assertEqual(posix_cksum(b"123456789"), 930766865)
        self.assertEqual(posix_cksum(b"abc"), 1219131554)

    def test_file_readback_validates_order_bytes_and_checksum(self):
        report = (
            "fsget /HIL4488.TXT\r\n"
            "@MKC:GET 3 1219131554\r\n"
            "@MKC:DATA 0 61\r\n"
            "@MKC:DATA 1 6263\r\n"
            "@MKC:END 3 1219131554\r\n/> "
        )
        require_file_contents(report, b"abc")
        require_file_contents(
            "@MKC:GET 0 4294967295\n@MKC:END 0 4294967295\n", b""
        )
        bad_reports = (
            report.replace("DATA 1", "DATA 2"),
            report.replace("6263", "6264"),
            report.replace("6263", "626"),
            report.replace("6263", "626364"),
            report.replace("1219131554", "0"),
            report.replace("@MKC:END 3 1219131554", ""),
            report.replace("@MKC:DATA 1 6263", "@MKC:ERROR GET_IO"),
        )
        for malformed in bad_reports:
            with self.subTest(report=malformed), self.assertRaises(AssertionError):
                require_file_contents(malformed, b"abc")

    def test_topology_selects_exact_cdc_and_msc(self):
        tree = {
            "IOConsoleLocked": False,
            "IORegistryEntryChildren": [
                usb_node(CDC_PID, IDENTITY.usb, 0x100000),
                usb_node(CDC_PID, "2068336B4731", 0x1140000),
            ],
        }
        location = find_cdc_location(tree, IDENTITY)
        self.assertEqual(location, 0x100000)
        tree["IORegistryEntryChildren"][0] = usb_node(
            MSC_PID, IDENTITY.usb, location
        )
        node = find_msc_node(tree, location, IDENTITY.usb)
        self.assertIsNotNone(node)
        self.assertTrue(msc_configured(node))
        self.assertIsNone(find_msc_node(tree, location, "2068336B4731"))

    def test_locked_and_unconfigured_are_distinct(self):
        tree = {
            "IOConsoleLocked": True,
            "IORegistryEntryChildren": [
                usb_node(MSC_PID, IDENTITY.usb, 7, configured=False)
            ],
        }
        self.assertTrue(console_locked(tree))
        node = find_msc_node(tree, 7, IDENTITY.usb)
        self.assertIsNotNone(node)
        self.assertFalse(msc_configured(node))

    def test_disk_gate_rejects_existing_or_unsafe_media(self):
        good = {
            "DeviceIdentifier": "disk9",
            "BusProtocol": "USB",
            "Internal": False,
            "WholeDisk": True,
            "Writable": True,
            "DeviceBlockSize": 512,
            "Size": 512 * 1024,
            "MediaName": "MK61S Programs",
        }
        self.assertEqual(
            validate_new_disk({"disk0", "disk8"},
                              {"disk0", "disk8", "disk9"}, good),
            "disk9",
        )
        with self.assertRaisesRegex(AssertionError, "exactly one"):
            validate_new_disk(
                {"disk0"}, {"disk0", "disk8", "disk9"}, good
            )
        unsafe = dict(good, DeviceIdentifier="disk8", Size=16_000_000_000_000)
        with self.assertRaisesRegex(AssertionError, "refusing"):
            validate_new_disk({"disk0"}, {"disk0", "disk8"}, unsafe)

    def test_configured_msc_is_usable_with_locked_console(self):
        tree = {
            "IOConsoleLocked": True,
            "IORegistryEntryChildren": [
                usb_node(MSC_PID, IDENTITY.usb, 7, configured=True)
            ],
        }
        info = {
            "DeviceIdentifier": "disk9",
            "BusProtocol": "USB",
            "Internal": False,
            "WholeDisk": True,
            "Writable": True,
            "DeviceBlockSize": 512,
            "Size": 512 * 1024,
            "MediaName": "MK61S Programs",
        }
        with patch("hil_usb_disk_transaction.usb_tree", return_value=tree), \
             patch("hil_usb_disk_transaction.whole_disks",
                   return_value={"disk0", "disk9"}), \
             patch("hil_usb_disk_transaction.disk_info", return_value=info):
            self.assertEqual(
                wait_for_msc_disk(7, IDENTITY.usb, {"disk0"}, 1.0),
                ("disk9", info),
            )

    def test_timeout_retains_unconfigured_stage_after_device_returns(self):
        unconfigured = {
            "IOConsoleLocked": True,
            "IORegistryEntryChildren": [
                usb_node(MSC_PID, IDENTITY.usb, 7, configured=False)
            ],
        }
        absent = {"IOConsoleLocked": True}
        with patch("hil_usb_disk_transaction.usb_tree",
                   side_effect=[unconfigured, absent]), \
             patch("hil_usb_disk_transaction.time.monotonic",
                   side_effect=[0.0, 0.1, 0.2, 0.4, 0.5, 2.0]), \
             patch("hil_usb_disk_transaction.time.sleep"), \
             patch("hil_usb_disk_transaction.whole_disks") as disks:
            with self.assertRaises(TimeoutError) as raised:
                wait_for_msc_disk(7, IDENTITY.usb, {"disk0"}, 1.0)
        self.assertIn("MSC enumerated but not configured", str(raised.exception))
        self.assertIn("MSC USB node not present", str(raised.exception))
        disks.assert_not_called()

    def test_listing_parser_ignores_echo_and_prompt(self):
        report = "ls /\r\nd\tGames/\r\nf\t12 B\tHIL4488.txt\r\n2 entries.\r\n/> "
        self.assertEqual(
            listing_entries(report),
            ("d\tGames/", "f\t12 B\tHIL4488.txt"),
        )


if __name__ == "__main__":
    unittest.main()
