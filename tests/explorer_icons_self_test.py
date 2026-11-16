#!/usr/bin/env python3
"""Stock folder coverage and actual distribution-copy contract, without a device."""

# Resolve shared host helpers independently of the current command directory.
import sys as _tool_sys
from pathlib import Path as _ToolPath
_tool_root = _ToolPath(__file__).resolve().parents[1]
_tool_sys.path[:0] = [str(_tool_root), str(_tool_root / "dev/lib"), str(_tool_root / "dev/tools")]
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import explorer_icons as icons
sys.path.insert(0,str(ROOT/'tools/games'))
from tools.apps.another import build_another_app
from tools.games import manager
from another_world_cache_tools_self_test import compressed


class IconTests(unittest.TestCase):
    def test_another_builder_adds_icon_but_keeps_a_custom_one(self):
        with tempfile.TemporaryDirectory(prefix='mk61-another-icon-build-') as temporary:
            root=Path(temporary);build=root/'build';output=root/'out';build.mkdir()
            (build/'ANOTHER.APP').write_bytes(b'app fixture')
            (build/'ANOTHER.json').write_text('{}')
            argv=['build_another_app.py','--build-dir',str(build),'--output-dir',str(output)]
            with mock.patch.object(sys,'argv',argv), mock.patch.object(build_another_app,'compiler_bin',return_value=root), \
                 mock.patch.object(build_another_app.subprocess,'run'):
                build_another_app.main()
                self.assertEqual((output/'autoexec.wbmp').read_bytes(),icons.draw('another-world'))
                (output/'autoexec.wbmp').rename(output/'AUTOEXEC.WBMP')
                (output/'AUTOEXEC.WBMP').write_bytes(b'personal icon')
                build_another_app.main()
                self.assertEqual((output/'AUTOEXEC.WBMP').read_bytes(),b'personal icon')
                self.assertEqual([p.name for p in output.iterdir() if p.name.casefold()=='autoexec.wbmp'],['AUTOEXEC.WBMP'])

    def test_another_downloaders_add_icon_but_keep_a_custom_one(self):
        with tempfile.TemporaryDirectory(prefix='mk61-another-icon-download-') as temporary:
            root=Path(temporary)
            listing=bytearray(41);listing[7]=listing[27]=1
            listing[14:16]=listing[18:20]=(24).to_bytes(2,'big')
            listing[28:32]=(32).to_bytes(4,'big');listing[34:36]=(16).to_bytes(2,'big')
            listing[38:40]=(24).to_bytes(2,'big');listing[40]=0xff
            bank=bytearray(64);bank[:24]=bytes(range(1,25));bank[32:48]=compressed()
            data={'MEMLIST.BIN':bytes(listing),'BANK01':bytes(bank)}
            archive=root/'cache/archives/fixture.zip';archive.parent.mkdir(parents=True)
            with zipfile.ZipFile(archive,'w') as z:
                for name,contents in data.items():z.writestr(name,contents)
            sha=lambda blob:hashlib.sha256(blob).hexdigest()
            folder='sd/Games/Another World'
            item={'id':'fixture','title':'Fixture','runner':'download_zip','source_page':'local',
                  'url':'https://example.invalid/fixture.zip','archive_name':'fixture.zip',
                  'sha256':sha(archive.read_bytes()),'rights':'fixture',
                  'prepared_cache':folder,'folder_icon':'doc/explorer-icons/another-world.wbmp',
                  'members':[{'source':name,'target':folder+'/'+name,'bytes':len(contents),
                              'sha256':sha(contents)} for name,contents in data.items()]}
            catalog={'format':1,'items':[item]}
            shell=shutil.which('pwsh') or shutil.which('powershell')
            fake=root/'repo';(fake/'tools/games').mkdir(parents=True)
            for name in ('games.ps1','another_cache.ps1'):
                shutil.copy2(ROOT/'tools/games'/name,fake/'tools/games'/name)
            (fake/'tools/games/catalog.json').write_text(json.dumps(catalog))
            (fake/'doc/explorer-icons').mkdir(parents=True)
            shutil.copy2(icons.ARTWORK/'another-world.wbmp',fake/'doc/explorer-icons/another-world.wbmp')
            for implementation in ('python','powershell'):
                if implementation=='powershell' and not shell:continue
                output=root/implementation
                def run():
                    if implementation=='python':
                        manager.execute(catalog,['fixture'],output,root/'cache',dry_run=False)
                    else:
                        subprocess.run([shell,'-NoProfile','-File',str(fake/'tools/games/games.ps1'),
                                        'run','--select','fixture','--output-root',str(output),
                                        '--cache-root',str(root/'cache')],check=True,capture_output=True)
                run()
                icon=output/folder/'autoexec.wbmp'
                self.assertEqual(icon.read_bytes(),icons.draw('another-world'),implementation)
                self.assertTrue((output/folder/'AWCACHE.BIN').exists())
                icon.rename(icon.with_name('AUTOEXEC.WBMP'))
                icon.with_name('AUTOEXEC.WBMP').write_bytes(b'personal icon')
                run()
                self.assertEqual([p.name for p in icon.parent.iterdir() if p.name.casefold()=='autoexec.wbmp'],['AUTOEXEC.WBMP'])
                self.assertEqual(icon.with_name('AUTOEXEC.WBMP').read_bytes(),b'personal icon')

    def test_all_program_folders_have_reviewed_current_artwork(self):
        icons.generate(check=True)
        folders={p.relative_to(ROOT/'programs').as_posix() for p in (ROOT/'programs').rglob('*') if p.is_dir()}
        self.assertEqual(folders,set(icons.PROGRAM_FOLDERS))
        for folder,role in icons.PROGRAM_FOLDERS.items():
            self.assertEqual((ROOT/'programs'/folder/'autoexec.wbmp').read_bytes(),
                             (icons.ARTWORK/(role+'.wbmp')).read_bytes(),folder)

    def test_distinct_drawings_have_padding_and_exact_native_dimensions(self):
        drawings=[]
        for role in sorted(set(icons.BUNDLE_FOLDERS.values())):
            with self.subTest(role=role):
                data=icons.validate((icons.ARTWORK/(role+'.wbmp')).read_bytes())
                self.assertEqual(data,icons.draw(role))
                foreground=[(x,y) for y in range(32) for x in range(32)
                            if not data[4+y*4+x//8]&(0x80>>(x%8))]
                self.assertTrue(40<len(foreground)<700)
                self.assertTrue(all(0<x<31 and 0<y<31 for x,y in foreground))
                drawings.append(data)
        self.assertEqual(len(drawings),len(set(drawings)))

    def test_local_bundle_contains_icons_for_existing_stock_folders_only(self):
        with tempfile.TemporaryDirectory(prefix='mk61-folder-icons-') as temporary:
            root=Path(temporary)
            for folder in icons.BUNDLE_FOLDERS:(root/folder).mkdir(parents=True,exist_ok=True)
            personal=root/'personal';personal.mkdir();(personal/'notes.txt').write_text('keep')
            copied=icons.install_bundle_icons(root)
            self.assertEqual(len(copied),len(icons.BUNDLE_FOLDERS))
            self.assertFalse((personal/'autoexec.wbmp').exists())
            self.assertEqual((personal/'notes.txt').read_text(),'keep')
            for folder,role in icons.BUNDLE_FOLDERS.items():
                self.assertEqual((root/folder/'autoexec.wbmp').read_bytes(),icons.draw(role))
            self.assertEqual({p.name for p in root.rglob('*') if p.is_file()}, {'autoexec.wbmp','notes.txt'})
            empty=root/'empty';empty.mkdir()
            self.assertEqual(icons.install_bundle_icons(empty),[])
            self.assertEqual(list(empty.iterdir()),[])

    def test_stm32_capitalized_apps_uses_the_same_icon(self):
        with tempfile.TemporaryDirectory(prefix='mk61-folder-icons-') as temporary:
            root=Path(temporary);(root/'Apps').mkdir()
            self.assertEqual(icons.install_bundle_icons(root),[root/'Apps/autoexec.wbmp'])
            self.assertEqual((root/'Apps/autoexec.wbmp').read_bytes(),icons.draw('applications'))

    def test_stm32_capitalized_games_and_urq_keep_actual_spelling(self):
        with tempfile.TemporaryDirectory(prefix='mk61-folder-icons-') as temporary:
            root=Path(temporary)
            game=root/'Games/URQ/house_that_jack_built'
            game.mkdir(parents=True)
            expected=[root/'Games/autoexec.wbmp',root/'Games/URQ/autoexec.wbmp',game/'autoexec.wbmp']
            self.assertEqual(icons.install_bundle_icons(root),expected)
            for path in expected:self.assertEqual(path.read_bytes(),icons.draw('games'))
            # A canonical role name must not create another physical directory.
            self.assertEqual({p.name for p in root.iterdir()},{'Games'})


if __name__=='__main__':unittest.main()
