#!/usr/bin/env python3
"""Exercise ELF help export and the production print_help with failing C5 reads."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('help_export', ROOT/'tools/.mk61-app/build_terminal_help.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def elf_metadata(content, flags=0):
    names = b'\0.shstrtab\0.mk61_help\0'
    header = struct.pack('<16sHHIIIIIHHHHHH', b'\x7fELF\x01\x01\x01'+bytes(9), 2, 40, 1,
                         0, 0, 52, 0, 52, 0, 0, 40, 3, 1)
    start = 52 + 3*40
    sections = bytes(40) + struct.pack('<10I', 1,3,0,0,start,len(names),0,0,1,0)
    sections += struct.pack('<10I', 11,1,flags,0,start+len(names),len(content),0,0,1,0)
    return header + sections + names + content


class HelpTest(unittest.TestCase):
    def test_export(self):
        # The 1400-byte boundary cuts a multibyte character unless adjusted.
        body = ('A'*1399 + 'я' + 'B'*1200).encode()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); elf = root/'resident.elf'
            elf.write_bytes(elf_metadata(body+b'\0'))
            result = export.build(elf, root)
            pages = [(root/f'HELP{i}.TXT').read_bytes() for i in (0,1)]
            self.assertEqual(pages[0][9:]+pages[1][9:], body)
            self.assertEqual(pages[0][:9], pages[1][:9])
            self.assertEqual(pages[0][:9], (result['tag']+'\n').encode())
            for page in pages:
                page.decode('utf8'); self.assertLessEqual(len(page), 1536)
            for content,flags in ((body+b'\0',2), (b'missing terminator',0),
                                  (b'x\0y\0',0), (b'x'*2801+b'\0',0), (b'\xff\0',0)):
                elf.write_bytes(elf_metadata(content,flags))
                with self.assertRaises(ValueError): export.build(elf, root)

    def test_reader(self):
        source = (ROOT/'code/terminal.cpp').read_text()
        start = source.index('void class_terminal::print_help(void)')
        end = source.index('\n#if MK61_CRASH_DUMP_SUPPORTED', start)
        prelude = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
using u8=uint8_t; using u16=uint16_t; using usize=size_t;
#define MK61_ENABLE_PORTABLE_APPS 1
static std::vector<std::string> files;
static bool busy=false, fail_body=false;
struct Output {
  std::string text;
  void print(const char* s) { text+=s; }
  void println(const char* s) { text+=s; text+='\n'; }
  void write(char c) { text+=c; }
  void write(const u8* p, usize n) { text.append((const char*)p,n); }
} Serial;
namespace program_store {
constexpr u16 ROOT_ID=0;
enum class ProgramType { TEXT };
struct Entry { u16 id, data_len; };
bool read_range_id(u16 id,u16 offset,u8* out,usize wanted,u16* count) {
  if(busy || (fail_body && offset>=9)) return false;
  auto chunk=files.at(id).substr(offset,wanted);
  memcpy(out,chunk.data(),chunk.size()); *count=chunk.size(); return true;
}
}
namespace storage_path {
enum class Status { OK, MISSING };
Status resolve_file(u16,const char* path,program_store::ProgramType,program_store::Entry& out) {
  assert(std::string(path)=="/System/HELP0.TXT" || std::string(path)=="/System/HELP1.TXT");
  unsigned i=path[12]-'0';
  if(i>=files.size()) return Status::MISSING;
  out={(u16)i,(u16)files[i].size()}; return Status::OK;
}
}
namespace terminal_catalog {
const char* help_signature() { return "1234abcd\n"; }
struct Command { const char* name; };
constexpr usize count() { return 3; }
Command at(usize i) { const char* names[]={"help","dfu","fsput"}; return {names[i]}; }
}
class class_terminal { public: void print_help(); };
'''
        checks = r'''
int main() {
  class_terminal terminal;
  const std::string tag=terminal_catalog::help_signature();
  for(int mode=0;mode<6;++mode) {
    files={tag+"first page\n",tag+"second page\n"};
    busy=mode==4; fail_body=mode==5; Serial.text.clear();
    if(mode==1) files.pop_back();
    if(mode==2) files[1][0]='0';
    if(mode==3) files[1]="short";
    terminal.print_help();
    if(mode==0) assert(Serial.text=="Available commands:\nfirst page\nsecond page\n");
    else if(mode==5) assert(Serial.text=="Available commands:\nHELP read error\n");
    else {
      assert(Serial.text.find("help dfu fsput ")!=std::string::npos);
      assert(Serial.text.find("fsput begin /System/<file> <size> <crc32>")!=std::string::npos);
      assert(Serial.text.find("first page")==std::string::npos);
    }
  }
}
'''
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cpp=root/'test.cpp'; exe=root/'test'
            cpp.write_text(prelude+source[start:end]+checks)
            flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS')=='1' else []
            subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',*flags,str(cpp),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

if __name__=='__main__': unittest.main()
