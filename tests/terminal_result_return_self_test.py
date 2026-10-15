#!/usr/bin/env python3
"""Exercise actual aggregate-return cases and input cleanup against the old path."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'code/terminal.cpp').read_text()
source = source[source.index('terminal_protocol::Result class_terminal::execute(bool'):
                source.index('\nclass_terminal::InputResult')]
guard_start = source.index('struct ResetInput {')
guard_end = source.index('reset_input{recive_pos};', guard_start) + len('reset_input{recive_pos};')
guard = source[guard_start:guard_end]
pairs = [
 ('CMD_IDENTITY','exec_identity'), ('CMD_BENCHMARK','exec_benchmark'),
 ('CMD_DATE','exec_date'), ('CMD_ALARM','exec_alarm'),
 ('CMD_DISPLAY','exec_display'), ('CMD_PROFILE','exec_profile'),
 ('CMD_CRASH','exec_crash'), ('CMD_WATCHDOG','exec_watchdog'),
 ('CMD_MPU','exec_mpu'), ('CMD_FS_GET','exec_fs_get'),
 ('CMD_FS_PUT','exec_fs_put'), ('CMD_IF','exec_if')]
cases = []
methods = []
legacy = []
for index, (command, handler) in enumerate(pairs):
    match = re.search(r'case\s+'+command+r':\s*{', source)
    if command == 'CMD_IF':
        match = re.search(r'case\s+CMD_IF:\s*return exec_if\(script_mode, trap_mode\);', source)
        assert match
        cases.append(source[match.start():match.end()])
        end = None
    else:
        end = 0
    assert match, command
    if end is not None:
        end = match.end()
        depth = 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        cases.append(source[match.start():end])
    args = 'bool script, bool trap' if handler == 'exec_if' else ''
    extra = 'seen_script=script; seen_trap=trap;' if args else ''
    methods.append(f'Result {handler}({args}) {{ called={index}; seen=recive_pos; {extra} '
                   'if(nested) recive_pos=99; return next; }')
    call = handler+'(script_mode,trap_mode)' if args else handler+'()'
    legacy.append(f'case {command}: {{ const Result result={call}; recive_pos=0; return result; }}')
cpp = r'''
#include "terminal_protocol.hpp"
#include "terminal_command_ids.hpp"
#include <cassert>
#include <climits>
using terminal_protocol::Result;
using terminal_protocol::ResultKind;
struct Terminal {
  usize recive_pos=7,seen=0;
  int called=-1;
  bool nested=false,seen_script=false,seen_trap=false;
  char argument[8]={'a','r','g','s',0};
  Result next=Result::ok();
''' + '\n'.join(methods) + r'''
  Result execute(u8 command,bool script_mode,bool trap_mode) {
    if(recive_pos==0 || recive_pos>240) return Result::error();
''' + guard + '\nswitch(command){\n' + '\n'.join(cases) + r'''
default:return Result::error();
}}
  Result legacy(u8 command,bool script_mode,bool trap_mode) {
    if(recive_pos==0 || recive_pos>240) return Result::error();
    switch(command) {
''' + '\n'.join(legacy) + r'''
default:recive_pos=0;return Result::error();
}}
};
int main() {
  const u8 commands[]={''' + ','.join(c for c,_ in pairs) + r'''};
  const ResultKind kinds[]={ResultKind::OK,ResultKind::ERROR,ResultKind::KEY,
    ResultKind::WAIT,ResultKind::OPEN_FILE,ResultKind::REINIT_CALCULATOR};
  const i32 keys[]={0,-1,INT_MIN,INT_MAX};
  for(unsigned i=0;i<sizeof(commands);++i) for(unsigned mode=0;mode<4;++mode)
    for(bool nested:{false,true}) for(auto kind:kinds) for(auto key:keys) {
      Terminal actual,expected;actual.nested=expected.nested=nested;
      actual.next={kind,key,actual.argument};expected.next={kind,key,expected.argument};
      auto got=actual.execute(commands[i],mode&1,mode&2);
      auto old=expected.legacy(commands[i],mode&1,mode&2);
      assert(got.kind==old.kind && got.key==old.key);
      assert(got.args==actual.argument && old.args==expected.argument);
      assert(actual.called==(int)i && expected.called==(int)i);
      assert(actual.seen==7 && expected.seen==7);
      assert(actual.recive_pos==0 && expected.recive_pos==0);
      assert(actual.seen_script==expected.seen_script && actual.seen_trap==expected.seen_trap);
    }
  for(usize length:{0U,241U}) {
    Terminal t;t.recive_pos=length;
    assert(t.execute(CMD_IDENTITY,false,false).kind==ResultKind::ERROR);
    assert(t.recive_pos==length && t.called==-1);
  }
}
'''
cpp = '#include <initializer_list>\n'+cpp
with tempfile.TemporaryDirectory(prefix='mk61-terminal-return-') as folder:
    folder = Path(folder)
    (folder/'test.cpp').write_text(cpp)
    flags = ['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS')=='1' else []
    subprocess.run(['clang++','-std=c++17','-O2','-Wall','-Wextra','-Werror',*flags,
                    '-I',str(root/'code'),str(folder/'test.cpp'),'-o',str(folder/'test')],check=True)
    subprocess.run([str(folder/'test')],check=True)
print('Terminal real return cases: 2304 legacy comparisons, all Result fields, nested input and cleanup PASS')
