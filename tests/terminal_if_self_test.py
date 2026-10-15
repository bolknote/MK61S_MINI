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
static unsigned cancellations=0,idle_resets=0;
void idle_signal_reset(){++idle_resets;}
int HexdecimalDigit(char c){if(c>='0'&&c<='9')return c-'0';if((c|32)>='a'&&(c|32)<='f')return (c|32)-'a'+10;return -1;}
void MK61Emu_ReadRegister(int,char* out,const char*){++reads;std::memcpy(out,regtext,15);}
const char* read_stack_register(stack,char* out,const char*){++reads;std::memcpy(out,regtext,15);return out;}
struct {std::string text;void println(const char* s){text+=s;text+='\n';}} Serial;
class class_terminal {
 public:
  static u8 input_buffer[MAX_INPUT_CHAR];usize recive_pos=0;bool legacy=false;
  static bool operand_delimiter(char);static bool parse_if_operand(const char*&,double&);
  static bool parse_if_condition(const char*&,bool&);static bool parse_mk_display_value(const char*,double&);
  const char* command_args();Result exec_if(bool,bool);Result execute_script_line(const char*,bool);
  Result legacy_if(bool,bool);Result legacy_script(const char*,bool);Result execute(bool,bool);
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
 if(cmd==CMD_OPEN)return Result::action(ResultKind::OPEN_FILE,args);
 if(cmd==CMD_RUN)return Result::action(ResultKind::GOTO_LABEL,args);
 if(cmd==CMD_RET)return Result::action(ResultKind::RETURN_SCRIPT,args);
 if(cmd==CMD_PRINT)return Result::action(ResultKind::OK,args);
 return Result::error();
}
struct Snapshot{ResultKind kind;int key,offset;std::string arg,text,buffer;usize position;unsigned reads,cancellations,idle_resets;};
static unsigned cases=0;
static Snapshot run(std::string line,bool legacy,bool script,bool trap,bool alias){
 class_terminal t;t.legacy=legacy;t.recive_pos=7;
 for(unsigned i=0;i<MAX_INPUT_CHAR;++i)t.input_buffer[i]=(u8)(0x80+i%97);
 const char* input=line.c_str();
 if(alias){assert(line.size()<MAX_INPUT_CHAR);std::memcpy(t.input_buffer,input,line.size()+1);input=(const char*)t.input_buffer;}
 Serial.text.clear();reads=0;cancellations=0;idle_resets=0;Result result;
 if(script)result=legacy?t.legacy_script(input,trap):t.execute_script_line(input,trap);
 else{assert(line.size()<MAX_INPUT_CHAR);std::memcpy(t.input_buffer,input,line.size());t.input_buffer[line.size()]=CR;t.recive_pos=line.size()+1;result=t.execute(false,trap);}
 const uintptr_t a=(uintptr_t)result.args,b=(uintptr_t)input;
 return {result.kind,result.key,a>=b&&a<=b+line.size()?(int)(a-b):-1,std::string(result.args),Serial.text,
         std::string((char*)t.input_buffer,MAX_INPUT_CHAR),t.recive_pos,reads,cancellations,idle_resets};
}
static void check(const std::string& line){
 for(bool script:{false,true})for(bool trap:{false,true})for(bool suspended:{false,true})for(bool alias:{false,true}){
  if((!script||alias)&&line.size()>=MAX_INPUT_CHAR)continue;
  m61_text::suspended=suspended;auto a=run(line,true,script,trap,alias),b=run(line,false,script,trap,alias);
  if(!(a.kind==b.kind&&a.key==b.key&&a.offset==b.offset&&a.arg==b.arg&&a.text==b.text&&a.buffer==b.buffer&&a.position==b.position&&a.reads==b.reads&&a.cancellations==b.cancellations&&a.idle_resets==b.idle_resets)){
   std::fprintf(stderr,"IF mismatch [%s] script=%d trap=%d suspended=%d alias=%d\n",line.c_str(),script,trap,suspended,alias);assert(false);
  }++cases;
 }
}
int main(){
 for(const char* text:{" 0.0000000  00","-0.0000000  00"," 1.0000000  00","-1.0000000  00"," 2.7000000  01"," 1.2345678 -99"," F.0000000  00"}){
  regtext=text;
  for(bool expanded:{false,true}){core_61::expanded=expanded;
   for(const char* lhs:{"re","rf","r0","x","x1","y","z","t","0","-0","1.25"})
   for(const char* op:{"==","!=","<","<=",">",">=","=","!","<>","===",""})
   for(const char* rhs:{"0","1","-0","1.25","re"}){
    check(std::string("if ")+lhs+op+rhs+" open \"some file.tbi\"");
   }
  }
 }
 regtext=" 0.0000000  00";
 for(const char* line:{"","if","if ","if 0==0","if 0==1 bad command","if 0==0 bad command","if 0==0 if 1<2 run :next","if 0==0 if 1>2 bad","if 0==0 open x","if 0==0 dfu","if\t0==0\tprint hi","IF 0==0 open x"," if 0==0 open x","ifx 0==0 open x","if 0==0\r\nopen x","if 0==0 ret"})check(line);
 for(unsigned n:{238U,239U,240U,241U,1000U})for(const char* prefix:{"if 0==0 open ","if 0==1 open ","open "}){std::string line=prefix;line.resize(n,'a');check(line);}
 std::string nested="open x";for(unsigned n=0;n<24;++n){check(nested);nested="if 0==0 "+nested;}
 std::printf("production IF/script differential: %u cases, buffers/arguments/errors/permissions/reads/cancellation/idle exact PASS\n",cases);
}
'''

production=''.join(method(name) for name in ('command_args','operand_delimiter','parse_mk_display_value',
    'parse_if_operand','parse_if_condition','exec_if','execute_script_line'))
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
