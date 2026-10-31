#!/usr/bin/env python3
"""No hardware: exact Pico image union, full backup and settings protection."""
import importlib.util
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
spec=importlib.util.spec_from_file_location('pico_image',HERE/'pico-image.py')
image=importlib.util.module_from_spec(spec);spec.loader.exec_module(image)


class ImageTest(unittest.TestCase):
    def fixture(self):
        baseline=b'baseline'*512;native=b'candidate'*768
        original=bytearray(b'\xff'*image.FLASH_BYTES)
        original[:len(baseline)]=baseline
        original[-8192:]=bytes(range(256))*32
        payload=b'payload'*1172+bytes(4) # Exactly 8,208 bytes, not an 8-KiB cap.
        self.assertEqual(len(payload),8208)
        layout=dict(cpu='m0',base=image.PAYLOAD_BASE,bytes=len(payload),sha256=image.sha(payload))
        return bytes(original),baseline,native,payload,layout

    def compose(self,original,baseline,native,payload,layout,**overrides):
        hashes=dict(original_sha256=image.sha(original),baseline_sha256=image.sha(baseline),native_sha256=image.sha(native))
        hashes.update(overrides)
        return image.compose(original,original,baseline,native,payload,layout,**hashes)

    def test_complete_original_tail_settings_and_unused_bytes_preserved(self):
        original,baseline,native,payload,layout=self.fixture()
        candidate=self.compose(original,baseline,native,payload,layout)
        start=image.PAYLOAD_BASE-image.BASE;end=start+len(payload)
        self.assertEqual(candidate[:len(native)],native)
        self.assertEqual(candidate[start:end],payload)
        self.assertEqual(candidate[len(native):start],original[len(native):start])
        self.assertEqual(candidate[end:],original[end:])
        self.assertEqual(candidate[-8192:],original[-8192:])
        self.assertEqual(len(candidate),image.FLASH_BYTES)

    def test_stale_hash_wrong_prefix_truncation_and_disagreeing_backups_rejected(self):
        original,baseline,native,payload,layout=self.fixture()
        for field in ('original_sha256','baseline_sha256','native_sha256'):
            with self.subTest(field=field),self.assertRaises(image.Hold):
                self.compose(original,baseline,native,payload,layout,**{field:'0'*64})
        with self.assertRaises(image.Hold):self.compose(original,baseline+b'bad',native,payload,layout)
        for backup in (original[:-1],original[:-1]+b'X'):
            with self.assertRaises(image.Hold):
                image.compose(original,backup,baseline,native,payload,layout,
                    original_sha256=image.sha(original),baseline_sha256=image.sha(baseline),native_sha256=image.sha(native))

    def test_entire_erase_span_must_be_unused_even_beyond_payload(self):
        original,baseline,native,payload,layout=self.fixture()
        for at in (image.PAYLOAD_BASE-image.BASE,image.PAYLOAD_BASE-image.BASE+len(payload)+16):
            changed=bytearray(original);changed[at]=0
            with self.subTest(at=hex(at)),self.assertRaises(image.Hold):
                self.compose(bytes(changed),baseline,native,payload,layout)

    def test_overlap_wrong_target_and_bad_layout_never_compose(self):
        original,baseline,native,payload,layout=self.fixture()
        for field,value in (('base',0x10180000),('cpu','m4'),('bytes',len(payload)-1),('sha256','0'*64)):
            with self.subTest(field=field),self.assertRaises(image.Hold):
                self.compose(original,baseline,native,payload,{**layout,field:value})
        for native in (b'x'*(image.PAYLOAD_BASE-image.BASE+1),b'x'*(image.SETTINGS_OFFSET+1)):
            with self.assertRaises(image.Hold):self.compose(original,baseline,native,payload,layout)
        too_large=b'x'*(image.SETTINGS_OFFSET-(image.PAYLOAD_BASE-image.BASE)+1)
        with self.assertRaises(image.Hold):
            self.compose(original,baseline,b'new',too_large,{**layout,'bytes':len(too_large),'sha256':image.sha(too_large)})


if __name__=='__main__':unittest.main()
