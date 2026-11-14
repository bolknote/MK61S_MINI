#!/usr/bin/env python3
"""Selection and real MKC mock sessions: CPU/ABI gates and safe owned updates."""
import copy
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

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'dev/lib'), str(ROOT)]
from program_collection import (MkcSession, capabilities, distribution_manifest, export,
                                firmware_identity, load_capabilities, logical, plan, sha, synchronize)


def sealed_image():
    data = bytearray(512)
    struct.pack_into('<8sHH7I', data, 256, b'MK61FWC\0', 1, 40, 0x08000000, len(data), 0, 0, 1, 1, 0)
    crc = zlib.crc32(data)
    struct.pack_into('<II', data, 276, crc, crc)
    return bytes(data)


class MemorySession:
    def __init__(self):
        self.files = {}
        self.dirs = {'/'}
        self.calls = []
        self.corrupt = False
    def call(self, operation, remote, local=''):
        self.calls.append((operation, remote))
        if operation == 'LIST':
            rows = []
            for kind, names in [('d', self.dirs), ('f', self.files)]:
                for name in sorted(names):
                    if name != '/' and str(Path(name).parent) == remote:
                        rows.append(f'{kind}\t0\t{Path(name).name}')
            Path(local).write_text('\n'.join(rows), encoding='utf-8')
        elif operation == 'GET':
            Path(local).write_bytes(self.files[remote] + (b'broken' if self.corrupt else b''))
        elif operation == 'PUT':
            assert str(Path(remote).parent) in self.dirs
            self.files[remote] = logical(Path(local).read_bytes(), remote)
        elif operation == 'MKDIR':
            self.dirs.add(remote)
        elif operation == 'REMOVE':
            del self.files[remote]
        else:
            raise AssertionError(operation)


class ProgramBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mk61-program-bundle-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bundle = self.base/'bundle'; self.bundle.mkdir()
        self.firmware = self.bundle/'mk61s-M-classic-v2-uc1609-f401.bin'
        self.firmware.write_bytes(sealed_image())
        self.flags = ' '.join('-D'+name+'='+value for name, value in {
            'MK61_BOARD_CLASSIC_V2':'1', 'MK61_ENABLE_FOCAL':'1', 'MK61_ENABLE_TINYBASIC':'1',
            'MK61_ENABLE_CHIP8':'0', 'MK61_ENABLE_MARKDOWN_VIEWER':'1', 'MK61_ENABLE_WBMP_VIEWER':'0',
            'MK61_ENABLE_USB_SCREEN':'0', 'MK61_PORTABLE_UI_FONTS':'1', 'MK61_FOCAL_AS_APP':'0',
            'MK61_TINYBASIC_AS_APP':'0', 'MK61_CHIP8_AS_APP':'0', 'MK61_MARKDOWN_VIEWER_AS_APP':'0',
            'MK61_WBMP_VIEWER_AS_APP':'0'}.items())
        self.cap = capabilities(self.flags, 'classic-v2', 'f401', self.firmware)
        self.write_cap()
    def write_cap(self):
        (self.bundle/'program-capabilities.json').write_text(json.dumps(self.cap))
    def selection(self, names):
        files = []
        for name, content in names.items():
            source = self.base/'sources'/name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
            data = logical(content, name)
            files.append(dict(path=name, source=str(source), size=len(data), sha256=sha(data)))
        return dict(capabilities=self.cap, files=files)
    def test_exact_build_binding_and_missing_options(self):
        self.assertEqual(load_capabilities(self.bundle)['build_id'], firmware_identity(self.firmware.read_bytes()))
        self.firmware.write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'another firmware'):
            load_capabilities(self.bundle)
        with self.assertRaisesRegex(ValueError, 'definition'):
            capabilities('', 'classic-v2', 'f401', self.firmware)
    def test_real_catalog_selects_sheet_and_filters_interpreter_packages(self):
        selected = plan(self.bundle)
        names = {f['path'] for f in selected['files']}
        self.assertIn('Programs/SHEET.APP', names)
        self.assertIn('Programs/Examples/Sheets/BUDGET.mks', names)
        self.assertIn('Games/Turochamp/autoexec.m61', names)
        self.assertFalse(any(p.startswith('Games/Br8kout/') for p in names))
        self.assertTrue(any(s['package'] == 'CHIP-8 games' for s in selected['skipped']))
        self.cap['features']['basic'] = False; self.cap['features']['focal'] = False
        self.cap['features']['math'] = False; self.write_cap()
        selected = plan(self.bundle)
        names = {f['path'] for f in selected['files']}
        self.assertNotIn('Programs/SHEET.APP', names)
        self.assertFalse(any(p.startswith(('Programs/Examples/Sheets/', 'Games/Turochamp/', 'Games/High Noon/')) for p in names))
        self.assertIn('Games/Runner/autoexec.m61', names)
    def test_f401_font_limits_and_case_only_update(self):
        selected = plan(self.bundle)
        self.assertNotIn('Fonts/DejaVu-14.FMK', {f['path'] for f in selected['files']})
        self.assertTrue(any('file limit 1536' in item['reason'] for item in selected['skipped']))
        session = MemorySession()
        synchronize(self.selection({'Programs/Calculations/Test.txt':b'old'}), session)
        # A case-only name change must not delete the newly updated file.
        session.dirs = {name.replace('/Programs/Calculations','/Programs/CALCULATIONS') for name in session.dirs}
        session.files = {name.replace('/Programs/Calculations','/Programs/CALCULATIONS'):data for name,data in session.files.items()}
        updated = self.selection({'Programs/Calculations/test.txt':b'new'})
        synchronize(updated, session)
        self.assertEqual(session.files['/Programs/CALCULATIONS/Test.txt'], b'new')

    def test_quest_folder_and_local_save_survive_reinstall(self):
        from tools.apps.urq.library import disk_games
        selected = plan(self.bundle)
        for title, leaf, source in disk_games():
            if title == 'Джим из Космоса':
                selected['files'].extend(self.selection({f'Games/{title}/{leaf}': source.read_bytes()})['files'])
        session = MemorySession()
        synchronize(selected, session, verify=True)
        directory = '/Games/Джим из Космоса'
        self.assertEqual(session.files[directory+'/Play.txt'], b'game.urq\n')
        self.assertTrue(any(name.startswith(directory+'/p') for name in session.files))
        self.assertIn('/Documents', session.dirs)
        session.files[directory+'/slot1.urs'] = b'player progress'
        self.assertEqual(synchronize(selected, session, verify=True)['installed'], 0)
        self.assertEqual(session.files[directory+'/slot1.urs'], b'player progress')

    def test_no_graphics_no_sheet_and_wrong_cpu_rejected(self):
        self.cap['features'].update(graphics=False, bitmap=False, fonts=False);self.write_cap()
        selected = plan(self.bundle)
        self.assertNotIn('Programs/SHEET.APP', {f['path'] for f in selected['files']})
        self.cap.update(platform='picocalc', app_memory_limit=49152)
        (self.bundle/'apps').mkdir()
        for name in ('ELIZA', 'SHEET'):
            shutil.copy2(ROOT/f'programs/app/{name}.APP', self.bundle/f'apps/{name}.APP')
        self.write_cap()
        with self.assertRaisesRegex(ValueError, 'CPU'):
            plan(self.bundle)
    def test_updates_preserve_modified_and_unowned_files_delete_only_owned(self):
        session = MemorySession()
        initial = self.selection({'Programs/Examples/Sheets/BUDGET.mks':b'original', 'Games/Test/old.txt':b'old', 'Programs/Calculations/new.txt':b'first'})
        synchronize(initial, session)
        self.assertFalse(any(op == 'GET' for op, _ in session.calls), 'fresh uploads require no readback')
        self.assertTrue(all(len(data) <= 1536 for name, data in session.files.items() if name.endswith('.TXT')))
        session.files['/Programs/Examples/Sheets/BUDGET.mks'] = b'user values'
        session.files['/Games/Test/save.txt'] = b'user save'
        update = self.selection({'Programs/Examples/Sheets/BUDGET.mks':b'updated sample', 'Programs/Calculations/new.txt':b'second'})
        result = synchronize(update, session, verify=True)
        self.assertEqual(session.files['/Programs/Examples/Sheets/BUDGET.mks'], b'user values')
        self.assertEqual(session.files['/Games/Test/save.txt'], b'user save')
        self.assertNotIn('/Games/Test/old.txt', session.files)
        self.assertEqual(session.files['/Programs/Calculations/new.txt'], b'second')
        self.assertIn('Programs/Examples/Sheets/BUDGET.mks', result['preserved'])
        # Repeat update retains the sample's user ownership.
        synchronize(update, session)
        self.assertEqual(session.files['/Programs/Examples/Sheets/BUDGET.mks'], b'user values')
    def test_preflight_failure_has_no_writes(self):
        selected = self.selection({'Programs/Calculations/test.txt':b'first'})
        Path(selected['files'][0]['source']).write_bytes(b'changed')
        session = MemorySession()
        with self.assertRaisesRegex(ValueError, 'changed after'):
            synchronize(selected, session)
        self.assertFalse(any(op in ('PUT','REMOVE','MKDIR') for op, _ in session.calls))
    def test_unchanged_defaults_need_no_program_download(self):
        session=MemorySession()
        original=self.selection({'Programs/Examples/Sheets/BUDGET.mks':b'original'})
        synchronize(original,session)
        session.files['/Programs/Examples/Sheets/BUDGET.mks']=b'user edited values'
        session.calls.clear()
        synchronize(original,session)
        self.assertNotIn(('GET','/Programs/Examples/Sheets/BUDGET.mks'),session.calls)
        self.assertEqual(session.files['/Programs/Examples/Sheets/BUDGET.mks'],b'user edited values')
        synchronize(self.selection({'Programs/Examples/Sheets/BUDGET.mks':b'new default'}),session)
        self.assertEqual(session.files['/Programs/Examples/Sheets/BUDGET.mks'],b'user edited values')

    def test_corrupt_receipt_prevents_any_update(self):
        session=MemorySession()
        selected=self.selection({'Programs/Calculations/test.txt':b'original'})
        synchronize(selected,session)
        session.files['/System/PROGRAMS.TXT']=b'{"format":1,"sha256":"' + b'0'*64 + b'","parts":257}'
        before=dict(session.files);session.calls.clear()
        with self.assertRaisesRegex(ValueError,'receipt index'):
            synchronize(self.selection({'Programs/Calculations/test.txt':b'new'}),session)
        self.assertEqual(session.files,before)
        self.assertFalse(any(op in ('PUT','REMOVE','MKDIR') for op,_ in session.calls))

    def test_missing_system_dependency_and_readback_failure(self):
        selected = self.selection({'Programs/Calculations/test.txt':b'first'})
        selected['system_files'] = [dict(path='BASIC.APP', sha256='0'*64)]
        session = MemorySession()
        with self.assertRaisesRegex(ValueError, 'matching System'):
            synchronize(selected, session)
        selected.pop('system_files')
        session.corrupt = True
        with self.assertRaisesRegex(ValueError, 'readback mismatch'):
            synchronize(selected, session, verify=True)
    def test_export_has_no_host_paths_and_refuses_existing_destination(self):
        selected = self.selection({'Programs/Calculations/test.txt':'Привет →\n'.encode()})
        selected.update(format=1, packages=[], skipped=[])
        output = self.base/'export'
        export(selected, output)
        text = (output/'programs-manifest.json').read_text()
        self.assertNotIn(str(self.base), text)
        self.assertEqual((output/'Programs/Calculations/test.txt').read_text(), 'Привет →\n')
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            export(selected, output)
    def test_installer_uses_frozen_release_files_and_rejects_damage(self):
        selected=self.selection({'Programs/Calculations/release.txt':b'frozen release'})
        selected.update(format=1,packages=['Programs/Calculations'],skipped=[],system_files=[])
        export(selected,self.bundle/'Disk',manifest=self.bundle/'programs-manifest.json')
        Path(selected['files'][0]['source']).write_bytes(b'new unrelated checkout')
        frozen=plan(self.bundle)
        self.assertEqual(Path(frozen['files'][0]['source']).read_bytes(),b'frozen release')
        (self.bundle/'Disk/Programs/Calculations/release.txt').write_bytes(b'damaged')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):
            plan(self.bundle)

    def test_release_zip_keeps_cyrillic_paths_and_empty_documents(self):
        from tools.programs.program_bundle import archive_disk
        selected = self.selection({'Games/Джим из Космоса/Play.txt': b'game.urq\n'})
        selected.update(format=1, packages=[], skipped=[], system_files=[])
        export(selected, self.bundle/'Disk', manifest=self.bundle/'programs-manifest.json')
        archive = self.base / 'release.zip'
        archive_disk(self.bundle, archive)
        with zipfile.ZipFile(archive) as actual:
            self.assertEqual(actual.read('bundle/Disk/Games/Джим из Космоса/Play.txt'), b'game.urq\n')
            self.assertIn('bundle/Disk/Documents/', actual.namelist())

    def test_compiler_resolves_defaults_and_last_definition(self):
        compiler = shutil.which('clang++') or shutil.which('g++')
        if not compiler: self.skipTest('no C++ preprocessor')
        from program_collection import resolved_build_flags
        schema = json.loads((ROOT/'dev/lib/program-capabilities.json').read_text())
        names = set(schema['features'].values()) | {v[0] for v in schema['system_apps'].values()}
        (self.base/'config.h').write_text(''.join(f'#ifndef {name}\n#define {name} 1\n#endif\n' for name in names) + '#define MK61_HAS_COMPILED_GRAPHICS 0\n#define MK61_WS0010_GRAPHICS_100X16 0\n')
        source=self.base/'terminal.cpp';source.write_text('')
        database=self.base/'compile_commands.json'
        database.write_text(json.dumps([dict(directory=str(self.base),file=str(source),
            arguments=[compiler,'-I'+str(self.base),'-DMK61_ENABLE_FOCAL=0','-c',str(source),'-o',str(self.base/'unused.o')])]))
        actual = resolved_build_flags(database)
        self.assertIn('-DMK61_ENABLE_FOCAL=0',actual)
        self.assertIn('-DMK61_ENABLE_TINYBASIC=1',actual)
        self.assertNotIn('-DMK61_DISPLAY_UC1609=',actual)
        self.assertFalse((self.base/'unused.o').exists())

    def test_powershell_capabilities_match_python(self):
        if not shutil.which('pwsh'):
            self.skipTest('PowerShell unavailable')
        (self.bundle/'build.flags').write_text(self.flags)
        subprocess.run(['pwsh','-NoLogo','-NoProfile','-File',str(ROOT/'dev/lib/write-program-capabilities.ps1'),
                        '-Bundle',str(self.bundle),'-Firmware',str(self.firmware),'-Profile','classic-v2','-Mcu','f401'],check=True,capture_output=True)
        self.assertEqual(json.loads((self.bundle/'program-capabilities.json').read_text()), self.cap)
    def test_firmware_cli_previews_and_installs_complete_software(self):
        config = self.base/'firmware.conf'
        config.write_text('MCU=f401\nPROFILE=classic-v2\nMK61_ENABLE_FOCAL=1\nMK61_ENABLE_TINYBASIC=1\nMK61_ENABLE_CHIP8=0\nMK61_ENABLE_MARKDOWN_VIEWER=1\n')
        output = self.base/'firmware-output'
        bundle = output/self.firmware.stem
        bundle.mkdir(parents=True)
        shutil.copy2(self.firmware, bundle/self.firmware.name)
        shutil.copy2(self.bundle/'program-capabilities.json',bundle/'program-capabilities.json')
        system = bundle/'System';system.mkdir()
        # Only source/transport orchestration is under test here: the ordinary
        # firmware/System build suites validate the actual ARM modules.
        for name in ('USBDISK','FOCAL','BASIC','LANGVM','LANGIN','SRCEDIT','SETUP','EXPLORER','MARKDOWN','TERMINAL','CLOCK'):
            (system/(name+'.APP')).write_bytes(bytes(64))
        (system/'HELP0.TXT').write_text('help\n')
        (system/'HELP1.TXT').write_text('help\n')
        (bundle/'build.apps').write_text('format 1\nabi 6\n')
        device=self.base/'complete-device';device.mkdir()
        environment={**os.environ, 'MK61_CONFIG_FILE':str(config), 'MK61_OUTPUT_DIR':str(output),
                     'MK61_TEST_MKC_DEVICE':str(device), 'MK61_COLOR':'never'}
        command=['bash', str(ROOT/'tools/firmware/cli/mk61-firmware.sh'), '--mcu','f401','--profile','classic-v2']
        report=subprocess.run([*command,'--show-config'],env=environment,text=True,capture_output=True,check=True).stdout
        flags=next(line.split('=',1)[1] for line in report.splitlines() if line.startswith('COMPILE_FLAGS='))
        (bundle/'build.flags').write_text(flags+'\n')
        # Remove the modules disabled by this exact selection.
        definitions=dict(__import__('re').findall(r'-D(\w+)=([01])',flags))
        for feature, placement, name in [('SETUP','SETUP','SETUP'),('CHIP8','CHIP8','CHIP8'),('MARKDOWN_VIEWER','MARKDOWN_VIEWER','MARKDOWN'),('WBMP_VIEWER','WBMP_VIEWER','WBMP')]:
            target=system/(name+'.APP')
            if definitions.get('MK61_ENABLE_'+feature)=='1' and definitions.get('MK61_'+placement+'_AS_APP')=='1':target.write_bytes(bytes(64))
            else:target.unlink(missing_ok=True)
        preview=subprocess.run([*command,'--preview-programs'],env=environment,text=True,capture_output=True)
        self.assertEqual(preview.returncode,0,preview.stdout+preview.stderr)
        self.assertIn('Programs/Examples/Sheets',preview.stdout)
        self.assertFalse(list(device.iterdir()),'preview must not access/write the device')
        installed=subprocess.run([*command,'--install-all'],env=environment,text=True,capture_output=True)
        self.assertEqual(installed.returncode,0,installed.stdout+installed.stderr)
        self.assertTrue((device/'Programs/SHEET.APP').exists())
        self.assertTrue((device/'Programs/Examples/Sheets/BUDGET.mks').exists())
        self.assertTrue((device/'System/BASIC.APP').exists())
        self.assertFalse((device/'Fonts/DejaVu-14.FMK').exists())
        if shutil.which('pwsh'):
            pscommand=['pwsh','-NoLogo','-NoProfile','-File',str(ROOT/'tools/firmware/cli/mk61-firmware.ps1'), '--mcu','f401','--profile','classic-v2']
            report=subprocess.run([*pscommand,'--show-config'],env=environment,text=True,capture_output=True,check=True).stdout
            flags=next(line.split('=',1)[1] for line in report.splitlines() if line.startswith('COMPILE_FLAGS='))
            (bundle/'build.flags').write_text(flags+'\n')
            preview=subprocess.run([*pscommand,'--preview-programs'],env=environment,text=True,capture_output=True)
            self.assertEqual(preview.returncode,0,preview.stdout+preview.stderr)
            installed=subprocess.run([*pscommand,'--install-programs'],env=environment,text=True,capture_output=True)
            self.assertEqual(installed.returncode,0,installed.stdout+installed.stderr)


    def test_real_bash_and_powershell_mkc_mock_update(self):
        commands = [['bash', str(ROOT/'tools/mkc/mkc.sh')]]
        if shutil.which('pwsh'):
            commands.append(['pwsh','-NoLogo','-NoProfile','-File',str(ROOT/'tools/mkc/mkc.ps1')])
        for number, command in enumerate(commands):
            with self.subTest(command=command[0]):
                device = self.base/f'device{number}'; device.mkdir()
                selected = self.selection({'Programs/Calculations/Тест.txt':'Привет →\n'.encode(), 'Programs/Examples/Sheets/BUDGET.mks':b'old', 'Games/Test/old.txt':b'old'})
                session = MkcSession(self.cap, mock=device, command=command)
                try: synchronize(selected, session, verify=True)
                finally: session.close()
                (device/'Programs/Examples/Sheets/BUDGET.mks').write_bytes(b'user')
                updated = self.selection({'Programs/Calculations/Тест.txt':'Обновление\n'.encode(), 'Programs/Examples/Sheets/BUDGET.mks':b'new'})
                session = MkcSession(self.cap, mock=device, command=command)
                try: synchronize(updated, session, verify=True)
                finally: session.close()
                self.assertEqual((device/'Programs/Examples/Sheets/BUDGET.mks').read_bytes(), b'user')
                self.assertFalse((device/'Games/Test/old.txt').exists())


if __name__ == '__main__':
    unittest.main()
