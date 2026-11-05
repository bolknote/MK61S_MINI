#!/usr/bin/env python3
"""Stock folder coverage and actual distribution-copy contract, without a device."""

# Resolve shared host helpers independently of the current command directory.
import sys as _tool_sys
from pathlib import Path as _ToolPath
_tool_root = _ToolPath(__file__).resolve().parents[1]
_tool_sys.path[:0] = [str(_tool_root / "tools"), str(_tool_root / "dev/lib"), str(_tool_root / "dev/tools")]
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import explorer_icons as icons


class IconTests(unittest.TestCase):
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


if __name__=='__main__':unittest.main()
