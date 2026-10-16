#!/usr/bin/env python3
"""Compile production IF/parser/script wrapper against the pre-optimization path.

Only terminal actions and calculator register I/O are adapters. The catalog,
operand reader, condition parser, interactive IF, and script wrapper are real.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'code/terminal.cpp').read_text()
def method(name):
    marker='class_terminal::'+name+'('
    at=source.index(marker);start=source.rfind('\n',0,at)+1
    end=source.index('{',at);depth=1;end+=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]+'\n'

prelude=r'''
#include "terminal_core.hpp"
#include "terminal_protocol.hpp"
#include "terminal_catalog.hpp"
#include "terminal_script.hpp"
#include "dwt_profiler.hpp"
#include <cassert>
#include <cstring>
#include <string>
#include <vector>
#include <cstdio>
using terminal_protocol::Result;using terminal_protocol::ResultKind;
constexpr usize MAX_INPUT_CHAR=terminal_core::INPUT_CAPACITY;constexpr u8 CR=13;
enum class stack {X1,X,Y,Z,T};
namespace core_61 {static bool expanded=false;bool expanded_program_is_on(){return expanded;}}
namespace m61_text {static bool suspended=false;bool calculator_suspended(){return suspended;}}
static const char* terminal_symbols="0123456789";
static const char* regtext=" 0.0000000  00";static unsigned reads=0;
static unsigned cancellations=0,idle_resets=0,dispatches=0;
static std::vector<std::string> opens;
static bool open_succeeds=true;
bool OpenStoredFile(u16,const char* args){opens.emplace_back(args);return open_succeeds;}
void idle_signal_reset(){++idle_resets;}
int HexdecimalDigit(char c){if(c>='0'&&c<='9')return c-'0';if((c|32)>='a'&&(c|32)<='f')return (c|32)-'a'+10;return -1;}
void MK61Emu_ReadRegister(int,char* out,const char*){++reads;std::memcpy(out,regtext,15);}
const char* read_stack_register(stack,char* out,const char*){++reads;std::memcpy(out,regtext,15);return out;}
// This suite compares script/interactive dispatch and the exact legacy fallback.
// The physical numeric fast path is covered by mk61_number_self_test instead.
namespace mk61_ref {
 bool try_read_register_number(int,double&){return false;}
 bool try_read_stack_number(stack,double&){return false;}
}
struct {std::string text;void println(const char* s){text+=s;text+='\n';}} Serial;
class class_terminal {
 public:
  static u8 input_buffer[MAX_INPUT_CHAR];usize recive_pos=0;bool legacy=false;u16 current_directory=0;
  static bool operand_delimiter(char);static bool parse_if_operand(const char*&,double&);
  static bool parse_if_condition(const char*&,bool&);static bool parse_mk_display_value(const char*,double&);
  static u8 parse_if_reference(const char*&);static bool read_if_reference(u8,double&);
  static u8 parse_if_operator(const char*&);static bool compare_if(u8,double,double);
  static bool prepare_script_if(const char*,terminal_script::PreparedIf&,u8&);
  terminal_script::IfResult evaluate_script_if(const terminal_script::PreparedIf&,bool);
  const char* command_args();Result exec_if(bool,bool);Result execute_script_line(const char*,bool);
  Result legacy_if(bool,bool);Result legacy_script(const char*,bool);Result execute(bool,bool);
  Result script_action(ResultKind,const char*);
  void cancel_file_upload(){++cancellations;}
};
u8 class_terminal::input_buffer[MAX_INPUT_CHAR]={};
'''

# Frozen semantics of the old implementation, deliberately independent of the
# new condition parser and read-only prefix loop.
legacy=r'''
Result class_terminal::legacy_if(bool script,bool trap){
 const char* p=command_args();double lhs=0,rhs=0;bool parsed=parse_if_operand(p,lhs);
 char op0=0,op1=0;
 if(parsed){p=terminal_core::skip_spaces(p);op0=p[0];if(op0=='>'||op0=='<'||op0=='='||op0=='!'){++p;if(*p=='='){op1='=';++p;}}
 parsed=(op0=='>'||op0=='<')||((op0=='='||op0=='!')&&op1=='=');}
 if(parsed)parsed=parse_if_operand(p,rhs);
 const char* tail=terminal_core::skip_spaces(p);
 if(!parsed||!*tail){recive_pos=0;Serial.println("Usage: if <x|y|z|t|x1|r0..re> <op> <value> <command>");return Result::error();}
 bool condition=false;
 if(op0=='>')condition=op1?lhs>=rhs:lhs>rhs;
 if(op0=='<')condition=op1?lhs<=rhs:lhs<rhs;
 if(op0=='=')condition=lhs==rhs;if(op0=='!')condition=lhs!=rhs;
 if(!condition){recive_pos=0;return Result::ok();}
 usize offset=tail-(const char*)input_buffer,n=std::strlen(tail);
 std::memmove(input_buffer,tail,n);input_buffer[n]=CR;recive_pos=n+1;
 auto result=execute(script,trap);
 if(!terminal_core::restore_conditional_argument_offset(input_buffer,MAX_INPUT_CHAR,offset,n,result.args))return Result::error();
 return result;
}
Result class_terminal::legacy_script(const char* line,bool trap){
 if(!line)return Result::error();u8 saved[MAX_INPUT_CHAR];std::memcpy(saved,input_buffer,sizeof(saved));
 auto result=Result::error();usize n=0;bool too_long=false;
 while(line[n]){if(!terminal_core::input_can_append(n)){too_long=true;break;}input_buffer[n]=(u8)line[n];++n;}
 if(too_long)recive_pos=0;else{input_buffer[n]=CR;recive_pos=n+1;result=execute(true,trap);}
 if(!terminal_core::rebind_script_argument(line,n,input_buffer,MAX_INPUT_CHAR,result.args))result=Result::error();
 std::memcpy(input_buffer,saved,sizeof(saved));return result;
}
Result class_terminal::execute(bool script,bool trap){
 ++dispatches;
 if(!recive_pos||recive_pos>MAX_INPUT_CHAR)return Result::error();
#if defined(MK61_OLED1602_WS0010)
 idle_signal_reset();
#endif
 input_buffer[--recive_pos]=0;
 trap=trap||m61_text::calculator_suspended();const u8 cmd=terminal_catalog::lookup(input_buffer);
 if((script&&!terminal_command_allowed_in_script(cmd))||(trap&&!terminal_command_allowed_in_trap(cmd))){recive_pos=0;return Result::error();}
 if(cmd!=CMD_FS_PUT)cancel_file_upload();
 if(cmd==CMD_IF)return legacy?legacy_if(script,trap):exec_if(script,trap);
 const char* args=command_args();recive_pos=0;
 // PRODUCTION_OPEN_DISPATCH
 if(cmd==CMD_RUN)return Result::action(ResultKind::GOTO_LABEL,args);
 if(cmd==CMD_RET)return Result::action(ResultKind::RETURN_SCRIPT,args);
 if(cmd==CMD_PRINT)return Result::action(ResultKind::OK,args);
 return Result::error();
}
struct Snapshot{ResultKind kind;int key,offset;std::string arg,text,buffer;usize position;unsigned reads,cancellations,idle_resets,dispatches;std::vector<std::string> opens;};
static unsigned cases=0;
static Snapshot run(std::string line,bool legacy,bool script,bool trap,bool alias,bool prepared=false){
 class_terminal t;t.legacy=legacy;t.recive_pos=7;
 for(unsigned i=0;i<MAX_INPUT_CHAR;++i)t.input_buffer[i]=(u8)(0x80+i%97);
 const char* input=line.c_str();
 if(alias){assert(line.size()<MAX_INPUT_CHAR);std::memcpy(t.input_buffer,input,line.size()+1);input=(const char*)t.input_buffer;}
 Serial.text.clear();reads=0;cancellations=0;idle_resets=0;dispatches=0;opens.clear();Result result;
 if(script){
  terminal_script::PreparedIf condition={};u8 tail=0;
  if(prepared&&t.prepare_script_if(input,condition,tail)){
   // Preparation is read-only, including a false IF or an unavailable RF.
   assert(reads==0&&cancellations==0&&idle_resets==0&&t.recive_pos==7);
   switch(t.evaluate_script_if(condition,trap)){
    case terminal_script::IfResult::TRUE:result=t.execute_script_line(input+tail,trap);break;
    case terminal_script::IfResult::FALSE:result=Result::ok();break;
    case terminal_script::IfResult::ERROR:result=Result::error();break;
    case terminal_script::IfResult::FALLBACK:result=t.execute_script_line(input,trap);break;
   }
  }else result=legacy?t.legacy_script(input,trap):t.execute_script_line(input,trap);
 }
 else{assert(line.size()<MAX_INPUT_CHAR);std::memcpy(t.input_buffer,input,line.size());t.input_buffer[line.size()]=CR;t.recive_pos=line.size()+1;result=t.execute(false,trap);}
 const uintptr_t a=(uintptr_t)result.args,b=(uintptr_t)input;
 return {result.kind,result.key,a>=b&&a<=b+line.size()?(int)(a-b):-1,std::string(result.args),Serial.text,
         std::string((char*)t.input_buffer,MAX_INPUT_CHAR),t.recive_pos,reads,cancellations,idle_resets,dispatches,opens};
}
static void check(const std::string& line){
 for(bool script:{false,true})for(bool trap:{false,true})for(bool suspended:{false,true})for(bool alias:{false,true}){
  if((!script||alias)&&line.size()>=MAX_INPUT_CHAR)continue;
  m61_text::suspended=suspended;auto a=run(line,true,script,trap,alias);
  for(bool prepared:{false,true}){
  auto b=run(line,false,script,trap,alias,prepared);
  if(!(a.kind==b.kind&&a.key==b.key&&a.offset==b.offset&&a.arg==b.arg&&a.text==b.text&&a.buffer==b.buffer&&a.position==b.position&&a.reads==b.reads&&a.cancellations==b.cancellations&&a.idle_resets==b.idle_resets&&a.opens==b.opens)){
   std::fprintf(stderr,"IF mismatch [%s] script=%d trap=%d suspended=%d alias=%d prepared=%d\n",line.c_str(),script,trap,suspended,alias,prepared);assert(false);
  }++cases;
  }
 }
}
int main(){
 for(const char* text:{" 0.0000000  00","-0.0000000  00"," 1.0000000  00","-1.0000000  00"," 2.7000000  01"," 1.2345678 -99"," F.0000000  00"}){
  regtext=text;
  for(bool expanded:{false,true}){core_61::expanded=expanded;
   for(const char* lhs:{"re","rf","r0","x","x1","y","z","t","0","-0","1.25"})
   for(const char* op:{"==","!=","<","<=",">",">=","=","!","<>","===",""})
   for(const char* rhs:{"0","1","-0","1.25","re","32767","-32768","32768","-32769","1e2","1e99"}){
    check(std::string("if ")+lhs+op+rhs+" open \"some file.tbi\"");
   }
  }
 }
 regtext=" 0.0000000  00";
 for(const char* line:{"","if","if ","if 0==0","if 0==1 bad command","if 0==0 bad command","if 0==0 if 1<2 run :next","if 0==0 if 1>2 bad","if 0==0 open x","if 0==0 dfu","if\t0==0\tprint hi","IF 0==0 open x"," if 0==0 open x","ifx 0==0 open x","if 0==0\r\nopen x","if 0==0 ret"})check(line);
 for(unsigned n:{238U,239U,240U,241U,1000U})for(const char* prefix:{"if 0==0 open ","if 0==1 open ","if re==0 open ","if re==1 open ","open "}){std::string line=prefix;line.resize(n,'a');check(line);}
 std::string nested="open x";for(unsigned n=0;n<24;++n){check(nested);nested="if 0==0 "+nested;}
 for(bool succeeds:{false,true}){open_succeeds=succeeds;
  for(const char* word:{"o","op","ope","open","OPEN","Open","openx","open?","open/"," open","\topen"})
  for(const char* space:{""," ","\t","  \t ","\r","\n"})
  for(const char* path:{"","a.tbi","'some file.foc'","\"unterminated","../x","/x","x\\y","x\rignored","x\nignored"}){
   const std::string line=std::string(word)+space+path;check(line);check("if 0==0 "+line);check("if 0==1 "+line);
  }
 }
 m61_text::suspended=false;
 for(const char* line:{"open x","open\t\"some file.tbi\"","if 0==0 open x","if 0==0 if 1<2 open ../x"}){
  const auto result=run(line,false,true,false,false);
  assert(result.kind==ResultKind::OPEN_FILE&&result.dispatches==0&&result.opens.empty());
 }
 for(const char* line:{"open","open ","open\t\r","OPEN x","openx x"})assert(run(line,false,true,false,false).dispatches==1);
 assert(run("open x",false,true,true,false).dispatches==1);
 m61_text::suspended=true;assert(run("open x",false,true,false,false).dispatches==1);
 std::printf("production IF/script differential: %u cases, buffers/arguments/errors/permissions/reads/cancellation/idle exact PASS\n",cases);
}
'''

production=''.join(method(name) for name in ('command_args','script_action','operand_delimiter','parse_mk_display_value',
    'parse_if_reference','read_if_reference','parse_if_operand','parse_if_operator','compare_if',
    'parse_if_condition','prepare_script_if','evaluate_script_if','exec_if','execute_script_line'))
# Unlike unrelated action adapters, OPEN uses its actual dispatcher case too.
# This checks missing-path diagnostics and the interactive/file-open boundary,
# not a second implementation that could accidentally mirror the shortcut.
open_start=source.index('          case CMD_OPEN: {')
open_end=source.index('          case  CMD_POKE:',open_start)
legacy=legacy.replace('// PRODUCTION_OPEN_DISPATCH',
    'if(cmd==CMD_OPEN){const bool script_mode=script;switch(cmd){'+
    source[open_start:open_end]+'default:break;}return Result::ok();}')
with tempfile.TemporaryDirectory(prefix='mk61-terminal-if-') as directory:
    work=Path(directory);cpp=work/'test.cpp';exe=work/'test'
    cpp.write_text(prelude+production+legacy)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS')=='1' else []
    for backend in (0,1):
        for ws0010 in (False,True):
            display=['-DMK61_OLED1602_WS0010'] if ws0010 else []
            subprocess.run(['clang++','-std=c++17','-O1','-Wall','-Wextra','-Werror',*flags,*display,
                '-DMK61_MATH_BACKEND='+str(backend),'-I'+str(ROOT/'tests/mk_math_shim'),'-I'+str(ROOT/'code'),
                str(cpp),str(ROOT/'code/terminal_catalog.cpp'),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)
