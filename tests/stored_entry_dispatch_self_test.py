#!/usr/bin/env python3
"""Compile the real stored-file dispatcher exhaustively for STM32 feature sets."""
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def block(text,signature):
    start=text.index(signature);brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

enum=block((ROOT/'code/program_store.hpp').read_text(),'enum class ProgramType')+';'
dispatch=block((ROOT/'code/tools.cpp').read_text(),'bool OpenStoredEntry(')
stub=r'''
#include <cassert>
#include <cstdint>
using u16=uint16_t;using u32=uint32_t;using u8=uint8_t;
static unsigned handlers;
int main_lcd(){return 0;}
namespace rtc_idle_clock {void hide(int){}}
namespace program_store { ENUM struct Entry {u16 id;ProgramType type;}; }
namespace m61_text {bool open_program(u16){++handlers;return true;}}
bool RunFocalProgram(u16){++handlers;return true;}bool FocalRunSucceeded(bool b){return b;}
bool RunTinyBasicProgram(u16){++handlers;return true;}
bool program_store_view_entry(const program_store::Entry&){++handlers;return true;}
bool program_store_apply_font(const program_store::Entry&){++handlers;return true;}
namespace loadable_module {
enum class FileOpenResult {OK};enum class RuntimeStatus {OK};
RuntimeStatus run_app(u16,u32&){++handlers;return RuntimeStatus::OK;}
}
namespace file_handlers {
loadable_module::FileOpenResult open(const program_store::Entry&){++handlers;return loadable_module::FileOpenResult::OK;}
}
DISPATCH
int main(){
 using T=program_store::ProgramType;
 for(T type:{T::EXTERNAL_BINARY,T::MK61_BINARY,T::URQ_DATA,T::URQ_SAVE}) {
  assert(!OpenStoredEntry({7,type}) && !handlers);
 }
 assert(OpenStoredEntry({7,T::MARKDOWN}) && handlers==1);
 assert(OpenStoredEntry({7,T::APP})==(bool)MK61_APP_RUNTIME_AVAILABLE);
}
'''.replace('ENUM',enum).replace('DISPATCH',dispatch)
stub=stub.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
with tempfile.TemporaryDirectory(prefix='mk61-stored-dispatch-') as temp:
    folder=Path(temp);source=folder/'test.cpp';source.write_text(stub)
    for enabled in (0,1):
        exe=folder/str(enabled)
        subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wswitch-enum',
                        '-DMK61_ENABLE_FOCAL='+str(enabled),'-DMK61_ENABLE_TINYBASIC='+str(enabled),
                        '-DMK61_APP_RUNTIME_AVAILABLE='+str(enabled),str(source),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
print('Stored dispatcher: all ProgramType values handled; external media rejected without launching a handler; compact/full STM32 feature sets PASS')
