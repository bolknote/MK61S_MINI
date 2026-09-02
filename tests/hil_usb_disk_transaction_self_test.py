#!/usr/bin/env python3

import unittest

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
    validate_new_disk,
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

    def test_listing_parser_ignores_echo_and_prompt(self):
        report = "ls /\r\nd\tGames/\r\nf\t12 B\tHIL4488.txt\r\n2 entries.\r\n/> "
        self.assertEqual(
            listing_entries(report),
            ("d\tGames/", "f\t12 B\tHIL4488.txt"),
        )


if __name__ == "__main__":
    unittest.main()
