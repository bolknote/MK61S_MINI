"""Incremental publishers own payload names, never saves or arbitrary files."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.apps.urq import build_urq_library as builder
from tools.apps.urq import library


def put(root, name, data=b'old'):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def seed(games, licenses):
    for name in ('game.urq', 'p0000.uqd', 'autoexec.wbmp'):
        put(games, 'house_that_jack_built/' + name)
    for name in ('AUTHORS.txt', 'LICENSE.txt'):
        put(licenses, 'house_that_jack_built/' + name)
    put(licenses, 'house_that_jack_built/autoexec.wbmp', (ROOT / 'doc/explorer-icons/license.wbmp').read_bytes())
    survivors = {'house_that_jack_built/slot.urs': b'save', 'house_that_jack_built/note.txt': b'note',
                 'semion_escape/custom.urq': b'custom quest', 'custom/game.urq': b'user game',
                 'custom/p0000.uqd': b'user data', 'root-note.txt': b'root note'}
    for name, payload in survivors.items():
        put(games, name, payload)
    put(games, 'semion_escape/p9999.uqd')
    put(licenses, 'house_that_jack_built/note.txt', b'license note')
    return survivors


class LibrarySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='urq-sync-')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def test_python_incremental_removes_only_owned_obsolete_payload(self):
        games, licenses = self.output / 'Games', self.output / 'licenses'
        survivors = seed(games, licenses)
        device_files = library.copy_device_library(games)
        license_files = library.copy_licenses(licenses)
        self.assertEqual(len(device_files), 18)
        self.assertEqual(len(license_files), 10)
        self.assertEqual(snapshot(games), {**{str(path.relative_to(games)): path.read_bytes() for path in device_files}, **survivors})
        self.assertEqual(snapshot(licenses), {**{str(path.relative_to(licenses)): path.read_bytes() for path in license_files},
                                            'house_that_jack_built/note.txt': b'license note'})
        # A second invocation has the same payload and still preserves saves.
        before = snapshot(games)
        library.copy_device_library(games)
        self.assertEqual(snapshot(games), before)

    def test_empty_retired_folders_disappear_but_custom_license_icon_stays(self):
        games, licenses = self.output / 'Games', self.output / 'licenses'
        put(games, 'house_that_jack_built/game.urq')
        put(licenses, 'house_that_jack_built/LICENSE.txt')
        put(licenses, 'house_that_jack_built/autoexec.wbmp', b'custom icon')
        library.copy_device_library(games)
        library.copy_licenses(licenses)
        self.assertFalse((games / 'house_that_jack_built').exists())
        self.assertEqual(snapshot(licenses)['house_that_jack_built/autoexec.wbmp'], b'custom icon')

    def test_redirected_directory_and_payload_refuse_before_mutation(self):
        for file_link in (False, True):
            with self.subTest(file_link=file_link):
                games = self.output / str(file_link)
                outside = self.output / ('outside-' + str(file_link))
                put(outside, 'game.urq', b'outside sentinel')
                stale = put(games, 'house_that_jack_built/game.urq', b'stale sentinel')
                folder = games / 'semion_escape'
                if file_link:
                    folder.mkdir()
                    (folder / 'game.urq').symlink_to(outside / 'game.urq')
                else:
                    folder.symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'unsafe'):
                    library.copy_device_library(games)
                self.assertEqual(stale.read_bytes(), b'stale sentinel')
                self.assertEqual((outside / 'game.urq').read_bytes(), b'outside sentinel')
                self.assertFalse((games / 'autoexec.wbmp').exists())

    def test_missing_source_part_refuses_before_destination_prune(self):
        fixture = self.output / 'source'
        shutil.copytree(ROOT / 'programs/urq', fixture / 'programs/urq')
        put(fixture, 'tools/apps/urq/catalog-report.json', (ROOT / 'tools/apps/urq/catalog-report.json').read_bytes())
        (fixture / 'programs/urq/semion_escape/p0000.uqd').unlink()
        games = self.output / 'Games'
        stale = put(games, 'house_that_jack_built/game.urq', b'keep on failure')
        with mock.patch.object(library, 'ROOT', fixture), self.assertRaisesRegex(ValueError, 'missing/unsafe'):
            library.copy_device_library(games)
        self.assertEqual(stale.read_bytes(), b'keep on failure')
        self.assertFalse((games / 'autoexec.wbmp').exists())

    def test_sources_cannot_be_used_as_distribution_destination(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            library.copy_device_library(ROOT / 'programs/urq')
        with self.assertRaisesRegex(ValueError, 'overlap'):
            library.copy_licenses(library.SOURCES)

    def upstream(self):
        upstream = self.output / 'upstream'
        games = [{'folder': key, 'title': key, 'author': 'Test', 'lang': 'ru'} for key in ('new', 'retired')]
        put(upstream, 'games.json', json.dumps(games).encode())
        put(upstream, 'games/new/main.qst', b'; SPDX-License-Identifier: MIT\n:start\npln Example\nend\n')
        put(upstream, 'games/new/LICENSE.txt', b'MIT License\nTest fixture')
        put(upstream, 'games/retired/main.qst', b':start\npln Unlicensed\nend\n')
        return upstream

    def generate(self, upstream, games):
        # Real conversion and filesystem publishing, no host/device access. The
        # startup boundary and supplementary source/network access are stubbed.
        with mock.patch.object(builder, 'revision', return_value=builder.LOCK['commit']), \
             mock.patch.object(builder, 'smoke', return_value={'status': 2, 'variables': 0, 'actions': 0}), \
             mock.patch('tools.apps.urq.extra_games.publish', return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            return builder.build(upstream, Path('/unused'), games, source_output=self.output / 'sources',
                                 report_path=self.output / 'report.json')

    def test_direct_incremental_generator_prunes_retired_quests_and_surplus_parts(self):
        upstream, games = self.upstream(), self.output / 'Games'
        for key in ('house_that_jack_built', 'retired'):
            for name in ('game.urq', 'p0000.uqd', 'autoexec.wbmp'):
                put(games, key + '/' + name)
            put(games, key + '/slot.urs', b'save')
        put(games, 'new/p9999.uqd')
        put(games, 'custom/game.urq', b'user')
        report = self.generate(upstream, games)
        self.assertEqual(report['published'], ['new'])
        self.assertTrue((games / 'new/game.urq').is_file())
        self.assertFalse((games / 'new/p9999.uqd').exists())
        for key in ('house_that_jack_built', 'retired'):
            self.assertEqual(snapshot(games / key), {'slot.urs': b'save'})
        self.assertEqual((games / 'custom/game.urq').read_bytes(), b'user')

    def test_generator_rejects_redirect_before_any_output_or_source_write(self):
        upstream, games = self.upstream(), self.output / 'Games'
        outside = self.output / 'external'
        put(outside, 'game.urq', b'outside sentinel')
        put(games, 'autoexec.wbmp', b'previous root icon')
        put(games, 'house_that_jack_built/game.urq', b'previous quest')
        (games / 'new').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self.generate(upstream, games)
        self.assertEqual(snapshot(outside), {'game.urq': b'outside sentinel'})
        self.assertEqual((games / 'autoexec.wbmp').read_bytes(), b'previous root icon')
        self.assertEqual((games / 'house_that_jack_built/game.urq').read_bytes(), b'previous quest')
        self.assertFalse((self.output / 'sources').exists())
        self.assertFalse((self.output / 'report.json').exists())

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_windows_publisher_matches_python_and_preserves_user_files(self):
        py_games, py_licenses = self.output / 'py/Games', self.output / 'py/licenses'
        ps_games, ps_licenses = self.output / 'ps/Games', self.output / 'ps/licenses'
        seed(py_games, py_licenses)
        seed(ps_games, ps_licenses)
        library.copy_device_library(py_games)
        library.copy_licenses(py_licenses)
        helper = ROOT / 'tools/apps/urq/copy_urq_library.ps1'
        process = subprocess.run(['pwsh', '-NoLogo', '-NoProfile', '-File', str(helper), '-ProjectRoot', str(ROOT),
                                  '-LibraryOutput', str(ps_games), '-LicensesOutput', str(ps_licenses)],
                                 capture_output=True, text=True, cwd=self.output)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(snapshot(ps_games), snapshot(py_games))
        self.assertEqual(snapshot(ps_licenses), snapshot(py_licenses))
        clean = self.output / 'clean'
        process = subprocess.run(['pwsh', '-NoLogo', '-NoProfile', '-File', str(helper), '-ProjectRoot', str(ROOT),
                                  '-LicensesOutput', str(clean)], capture_output=True, text=True, cwd=self.output)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertFalse((clean / 'house_that_jack_built').exists())
        self.assertEqual(len(snapshot(clean)), 10)

    @unittest.skipUnless(shutil.which('pwsh'), 'PowerShell unavailable')
    def test_windows_preflight_prevents_partial_write_and_no_output_needs_no_library(self):
        helper = ROOT / 'tools/apps/urq/copy_urq_library.ps1'
        games, licenses, outside = self.output / 'Games', self.output / 'licenses', self.output / 'external'
        put(outside, 'LICENSE.txt', b'outside sentinel')
        stale = put(games, 'house_that_jack_built/game.urq', b'stale sentinel')
        licenses.mkdir()
        (licenses / 'semion_escape').symlink_to(outside, target_is_directory=True)
        process = subprocess.run(['pwsh', '-NoLogo', '-NoProfile', '-File', str(helper), '-ProjectRoot', str(ROOT),
                                  '-LibraryOutput', str(games), '-LicensesOutput', str(licenses)], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('Unsafe URQ distribution link', process.stderr)
        self.assertEqual(stale.read_bytes(), b'stale sentinel')
        self.assertEqual((outside / 'LICENSE.txt').read_bytes(), b'outside sentinel')
        self.assertFalse((games / 'autoexec.wbmp').exists())
        process = subprocess.run(['pwsh', '-NoLogo', '-NoProfile', '-File', str(helper),
                                  '-ProjectRoot', str(self.output / 'nonexistent')], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == '__main__':
    unittest.main()
