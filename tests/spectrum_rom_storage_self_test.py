"""APP assets are SD files; obsolete Flash packs never survive a rebuild."""
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'dev/tools'))
from tools.apps.spectrum.build_spectrum_app import copy_assets,SOURCES

class RomStorageTests(unittest.TestCase):
 def test_sd_bundle_replaces_only_obsolete_generated_pack(self):
  with tempfile.TemporaryDirectory(prefix='spectrum-sd-rom-')as tmp:
   folder=Path(tmp)
   for name in ('ROMCACHE.uf2','rom-cache.json','user-file.keep'):(folder/name).write_bytes(b'old output')
   copy_assets(folder)
   for name in ('48.rom','128-0.rom','128-1.rom'):
    self.assertEqual((folder/name).read_bytes(),(ROOT/'third_party/spectrum-rom'/name).read_bytes())
    self.assertEqual((folder/name).stat().st_size,16384)
   self.assertFalse((folder/'ROMCACHE.uf2').exists());self.assertFalse((folder/'rom-cache.json').exists())
   self.assertEqual((folder/'user-file.keep').read_bytes(),b'old output')
   self.assertFalse(any(p.suffix.lower()=='.uf2'for p in folder.rglob('*')))
 def test_runtime_has_no_flash_asset_reader(self):
  self.assertNotIn('examples/portable-apps/SPECTRUM/rom_cache.c',SOURCES)
  for name in SOURCES:
   source=(ROOT/name).read_text()
   self.assertNotIn('SPECTRUM_ROM_CACHE_ADDRESS',source)
   self.assertNotIn('spectrum_rom_cache_find',source)
   self.assertNotIn('0x101C0000',source.upper().replace('0X','0x'))

if __name__=='__main__':unittest.main()
