#!/usr/bin/env python3
"""Verify native artwork with the production WBMP/FMK decoders and compact hashes."""
import hashlib,json,re,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_picocalc_game_assets import bee_font


def main():
    records=json.loads((ROOT/'doc/game-artwork/native/manifest.json').read_text())
    assert len(records)==15
    for record in records:
        path=ROOT/record['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==record['sha256']
        compact=path.with_name(path.name.replace('-320.wbmp','.wbmp'))
        assert hashlib.sha256(compact.read_bytes()).hexdigest()==record['compact_sha256']
        assert 0<record['width']<=320 and 0<record['height']<=224 and path.stat().st_size<=16384
        if record['source'].startswith('doc/'):
            assert hashlib.sha256((ROOT/record['source']).read_bytes()).hexdigest()==record['source_sha256']
    face=ROOT/'programs/games/Bumblebee/Bumblebee320.FMK';assert face.read_bytes()==bee_font()
    script=(face.parent/'autoexec.m61').read_text()
    assert 'RE= 0\nopen? display.tbi\nif re==0 run :ready\nloadfont Bumblebee320\n:ready\n' in script
    assert script.count('trap 21 ')==1 and script.count('trap 33 ')==1
    assert re.findall(r'^hin (.+)$',script,re.M)==['0000 0D400207021D5923600110400103115919270060155102600111400111591760155102']
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory);source=work/'decode.cpp';exe=work/'decode'
        source.write_text(r'''
#include "wbmp.hpp"
#include "fmk_font.hpp"
#include <cassert>
#include <fstream>
#include <vector>
#include <cstring>
int main(int argc,char** argv) {
 for(int i=1;i<argc;++i) {
  std::ifstream file(argv[i],std::ios::binary);assert(file.good());
  std::vector<u8> bytes{std::istreambuf_iterator<char>(file),{}};
  if(std::strstr(argv[i],".FMK")) {
   fmk::Face face;assert(face.open(bytes.data(),bytes.size()));
   assert(face.metrics().height==32 && face.metrics().default_advance==16 && face.metrics().glyph_count==4);
   for(unsigned cp:{32,45,48,56}) { fmk::Glyph g{};u8 out[fmk::MAX_BITMAP_SIZE]{};
    assert(face.glyph(cp,g) && face.decode(g,out,sizeof(out)) && g.width==16 && g.height==32);
    unsigned ink=0;for(u8 byte:out) ink+=__builtin_popcount(byte);assert(cp==32?ink==0:ink>0);
   }
  } else {
   wbmp::Info info{};assert(wbmp::inspect(bytes.data(),bytes.size(),info)==wbmp::Status::OK);
   u8 frame[12802];std::memset(frame,0xA5,sizeof(frame));
   assert(wbmp::decode_viewport(bytes.data(),bytes.size(),info,0,0,320,320,wbmp::Layout::PAGE_MAJOR_LSB,frame+1,12800)==wbmp::Status::OK);
   assert(frame[0]==0xA5 && frame[12801]==0xA5);
   unsigned ink=0;for(unsigned at=1;at<=12800;++at) ink+=__builtin_popcount(frame[at]);assert(ink>10 && ink<320*240);
   for(unsigned y=info.height;y<320;++y) for(unsigned x=0;x<320;++x) assert(!(frame[1+y/8*320+x]&(1U<<(y%8))));
   if(std::strstr(argv[i],"Bumblebee/scene-320")) assert(!wbmp::dark_pixel(bytes.data(),bytes.size(),info,0,0));
  }
 }
}
''')
        subprocess.run(['clang++','-std=c++17','-O2','-I'+str(ROOT/'code'),str(source),
            str(ROOT/'code/wbmp.cpp'),str(ROOT/'code/fmk_font.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe),*[str(ROOT/r['path']) for r in records],str(face)],check=True)
    print('PASS 15 native WBMPs, polarity/padding/viewport bounds, immutable compact images, FMK decode and original Bumblebee ROM')


if __name__=='__main__':main()
