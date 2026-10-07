#!/usr/bin/env python3
"""Exercise the production CMD_RUN dispatcher with terminal/core adapters."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'code/terminal.cpp').read_text()
start=source.index('          case  CMD_RUN: {')
end=source.index('          case CMD_OPEN:',start)
body=source[start:end]
prelude=r'''
#include "terminal_core.hpp"
#include "terminal_protocol.hpp"
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
using terminal_protocol::Result;
using terminal_protocol::ResultKind;
constexpr int CMD_RUN=1;
enum class sw : u8 {F,NEG,RET,RUN};
namespace core_61 { static usize steps=105; static bool running=false;
usize program_steps(){return steps;} bool is_RUN(){return running;} }
namespace program_load { static bool failed=false;
bool blocked(){return failed;} const char* error(){return "load blocked";} }
namespace kbd { static std::vector<i8> keys; void push(i8 key){keys.push_back(key);} }
static std::vector<u8> starts;
static std::vector<std::string> opens;
static int start_hooks=0;
void hidden_start_loaded_program(u8 address){starts.push_back(address);core_61::running=true;}
void mk61_program_started(){assert(core_61::running);++start_hooks;}
bool OpenStoredFile(u16,const char* args){opens.emplace_back(args);return true;}
struct {std::string text;void println(const char* s){text+=s;text+='\n';}} Serial;
class class_terminal {
 public:
  usize recive_pos=10;u16 current_directory=0;const char* args="";
  const char* command_args(){return args;}
  Result script_action(ResultKind kind,const char* argument){recive_pos=0;return Result::action(kind,argument);}
  Result execute(bool script_mode,bool trap_mode){switch(CMD_RUN){
'''
postlude=r'''
}return Result::ok();}
};
static void reset(){core_61::steps=105;core_61::running=false;program_load::failed=false;kbd::keys.clear();starts.clear();opens.clear();start_hooks=0;Serial.text.clear();}
static Result dispatch(const char* arg,bool script=false,bool trap=false){class_terminal terminal;terminal.args=arg;return terminal.execute(script,trap);}
int main(){
  reset();assert(dispatch("").kind==ResultKind::OK);
  assert((kbd::keys==std::vector<i8>{(i8)sw::F,(i8)sw::NEG,(i8)sw::RET,(i8)sw::RUN}));
  assert(starts.empty() && start_hooks==0);
  reset();auto r=dispatch("",true);assert(r.kind==ResultKind::RUN_PROGRAM && r.key==0 && r.args[0]==0);
  for(const char* address:{"8","08","104"}){
    reset();assert(dispatch(address).kind==ResultKind::OK);
    assert(starts.size()==1 && starts[0]==(std::strcmp(address,"104")==0?104:8));
    assert(start_hooks==1 && kbd::keys.empty() && opens.empty());
    reset();r=dispatch(address,true);assert(r.kind==ResultKind::RUN_PROGRAM && r.key==(std::strcmp(address,"104")==0?104:8));
    assert(starts.empty() && start_hooks==0 && kbd::keys.empty());
  }
  for(const char* address:{"105","112","-1","+8","9999999999999999999"}){
    reset();assert(dispatch(address).kind==ResultKind::ERROR);
    assert(starts.empty() && opens.empty() && kbd::keys.empty());
    reset();assert(dispatch(address,true).kind==ResultKind::ERROR);
  }
  reset();core_61::steps=112;r=dispatch("111",true);assert(r.kind==ResultKind::RUN_PROGRAM && r.key==111);
  assert(dispatch("112",true).kind==ResultKind::ERROR);
  for(const char* name:{"GAME","8.m61","dir/8"}){
    reset();assert(dispatch(name).kind==ResultKind::OK && opens==std::vector<std::string>{name});
    reset();r=dispatch(name,true);assert(r.kind==ResultKind::OPEN_FILE && std::strcmp(r.args,name)==0);
    assert(starts.empty() && opens.empty());
  }
  reset();r=dispatch(":loop",true);assert(r.kind==ResultKind::GOTO_LABEL && std::strcmp(r.args,"loop")==0);
  assert(dispatch(":loop").kind==ResultKind::ERROR);
  r=dispatch(":loop",true,true);assert(r.kind==ResultKind::GOTO_LABEL);
  for(const char* arg:{"","8","GAME"}){reset();assert(dispatch(arg,true,true).kind==ResultKind::ERROR);assert(starts.empty() && opens.empty());}
  reset();program_load::failed=true;assert(dispatch("8",true).kind==ResultKind::ERROR && starts.empty());
  assert(dispatch("8").kind==ResultKind::ERROR && starts.empty() && kbd::keys.empty());
}
'''
with tempfile.TemporaryDirectory(prefix='mk61-terminal-run-') as temp:
    cpp=Path(temp)/'test.cpp';exe=Path(temp)/'test'
    cpp.write_text(prelude+body+postlude)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS')=='1' else []
    subprocess.run(['clang++','-std=c++17','-Wall','-Wextra','-Werror',*flags,'-I',str(ROOT/'code'),str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
print('terminal CMD_RUN production dispatcher: addresses, files, default, labels and guards PASS')
