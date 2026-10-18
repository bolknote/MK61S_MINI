#!/usr/bin/env python3
"""Build a release from a clean directory and reject a validly checksummed M4 APP."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_picocalc_apps import APPS,ASSETS


class PackageTests(unittest.TestCase):
    def test_clean_bundle_and_cpu_guard(self):
        source=ROOT/'binary/picocalc-pico-h'
        with tempfile.TemporaryDirectory(prefix='mk61-pico-package-') as temporary:
            target=Path(temporary)/'release';target.mkdir()
            for name in ('manifest.json','mk61s-picocalc-pico-h.uf2'):
                shutil.copy2(source/name,target/name)
            shutil.copytree(source/'apps',target/'apps')
            command=[sys.executable,str(ROOT/'tools/package_picocalc.py'),'--directory',str(target)]
            subprocess.run(command,check=True,capture_output=True,text=True)
            version=json.loads((target/'manifest.json').read_text())['prototype_version']
            archive=target/f'mk61s-picocalc-pico-h-{version}.zip'
            with zipfile.ZipFile(archive) as reader:
                prefix='mk61s-picocalc-pico-h/'
                self.assertIsNone(reader.testzip())
                expected=[*(f'apps/{name}.APP' for name in APPS),*(f'apps/{name}' for name in ASSETS),
                    'README.txt','README.md','Fonts/DejaVu-12.FMK','Fonts/DejaVu-14.FMK',
                    'licenses/ui-fonts/LICENSE-Ark-Pixel.txt','licenses/ui-fonts/LICENSE-DejaVu.txt']
                for name in expected:self.assertIn(prefix+name,reader.namelist())
                hashes=json.loads(reader.read(prefix+f'bundle-sha256-{version}.json'))
                for name,digest in hashes.items():
                    self.assertEqual(hashlib.sha256(reader.read(prefix+name)).hexdigest(),digest,name)
                for font in ('DejaVu-12.FMK','DejaVu-14.FMK'):
                    self.assertEqual(reader.read(prefix+'Fonts/'+font),(ROOT/'programs/Fonts'/font).read_bytes())
            report=target/'hardware-software-summary.json'
            build=json.loads((target/'manifest.json').read_text())
            # An updated SHA-256 manifest cannot legitimize a broken resident CRC.
            original_firmware=(target/'mk61s-picocalc-pico-h.uf2').read_bytes()
            corrupted=bytearray(original_firmware)
            image_offset=build['firmware_integrity']['footer_offset']+20
            corrupted[(image_offset//256)*512+32+image_offset%256]^=1
            (target/'mk61s-picocalc-pico-h.uf2').write_bytes(corrupted)
            altered=dict(build);altered['uf2_sha256']=hashlib.sha256(corrupted).hexdigest()
            (target/'manifest.json').write_text(json.dumps(altered))
            before=archive.read_bytes()
            rejected=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('firmware CRC mismatch',rejected.stderr)
            self.assertEqual(archive.read_bytes(),before)
            (target/'mk61s-picocalc-pico-h.uf2').write_bytes(original_firmware)
            (target/'manifest.json').write_text(json.dumps(build))
            report.write_text(json.dumps({'passed':True,'uf2_sha256':build['uf2_sha256']}))
            subprocess.run(command,check=True,capture_output=True,text=True)
            with zipfile.ZipFile(archive) as reader:
                self.assertEqual(json.loads(reader.read(prefix+report.name))['passed'],True)
            before=archive.read_bytes()
            for evidence,message in (({'passed':True,'uf2_sha256':'0'*64},'another UF2'),
                                     ({'passed':False,'uf2_sha256':build['uf2_sha256']},'verification failed')):
                report.write_text(json.dumps(evidence))
                rejected=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(rejected.returncode,0)
                self.assertIn(message,rejected.stderr)
                self.assertEqual(archive.read_bytes(),before)
            report.unlink()
            app=target/'apps/HELLO.APP';encoded=bytearray(app.read_bytes())
            flags=struct.unpack_from('<I',encoded,16)[0]
            struct.pack_into('<I',encoded,16,flags&~8)
            struct.pack_into('<I',encoded,60,zlib.crc32(encoded[:60]))
            app.write_bytes(encoded)
            records=json.loads((target/'apps/manifest.json').read_text())
            records[0]['app_sha256']=hashlib.sha256(encoded).hexdigest()
            (target/'apps/manifest.json').write_text(json.dumps(records))
            rejected=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('incompatible CPU',rejected.stderr)
            self.assertEqual(archive.read_bytes(),before)


if __name__=='__main__':unittest.main()
