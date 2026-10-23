#!/usr/bin/env python3
"""Complete fake-C9 transactions: exact restoration and unknown-data refusal."""
import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shlex
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

from hil_vm_cache_snapshot import CacheSnapshot, PAGES


class Filesystem:
    def __init__(self):
        self.files = {'/personal.txt': b'private user data', '/System/HELP0.TXT': b'help'}
        self.directories = {'/System', '/System/VMCache'}
        self.mutations = []

    def fingerprint(self):
        return dict(files={p: dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest()) for p, b in self.files.items()},
                    directories=sorted(self.directories))

    def read(self, path):
        return self.files[path]

    def write(self, path, data):
        assert path.rsplit('/', 1)[0] in self.directories
        self.mutations.append(('write', path))
        self.files[path] = data

    def command(self, text):
        action, path = shlex.split(text)
        self.mutations.append((action, path))
        if action == 'rm':
            del self.files[path]
            return 'Removed 1 entry.'
        if action == 'mkdir':
            assert path.rsplit('/', 1)[0] in self.directories
            self.directories.add(path)
            return ''
        assert action == 'rmdir' and path in self.directories
        assert not any(p.startswith(path+'/') for p in self.files)
        assert not any(p.startswith(path+'/') for p in self.directories)
        self.directories.remove(path)
        return ''

    def cache(self, source=0x10, language=1, owner_only=False, stamp=1):
        root = f'{PAGES}/{source:04X}'
        self.directories.update((PAGES, root, root+'/IndexA', root+'/Image0'))
        owner = bytearray(16); owner[:4] = b'LFW1'; struct.pack_into('<H', owner, 4, source)
        struct.pack_into('<I', owner, 12, zlib.crc32(owner[:12]))
        self.files[root+'/Owner.bin'] = bytes(owner)
        if not owner_only:
            image = bytearray(1024); image[:4] = b'LBV2'; image[4:6] = bytes((14, language))
            struct.pack_into('<I', image, 8, 1024)
            manifest = bytearray(64); manifest[:4] = b'LFP1'; manifest[5] = 14
            struct.pack_into('<HII', manifest, 6, source, stamp, 0x12345678)
            manifest[16:48] = image[:32]
            struct.pack_into('<I', manifest, 60, zlib.crc32(manifest[:60]))
            self.files[root+'/Manifest.bin'] = bytes(manifest)
            self.files[root+'/Image0/00000000.bin'] = bytes(image)
        return root


class CacheRestorationTests(unittest.TestCase):
    def setUp(self):
        self.fs = Filesystem(); self.root = self.fs.cache()
        self.original = self.fs.fingerprint()
        self.saved = CacheSnapshot(self.original, self.fs.read)

    def restore(self):
        result = self.saved.restore(self.fs.fingerprint(), self.fs.read, self.fs.write, self.fs.command)
        self.assertEqual(self.fs.fingerprint(), self.original)
        self.assertEqual(self.fs.files['/personal.txt'], b'private user data')
        return result

    def refused(self):
        before = copy.deepcopy(self.fs.fingerprint())
        with self.assertRaises(AssertionError):
            self.saved.restore(before, self.fs.read, self.fs.write, self.fs.command)
        self.assertEqual(self.fs.fingerprint(), before)
        self.assertEqual(self.fs.mutations, [])

    def test_basic_generated_pages_and_directories_removed(self):
        self.fs.cache(0x20, 1); result = self.restore()
        self.assertEqual(result['removed'], 3)
        self.assertEqual(result['removed_directories'], 3)
        self.assertTrue(all(action != 'rm -r' for action, path in self.fs.mutations))

    def test_focal_generated_pages_and_directories_removed(self):
        self.fs.cache(0x20, 2); self.restore()

    def test_changed_existing_cache_bytes_restored(self):
        self.fs.cache(stamp=2)
        image = bytearray(self.fs.files[self.root+'/Image0/00000000.bin']); image[100] = 42
        self.fs.files[self.root+'/Image0/00000000.bin'] = bytes(image)
        self.assertEqual(self.restore()['restored'], 2)

    def test_evicted_cache_and_all_directories_recreated(self):
        self.fs.files = {p: b for p, b in self.fs.files.items() if not p.startswith(PAGES+'/')}
        self.fs.directories = {p for p in self.fs.directories if not p.startswith(PAGES)}
        self.assertEqual(self.restore()['created_directories'], 4)

    def test_interrupted_owned_build_can_be_cleaned(self):
        self.fs.cache(0x20, owner_only=True); self.restore()

    def test_unchanged_snapshot_needs_no_mutations(self):
        self.restore(); self.assertEqual(self.fs.mutations, [])

    def test_legacy_cache_is_also_restored(self):
        data = bytearray(65); data[:8] = b'MK61APP\0'
        struct.pack_into('<HH', data, 8, 1, 64)
        struct.pack_into('<I', data, 24, 1)
        struct.pack_into('<I', data, 48, zlib.crc32(data[64:]))
        struct.pack_into('<I', data, 60, zlib.crc32(data[:60]))
        self.fs.files['/System/VMCache/VMC-1234.app'] = bytes(data)
        self.restore()

    def test_unknown_new_user_file_stops_before_mutation(self):
        self.fs.files['/unexpected.txt'] = b'preserve'; self.refused()

    def test_unknown_page_file_stops_before_mutation(self):
        self.fs.files[self.root+'/note.txt'] = b'preserve'; self.refused()

    def test_unknown_page_directory_stops_before_mutation(self):
        self.fs.directories.add(self.root+'/personal'); self.refused()

    def test_invalid_owner_crc_stops_before_mutation(self):
        root = self.fs.cache(0x20, owner_only=True)
        self.fs.files[root+'/Owner.bin'] = b'LFW1'+bytes(12); self.refused()

    def test_owner_source_must_match_directory(self):
        root = self.fs.cache(0x20, owner_only=True)
        owner = bytearray(self.fs.files[root+'/Owner.bin']); struct.pack_into('<H', owner, 4, 0x21)
        struct.pack_into('<I', owner, 12, zlib.crc32(owner[:12]))
        self.fs.files[root+'/Owner.bin'] = bytes(owner); self.refused()

    def test_invalid_manifest_stops_before_mutation(self):
        root = self.fs.cache(0x20)
        manifest = bytearray(self.fs.files[root+'/Manifest.bin']); manifest[4] = 2
        struct.pack_into('<I', manifest, 60, zlib.crc32(manifest[:60]))
        self.fs.files[root+'/Manifest.bin'] = bytes(manifest); self.refused()

    def test_nonstandard_page_size_stops_before_mutation(self):
        self.fs.files[self.root+'/Image0/00000001.bin'] = b'not a 1KiB page'; self.refused()

    def test_noncache_existing_file_change_is_not_overwritten(self):
        self.fs.files['/personal.txt'] = b'changed elsewhere'; self.refused()

    def test_unknown_initial_cache_is_preserved_and_refused(self):
        self.fs.files[self.root+'/note.txt'] = b'preserve'
        before = self.fs.fingerprint()
        with self.assertRaises(AssertionError): CacheSnapshot(before, self.fs.read)
        self.assertEqual(self.fs.fingerprint(), before)
        self.assertEqual(self.fs.mutations, [])

    def test_snapshot_read_must_match_fingerprint(self):
        self.fs.files[self.root+'/Owner.bin'] = bytes(16)
        with self.assertRaisesRegex(AssertionError, 'changed while reading'):
            CacheSnapshot(self.original, self.fs.read)


class GraphicsPreparationTests(unittest.TestCase):
    def test_upload_error_preserves_original_error_and_exact_files(self):
        import hil_basic_graphics as graphics
        for committed in (False,True):
            with self.subTest(lost_commit_ACK=committed), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);examples=root/'programs/examples';examples.mkdir(parents=True)
                (examples/'Graphics.tbi').write_bytes(b'owned graphics source')
                fs=Filesystem();original=fs.fingerprint();closed=[]
                state=dict(reg='reg\r\n'+''.join(f'R{x} =  0.0000000  00\r\n' for x in '0123456789ABCDE')+'IP: 0\r\n/> ',
                           stk='stk\r\n'+''.join(f'{x} =  0.0000000  00\r\n' for x in ('X1','T','Z','Y','X'))+'IP =  0\r\n/> ',
                           dump='dump\r\n'+'00  '*105+'\r\n/> ',pwd='pwd\r\n/\r\n/> ')
                class Port:
                    def pump(self, delay):pass
                    def write_line(self, line):assert line==''
                    def close(self):closed.append(True)
                    def command(self, command):
                        if command=='identity':return 'MK61 ID v=1 public=AEB505B6E0067623 short=E0067623 usb=2068336B4731 volume=AED647EB build=AF4CA1D1 profile=classic-v3-uc1609\r\n/> '
                        if command=='alarm':return 'RTC ALARM A off\r\nRTC ALARM B off\r\n'
                        if command.startswith('cd '):return '/> '
                        if command.startswith('rm '):return fs.command(command)
                        return state[command]
                def upload(port,path,data):
                    if committed:fs.files[path]=data
                    raise RuntimeError('upload unavailable')
                arguments=['hil_basic_graphics.py','--port','fake','--public-id','AEB505B6E0067623','--build-id','AF4CA1D1','--output-dir',str(root/'out')]
                with mock.patch.object(sys,'argv',arguments),mock.patch.object(graphics,'ROOT',root),mock.patch.object(graphics,'ScreenPort',return_value=Port()),mock.patch.object(graphics,'health',return_value={}),mock.patch.object(graphics,'fingerprint',side_effect=lambda port:fs.fingerprint()),mock.patch.object(graphics,'read_file',side_effect=lambda port,path:fs.read(path)),mock.patch.object(graphics,'write_file',side_effect=upload):
                    with self.assertRaisesRegex(RuntimeError,'upload unavailable'):graphics.main()
                self.assertEqual(fs.fingerprint(),original);self.assertTrue(closed)
                result=json.loads((root/'out/result.json').read_text())
                self.assertEqual(result['error'],'upload unavailable');self.assertNotIn('cleanup_error',result)
                self.assertTrue(result['calculator_state_preserved'])

    def test_existing_output_is_refused_before_opening_device(self):
        import hil_basic_graphics as graphics
        with tempfile.TemporaryDirectory() as directory:
            arguments = ['hil_basic_graphics.py', '--port', 'must-not-open', '--public-id', 'AEB505B6E0067623',
                         '--build-id', 'AF4CA1D1', '--output-dir', directory]
            with mock.patch.object(sys, 'argv', arguments), mock.patch.object(graphics, 'ScreenPort') as connect:
                with self.assertRaises(FileExistsError): graphics.main()
                connect.assert_not_called()

    def test_nonempty_calculator_or_IP_refused_for_both_languages(self):
        import hil_basic_graphics as graphics
        for language in ('basic', 'focal'):
            for wrong_register, wrong_ip in ((True, False), (False, True)):
                with self.subTest(language=language, register=wrong_register, ip=wrong_ip), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory); examples = root/'programs/examples'; examples.mkdir(parents=True)
                    (examples/('Graphics.'+('tbi' if language=='basic' else 'foc'))).write_bytes(b'test source')
                    registers = ['R'+x for x in '0123456789ABCDE']
                    state = dict(reg='reg\r\n'+''.join(f'{n} =  {1 if wrong_register and n=="R0" else 0}.0000000  00\r\n' for n in registers)+f'IP: {7 if wrong_ip else 0}\r\n/> ',
                                 stk='stk\r\n'+''.join(f'{n} =  0.0000000  00\r\n' for n in ('X1','T','Z','Y','X'))+'IP =  0\r\n/> ',
                                 dump='dump\r\n'+'00  '*105+'\r\n/> ', pwd='pwd\r\n/\r\n/> ')
                    calls = []
                    class Port:
                        def pump(self, delay): pass
                        def write_line(self, line): assert line == ''
                        def command(self, command):
                            calls.append(command)
                            if command == 'identity':
                                return 'MK61 ID v=1 public=AEB505B6E0067623 short=E0067623 usb=2068336B4731 volume=AED647EB build=AF4CA1D1 profile=classic-v3-uc1609\r\n/> '
                            if command == 'alarm': return 'RTC ALARM A off\r\nRTC ALARM B off\r\n'
                            if command.startswith('cd '): return '/> '
                            return state[command]
                        def close(self): calls.append('closed')
                        def attach(self): raise AssertionError('must not enter foreground')
                    arguments = ['hil_basic_graphics.py', '--language', language, '--port', 'fake', '--public-id', 'AEB505B6E0067623', '--build-id', 'AF4CA1D1', '--output-dir', str(root/'out')]
                    with mock.patch.object(sys, 'argv', arguments), mock.patch.object(graphics, 'ROOT', root), mock.patch.object(graphics, 'ScreenPort', return_value=Port()), mock.patch.object(graphics, 'health', return_value={}), mock.patch.object(graphics, 'fingerprint', return_value={'files':{},'directories':[]}):
                        with self.assertRaises(AssertionError): graphics.main()
                    self.assertIn('closed', calls)
                    self.assertFalse(any(c.startswith(('fsput', 'rm ', 'rst ')) for c in calls))


class CallerPreservationTests(unittest.TestCase):
    def setUp(self):
        import hil_vm_compiled_blocks as base
        import hil_vm_cache_latency as latency
        import hil_turochamp_merge as turo
        self.base, self.latency, self.turo = base, latency, turo
        self.fs = Filesystem(); self.fs.cache()
        self.fs.files['/System/BASIC.app'] = b'original BASIC'
        self.fs.files['/System/VMCache/VMSTORE.app'] = b'user VMSTORE'
        self.temporary = tempfile.TemporaryDirectory(); self.backup = Path(self.temporary.name)
        self.patches = ExitStack()
        self.patches.enter_context(mock.patch.object(base.storage_hil, 'fingerprint', lambda port:self.fs.fingerprint()))
        for module in (base, turo):
            self.patches.enter_context(mock.patch.object(module, 'read_file', lambda port,path:self.fs.read(path)))
            self.patches.enter_context(mock.patch.object(module, 'write_file', lambda port,path,data:self.fs.write(path,data)))
        class Port:
            def command(inner, command, timeout=30): return self.fs.command(command)
        self.port = Port()

    def tearDown(self):
        self.patches.close(); self.temporary.cleanup()

    def snapshot(self):
        self.original = self.fs.fingerprint()
        for path, data in self.fs.files.items():
            destination = self.backup/path.lstrip('/'); destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)

    def assert_refused(self, function):
        before = self.fs.fingerprint()
        with self.assertRaises(AssertionError): function()
        self.assertEqual(self.fs.fingerprint(),before)
        self.assertEqual(self.fs.mutations,[])

    def test_compiled_blocks_stage_preserves_owned_APP_and_user_VMSTORE(self):
        self.snapshot(); self.fs.cache(stamp=2); self.fs.cache(0x20)
        self.fs.files['/System/BASIC.app'] = b'approved candidate BASIC'
        self.base.restore_cache(self.port,self.original,self.backup,allowed_files={'/System/BASIC.app'})
        expected = copy.deepcopy(self.original)
        data=self.fs.files['/System/BASIC.app'];expected['files']['/System/BASIC.app']=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(self.fs.fingerprint(),expected)
        self.assertEqual(self.fs.files['/System/VMCache/VMSTORE.app'],b'user VMSTORE')

    def test_compiled_blocks_foreign_VMSTORE_change_is_refused(self):
        self.snapshot();self.fs.cache(0x20);self.fs.files['/System/VMCache/VMSTORE.app']=b'foreign'
        self.assert_refused(lambda:self.base.restore_cache(self.port,self.original,self.backup))

    def test_latency_finally_restores_original_absent_Pages_root(self):
        self.fs.files={p:b for p,b in self.fs.files.items() if not p.startswith(PAGES+'/')}
        self.fs.directories={p for p in self.fs.directories if not p.startswith(PAGES)}
        self.snapshot();self.fs.cache(0x20)
        self.fs.directories.add('/VMLAT');self.fs.files['/VMLAT/known.tbi']=b'owned source'
        self.fs.files['/System/BASIC.app']=b'approved candidate'
        self.latency.cleanup_files(self.port,self.original,{'/VMLAT/known.tbi'},
            dict(changed_apps={'/System/BASIC.app'},original_files=self.backup))
        self.assertEqual(self.fs.fingerprint(),self.original)
        self.assertEqual(self.fs.files['/System/VMCache/VMSTORE.app'],b'user VMSTORE')

    def test_latency_unknown_fixture_file_is_refused(self):
        self.snapshot();self.fs.cache(0x20);self.fs.directories.add('/VMLAT')
        self.fs.files['/VMLAT/unregistered.tbi']=b'preserve'
        self.assert_refused(lambda:self.latency.cleanup_files(self.port,self.original,{'/VMLAT/known.tbi'},
            dict(changed_apps=set(),original_files=self.backup)))

    def test_turochamp_stage_and_finally_preserve_exact_state(self):
        self.snapshot();self.fs.cache(0x20);self.fs.directories.add('/TCMERGE')
        self.fs.files['/TCMERGE/known.tbi']=b'owned source';self.fs.files['/System/BASIC.app']=b'approved candidate'
        self.turo.restore_vm_cache(self.port,self.original,self.backup,replace_basic=True,
            owned_files={'/TCMERGE/known.tbi'})
        self.assertEqual(self.fs.files['/System/VMCache/VMSTORE.app'],b'user VMSTORE')
        self.fs.command('rm "/TCMERGE/known.tbi"');self.fs.command('rmdir "/TCMERGE"')
        self.assertEqual(self.fs.fingerprint(),self.original)

    def test_turochamp_unknown_fixture_file_is_refused(self):
        self.snapshot();self.fs.cache(0x20);self.fs.directories.add('/TCMERGE')
        self.fs.files['/TCMERGE/unregistered.tbi']=b'preserve'
        self.assert_refused(lambda:self.turo.restore_vm_cache(self.port,self.original,self.backup,
            owned_files={'/TCMERGE/known.tbi'}))


if __name__ == '__main__':
    unittest.main()
