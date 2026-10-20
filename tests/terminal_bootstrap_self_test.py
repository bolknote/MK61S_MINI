#!/usr/bin/env python3
"""Exercise the resident command bridge before /System exists and on failure."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'code/terminal_command_resident.inc').read_text()
bridge = source[source.index('terminal_protocol::Result class_terminal::exec_external('):]
fixture = r'''
#include <cassert>
#include <cstdio>
#include <string>
#include "terminal_command_driver.hpp"
#include "terminal_command_ids.hpp"
#include "terminal_protocol.hpp"
#include "terminal_core.hpp"
#include "terminal_output.hpp"
#include "loadable_app_api.h"
#include "app_flow.h"
struct Printer {
  std::string text;
  void print(const char* p){text+=p;}
  void println(){text+="\r\n";}
  void println(const char* p){print(p);println();}
} Serial;
namespace program_store {
enum class ProgramType : u8 { APP=8 };
enum class MountStatus { UNAVAILABLE,FORMAT_REQUIRED,REPAIR_REQUIRED };
constexpr u16 ROOT_ID=0xFFFF;
struct Entry {u16 id;};
}
namespace storage_path {
enum class Status : u8 { OK,NOT_FOUND };
static bool installed=false;
static std::string path;
Status resolve_file(u16 root,const char* p,program_store::ProgramType type,program_store::Entry& out) {
  assert(root==program_store::ROOT_ID && type==program_store::ProgramType::APP);
  path=p;out.id=42;return installed?Status::OK:Status::NOT_FOUND;
}
}
namespace terminal_command_driver {
const Services services={};
static StorageInfo info={};
StorageInfo storage_info(){return info;}
void help_fallback(){Serial.println("bootstrap help: fsput fsls identity");}
}
namespace loadable_module {
enum class RuntimeStatus {OK,BUSY,INVALID_MODULE};
static RuntimeStatus status=RuntimeStatus::OK;
static u32 answer=1,calls=0;
const char* status_text(RuntimeStatus){return "another app is active";}
RuntimeStatus run_flow(mk61_app_flow_target target,void* raw,u32 size,u32& result) {
  assert(target.kind==MK61_APP_KIND_APPLICATION && target.file_id==42);
  assert(target.phase==terminal_command_driver::EXECUTE && target.flags==MK61_APP_FLOW_DIRECT);
  assert(size==16 && ((u32*)raw)[1]==sizeof(terminal_command_driver::Request));
  ++calls;result=answer;return status;
}
}
class class_terminal {
public:
  static constexpr u32 HISTORY_TEXT_SIZE=256,HISTORY_DEPTH=8;
  inline static u8 hist_head=0,hist_count=0,hist_length[8]={},input_buffer[240]={};
  inline static u16 hist_start[8]={};
  inline static char hist_text[256]={};
  u16 current_directory=0xFFFF;
  isize AT=73;
  const char* arguments="";
  const char* command_args(){return arguments;}
  terminal_protocol::Result exec_external(u8);
};
'''
checks = r'''
int main() {
  using namespace terminal_protocol;
  using namespace terminal_command_driver;
  using namespace program_store;
  class_terminal terminal;
  auto run=[&](u8 command){Serial.text.clear();return terminal.exec_external(command).kind;};
  assert(run(CMD_HELP)==ResultKind::OK && Serial.text.find("fsput")!=std::string::npos);
  assert(run(CMD_DATE)==ResultKind::ERROR && storage_path::path=="/System/CLOCK.APP");
  assert(Serial.text=="Install matching /System/CLOCK.APP\r\n");
  assert(run(CMD_ASM)==ResultKind::ERROR && storage_path::path=="/System/TERMINAL.APP");
  info.mount_status=(u32)MountStatus::FORMAT_REQUIRED;
  assert(run(CMD_FS_STAT)==ResultKind::OK && Serial.text.find("run format")!=std::string::npos);
  info.mount_status=(u32)MountStatus::REPAIR_REQUIRED;
  assert(run(CMD_FS_STAT)==ResultKind::OK && Serial.text.find("catalog damaged")!=std::string::npos);
  info={1,0,524288,12,1024,10,2,512,128,1};
  assert(run(CMD_FS_STAT)==ResultKind::OK && Serial.text.find("1012 free")!=std::string::npos);
  assert(loadable_module::calls==0);
  terminal.arguments="wrong";
  assert(run(CMD_FS_STAT)==ResultKind::ERROR && Serial.text=="Usage: df\r\n");
  terminal.arguments="";storage_path::installed=true;
  assert(run(CMD_ALARM)==ResultKind::OK && storage_path::path=="/System/CLOCK.APP");
  loadable_module::answer=0;
  assert(run(CMD_HIN)==ResultKind::ERROR);
  loadable_module::status=loadable_module::RuntimeStatus::BUSY;
  assert(run(CMD_LIST)==ResultKind::ERROR && Serial.text.find("another app is active")!=std::string::npos);
  assert(terminal.AT==73);
}
'''
with tempfile.TemporaryDirectory(prefix='mk61-terminal-bootstrap-') as directory:
    path = Path(directory)
    cpp = path / 'test.cpp'
    cpp.write_text(fixture + bridge + checks)
    flags = (['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
             if os.environ.get('MK61_TEST_SANITIZERS') == '1' else [])
    subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                    *flags, '-I'+str(ROOT/'code'), str(cpp), '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True)
print('terminal bootstrap: absent System, damaged C9, disk report, helper selection and busy APP PASS')
