#!/usr/bin/env python3
"""Build a release from a clean directory and reject a validly checksummed M4 APP."""

# Resolve shared host helpers independently of the current command directory.
import sys as _tool_sys
from pathlib import Path as _ToolPath
_tool_root = _ToolPath(__file__).resolve().parents[1]
_tool_sys.path[:0] = [str(_tool_root), str(_tool_root / "dev/lib"), str(_tool_root / "dev/tools")]
import hashlib
import json
import os
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
from tools.apps.system.build_picocalc_apps import APPS
from tools.apps.urq.library import disk_games


class PackageTests(unittest.TestCase):
    def test_clean_bundle_and_cpu_guard(self):
        # Qualify another sealed candidate without replacing the default bundle.
        source=Path(os.environ.get('MK61_TEST_PICOCALC_PACKAGE_DIR',ROOT/'.build/firmware/picocalc-pico-h'))
        with tempfile.TemporaryDirectory(prefix='mk61-pico-package-') as temporary:
            target=Path(temporary)/'release';target.mkdir()
            for name in ('manifest.json','program-capabilities.json','mk61s-picocalc-pico-h.uf2'):
                shutil.copy2(source/name,target/name)
            shutil.copytree(source/'apps',target/'apps')
            stale_urq=target/'apps/URQ/demo'
            stale_urq.mkdir(parents=True,exist_ok=True)
            (stale_urq/'catalog-report.json').write_text('{}')
            (target/'System/VMCache').mkdir(parents=True)
            (target/'System/old.txt').write_text('stale output, outside this Pico bundle')
            command=[sys.executable,str(ROOT/'tools/firmware/picocalc/package_picocalc.py'),'--directory',str(target)]
            subprocess.run(command,check=True,capture_output=True,text=True)
            version=json.loads((target/'manifest.json').read_text())['prototype_version']
            archive=target/f'mk61s-picocalc-pico-h-{version}.zip'
            with zipfile.ZipFile(archive) as reader:
                prefix='mk61s-picocalc-pico-h/'
                self.assertIsNone(reader.testzip())
                self.assertEqual(reader.read(prefix+'licenses/LUCIDE.txt'),
                                 (ROOT/'ports/picocalc/MENU_ICONS_LICENSE.txt').read_bytes())
                self.assertFalse(any(name.startswith(prefix+'System/') for name in reader.namelist()))
                self.assertFalse((target/'System/autoexec.wbmp').exists())
                self.assertEqual(len(reader.namelist()),len(set(reader.namelist())))
                disk=prefix+'Disk/'
                self.assertIn(disk+'Documents/',reader.namelist())
                self.assertFalse(any(name.startswith(prefix+path) for name in reader.namelist()
                                     for path in ('urq/','games/','examples/','apps/URQ/')))
                for title, name, source in disk_games():
                    self.assertEqual(reader.read(disk+'Games/'+title+'/'+name),source.read_bytes())
                for title, rom in (('Br8kout','br8kout.ch8'),('ECHO-8','echo8.ch8'),
                                   ('Fuse','fuse.ch8'),('Space Invaders','space-invaders.ch8')):
                    self.assertEqual(reader.read(disk+'Games/'+title+'/Play.txt'),(rom+'\n').encode())
                    self.assertIn(disk+'Games/'+title+'/'+rom,reader.namelist())
                self.assertFalse(any('/house_that_jack_built/' in name for name in reader.namelist()))
                for game in ('trapped_in_time_ru','jim_from_outer_space_ru',
                             'semion_escape','semion_road','semion_snow'):
                    for name in ('AUTHORS.txt','LICENSE.txt'):
                        self.assertIn(prefix+'licenses/urq/'+game+'/'+name,reader.namelist())
                devices={'ELIZA':'Programs','SHEET':'Programs','URQ':'System/URQ','WBMP':'System'}
                for name in APPS:
                    relative=f'{devices.get(name,"Programs/Examples")}/{name}.APP'
                    self.assertEqual(reader.read(disk+relative),(target/'apps'/(name+'.APP')).read_bytes())
                expected=['Disk/Programs/Spectrum/SPECTRUM.APP','Disk/Programs/Spectrum/48.rom',
                    'Disk/Programs/Examples/PATTERN.wbmp','Disk/Programs/Examples/Sheets/BUDGET.mks',
                    'README.txt','README.md','Disk/Fonts/DejaVu-12.FMK','Disk/Fonts/DejaVu-14.FMK',
                    'licenses/ui-fonts/LICENSE-Ark-Pixel.txt','licenses/ui-fonts/LICENSE-DejaVu.txt']
                for name in expected:self.assertIn(prefix+name,reader.namelist())
                hashes=json.loads(reader.read(prefix+f'bundle-sha256-{version}.json'))
                for name,digest in hashes.items():
                    self.assertEqual(hashlib.sha256(reader.read(prefix+name)).hexdigest(),digest,name)
                for font in ('DejaVu-12.FMK','DejaVu-14.FMK'):
                    self.assertEqual(reader.read(disk+'Fonts/'+font),(ROOT/'programs/Fonts'/font).read_bytes())
                for game_dir in sorted((ROOT/'programs/games').iterdir()):
                    if not game_dir.is_dir() or not (game_dir/'autoexec.m61').exists():continue
                    for source in game_dir.iterdir():
                        if source.is_file():
                            self.assertEqual(reader.read(disk+'Games/'+game_dir.name+'/'+source.name),source.read_bytes())
                for name in ('Graphics.tbi','Graphics.foc','Graph.tbi'):
                    self.assertEqual(reader.read(disk+'Programs/Examples/'+name),(ROOT/'programs/examples'/name).read_bytes())
                # A release can be installed without consulting the local source tree.
                reader.extractall(target/'extracted')
            from program_collection import plan
            frozen=plan(target/'extracted/mk61s-picocalc-pico-h')
            self.assertIn('Games/Runner/autoexec.m61',{entry['path'] for entry in frozen['files']})
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
            eliza_report=target/'hardware-eliza-summary.json'
            records=json.loads((target/'apps/manifest.json').read_text())
            eliza=next(r for r in records if r['name']=='ELIZA')
            evidence={'passed':True,'uf2_sha256':build['uf2_sha256'],'app_sha256':eliza['app_sha256']}
            eliza_report.write_text(json.dumps(evidence))
            subprocess.run(command,check=True,capture_output=True,text=True)
            before=archive.read_bytes()
            eliza_report.write_text(json.dumps({**evidence,'app_sha256':'0'*64}))
            rejected=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('ELIZA hardware verification belongs to another APP',rejected.stderr)
            self.assertEqual(archive.read_bytes(),before)
            eliza_report.unlink()
            sheet_report=target/'hardware-sheet-summary.json'
            sheet=next(r for r in records if r['name']=='SHEET')
            evidence={'passed':True,'uf2_sha256':build['uf2_sha256'],'app_sha256':sheet['app_sha256']}
            sheet_report.write_text(json.dumps(evidence))
            subprocess.run(command,check=True,capture_output=True,text=True)
            before=archive.read_bytes()
            sheet_report.write_text(json.dumps({**evidence,'app_sha256':'0'*64}))
            rejected=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn('SHEET hardware verification belongs to another APP',rejected.stderr)
            self.assertEqual(archive.read_bytes(),before)
            sheet_report.unlink()
            native_report=target/'hardware-native-complete-summary.json'
            wbmp=next(r for r in records if r['name']=='WBMP')
            bee=ROOT/'programs/games/Bumblebee'
            evidence={'passed':True,'uf2_sha256':build['uf2_sha256'],
                'app_sha256':wbmp['app_sha256'],
                'native_artwork_manifest_sha256':hashlib.sha256((ROOT/'doc/game-artwork/native/manifest.json').read_bytes()).hexdigest(),
                'uploaded_files_sha256':{'Bumblebee/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in bee.iterdir() if p.is_file()}}
            native_report.write_text(json.dumps(evidence))
            subprocess.run(command,check=True,capture_output=True,text=True)
            before=archive.read_bytes()
            for altered,message in (
                ({**evidence,'app_sha256':'0'*64},'another WBMP APP'),
                ({**evidence,'native_artwork_manifest_sha256':'0'*64},'another artwork manifest'),
                ({**evidence,'uploaded_files_sha256':{'Bumblebee/autoexec.m61':'0'*64}},'another game file')):
                native_report.write_text(json.dumps(altered))
                rejected=subprocess.run(command,capture_output=True,text=True)
                self.assertNotEqual(rejected.returncode,0)
                self.assertIn(message,rejected.stderr)
                self.assertEqual(archive.read_bytes(),before)
            native_report.unlink()
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
