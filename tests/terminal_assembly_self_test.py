#!/usr/bin/env python3
"""Compile the real assembler, mnemonic tables and listing writers on the host.

Only the CDC stream, shared scratch lease and calculator memory are adapted.
The production functions are extracted just as in terminal_run_self_test.py.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(source, marker):
    at = source.index(marker)
    start = source.rfind('\n', 0, at) + 1
    end = source.index('{', at) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


terminal = (ROOT / 'code/terminal.cpp').read_text()
terminal += (ROOT / 'code/terminal_command_functions.inc').read_text().replace(
    'MK61_TERMINAL_COMMAND_CLASS', 'class_terminal')
mnemonics = terminal[terminal.index('static constexpr char ISA_61[] ='):
                     terminal.index('#if MK61_DWT_PROFILER_SUPPORTED && MK61_ENABLE_PROFILE_SAVE')]
prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "terminal_core.hpp"
#include "terminal_front_coding.hpp"
#include "terminal_encoding.hpp"
#include "terminal_mnemonics_legacy.hpp"
#if __has_include("terminal_mnemonics.hpp")
#include "terminal_mnemonics.hpp"
#endif
#if __has_include("terminal_listing.hpp")
#include "terminal_listing.hpp"
#endif
namespace terminal_keys { constexpr usize COUNT = 240; }
namespace shared_scratch {
enum class Owner { TERMINAL_TRANSFER };
static bool busy = false;
class Lease {
  std::array<u8,1600> bytes{};
public:
  Lease(Owner,usize size) { assert(size <= bytes.size()); }
  bool ok() const { return !busy; }
  u8* data() { return bytes.data(); }
};
}
struct Printer {
  std::string text;
  usize write(u8 byte) { text += (char)byte; return 1; }
  void print(usize value,int base) {
    assert(base==16);char text[20];std::snprintf(text,sizeof(text),"%zX",(size_t)value);
    this->text+=text;
  }
  void print(const char* value) { text += value; }
  void print(char value) { text += value; }
  void print(usize value) { text += std::to_string(value); }
  void println() { text += "\r\n"; }
  void println(const char* value) { print(value); println(); }
  void println(usize value) { print(value); println(); }
} Serial;
static void Serial_write_hex(u8 value) {
  const char hex[] = "0123456789ABCDEF";
  Serial.write(hex[value >> 4]); Serial.write(hex[value & 15]);
}
static bool byte_writer(u8 byte,void*) { return Serial.write(byte)==1; }
static void terminal_write_m8(const char* text) {
  assert(terminal_encoding::write_m8(text,byte_writer,nullptr));
}
namespace core_61 {
constexpr usize MAX_PROGRAM_STEP = 112;
constexpr usize CLASSIC_PROGRAM_STEP = 105;
constexpr usize EXTENDED_ADDRESS_LIMIT = 10000;
constexpr usize CODE_PAGE_BUFFER_SIZE = MAX_PROGRAM_STEP+1;
static usize steps = 105;
static std::array<u8,10000> memory{};
static u8 bank = 0;
static usize writes = 0;
usize program_steps() { return steps; }
bool expanded_program_is_on() { return steps==112; }
u8 active_program_bank() { return bank; }
void get_code_page(u8* page) {
  std::copy_n(memory.begin()+bank*112,steps,page);
  std::fill(page+steps,page+CODE_PAGE_BUFFER_SIZE,0);
}
bool read_absolute_program(u16 address,u8& value) {
  if(address>=memory.size())return false;
  value=memory[address];return true;
}
bool write_absolute_program(u16 address,u8 value) {
  if(address>=memory.size())return false;
  memory[address]=value;++writes;return true;
}
}
enum class ProgramMemoryMode { AUTO, CLASSIC_105 };
namespace library_mk61 {
static ProgramMemoryMode mode=ProgramMemoryMode::AUTO;
ProgramMemoryMode program_memory_mode() { return mode; }
}
static void apply_program_memory_auto(const u8*,usize,bool,bool) {}
static void ErrorReaction() {}
constexpr usize MAX_LEN_CLASSIC_MNEMO=8;
constexpr int HEX=16;
class class_terminal {
public:
  isize AT=0;
  const char* args="";
  const char* command_args() const { return args; }
  void print_address_as_MK61(usize);
  void list_mk61_code_page();
  void lasm_mk61_code_page();
  void pub_mk61_code_page();
  void echo_ISA_61();
  bool Assembler();
};
'''
fixture = r'''
static void reset(std::initializer_list<u8> bytes={}) {
  core_61::memory.fill(0);core_61::steps=105;core_61::bank=0;
  std::copy(bytes.begin(),bytes.end(),core_61::memory.begin());
  core_61::writes=0;Serial.text.clear();
  shared_scratch::busy=false;library_mk61::mode=ProgramMemoryMode::AUTO;
}
static bool assemble(class_terminal& terminal,const char* args) {
  terminal.args=args;return terminal.Assembler();
}
static void check(bool ok,const char* message) {
  if(!ok) { std::fprintf(stderr,"FAIL: %s\n",message);std::abort(); }
}
static std::string line(const std::string& text,const std::string& address) {
  auto begin=text.find(address);
  check(begin!=std::string::npos,"listing address missing");
  return text.substr(begin,text.find("\r\n",begin)-begin);
}
static void basic_assembly() {
  reset();class_terminal terminal;
  check(assemble(terminal,"0000 1 2 add hlt"),"documented English asm example");
  check(core_61::memory[0]==1&&core_61::memory[1]==2&&
        core_61::memory[2]==0x10&&core_61::memory[3]==0x50,"English opcodes");
  check(terminal.AT==4,"assembler continuation address");
  check(assemble(terminal,"3 4 mul"),"continuation without four-digit address");
  check(core_61::memory[4]==3&&core_61::memory[6]==0x12,"continuation opcodes");
  reset();terminal.AT=0;
  check(assemble(terminal,"0000 1 2 + C/\317"),"CP1251 calculator aliases");
  check(assemble(terminal,"0004 Kx!=0 0 Kx>=0\tA Kx<0  3 Kx=0 E"),
        "all four indirect conditional families accept spaced aliases");
  check(core_61::memory[4]==0x70&&core_61::memory[5]==0x9A&&
        core_61::memory[6]==0xC3&&core_61::memory[7]==0xEE,"indirect alias opcodes");
  const auto saved=core_61::memory;const auto at=terminal.AT;
  check(!assemble(terminal,"0000 1 bad-token"),"reject unknown mnemonic");
  check(core_61::memory==saved&&terminal.AT==at,"parse failure is atomic");
  library_mk61::mode=ProgramMemoryMode::CLASSIC_105;
  check(!assemble(terminal,"0104 hlt hlt"),"active memory bound");
  check(core_61::memory==saved&&terminal.AT==at,"overflow is atomic");
  check(!assemble(terminal,"0000 ?"),"unknown opcode has no ambiguous question-mark mnemonic");
}
static void mnemonics_and_extensions() {
  reset();class_terminal terminal;
  check(assemble(terminal,"0000 far jmp 02 50 disp 53 xmsr xmsp stoF ldF"),
        "new prefixes, Ms exchanges and RF mnemonics");
  const u8 expected[]={0x1F,0x51,0x02,0x50,0x2F,0x53,0x55,0x56,0x4F,0x6F};
  check(std::equal(std::begin(expected),std::end(expected),core_61::memory.begin()),
        "extension bytes preserve BCD and hex operands");
  terminal.echo_ISA_61();
  check(Serial.text.find("1F far")!=std::string::npos,"ISA names far prefix");
  check(Serial.text.find("2F disp")!=std::string::npos,"ISA names display prefix");
  check(Serial.text.find("55 xmsr")!=std::string::npos,"ISA names register exchange");
  check(Serial.text.find("56 xmsp")!=std::string::npos,"ISA names program exchange");
  check(Serial.text.find("4F stoF")!=std::string::npos,"ISA names RF store");
  reset({0x1F,0x51,0x02,0x50,0x2F,0x53,0x50});core_61::steps=112;
  terminal.lasm_mk61_code_page();
  check(line(Serial.text,"0000").find("far")!=std::string::npos,"LASM far name");
  check(line(Serial.text,"0000").find("51 02 50")!=std::string::npos,"far operands together");
  check(line(Serial.text,"0004").find("disp")!=std::string::npos,"LASM display name");
  check(line(Serial.text,"0005").find("call")==std::string::npos,"display subcode is data");
  check(line(Serial.text,"0006").find("hlt")!=std::string::npos,"instruction after display prefix");
  for(usize address=1;address<=3;++address) {
    const char* labels[]={"","0001","0002","0003"};
    check(line(Serial.text,labels[address]).find("hlt")==std::string::npos,"far arguments are data");
  }
}
static void operand_boundaries() {
  class_terminal terminal;
  for(u8 opcode:{u8{0x51},u8{0x53},u8{0x57},u8{0x58},u8{0x59},u8{0x5A},
                 u8{0x5B},u8{0x5C},u8{0x5D},u8{0x5E}}) {
    for(unsigned value=0;value<256;++value) {
      reset({opcode,(u8)value,0x50});terminal.lasm_mk61_code_page();
      check(line(Serial.text,"0002").find("hlt")!=std::string::npos,
            "every branch operand preserves the following mnemonic");
      Serial.text.clear();terminal.pub_mk61_code_page();
      check(line(Serial.text,"02.").find("C/\317")!=std::string::npos,
            "PUB uses instruction boundaries, not the previous raw byte");
    }
  }
  reset({0x51,0x1F,0x50});core_61::steps=112;terminal.lasm_mk61_code_page();
  check(line(Serial.text,"0002").find("hlt")!=std::string::npos,"prefix-valued ordinary operand");
  reset({0x1F,0x51,0x50});terminal.lasm_mk61_code_page();
  check(line(Serial.text,"0001").find("jmp")!=std::string::npos,"classic mode ignores prefix semantics");
}
static void addresses_and_unknown_bytes() {
  reset();class_terminal terminal;core_61::steps=112;
  core_61::memory[104]=0x50;core_61::memory[110]=0x50;core_61::memory[111]=0x50;
  terminal.lasm_mk61_code_page();
  check(Serial.text.find("00B0 50 hlt")!=std::string::npos,"step 110 uses B0");
  check(Serial.text.find("00B1 50 hlt")!=std::string::npos,"last extended step is included");
  check(Serial.text.find("00A10")==std::string::npos,"no five-character addresses");
  Serial.text.clear();terminal.list_mk61_code_page();
  check(Serial.text.find("B0. 50")!=std::string::npos&&
        Serial.text.find("B1. 50")!=std::string::npos,"LIST also uses B0/B1");
  for(unsigned value=0xF0;value<=0xFF;++value) {
    reset({(u8)value});terminal.lasm_mk61_code_page();
    char expected[20];std::snprintf(expected,sizeof(expected),"0000 %02X %02X",value,value);
    check(Serial.text.find(expected)!=std::string::npos,"unknown byte remains visible and assemblable");
  }
}
static void vocabulary_round_trip() {
  reset();class_terminal terminal;
  char mnemonic[terminal_mnemonics::MAX_LENGTH+1];
  usize legacy_count=0;
  for(unsigned opcode=0;opcode<240;++opcode) {
    terminal_mnemonics::csv(LEGACY_ISA_61,opcode,mnemonic);
    if(std::strcmp(mnemonic,"?")==0)continue;
    ++legacy_count;
    check(assemble(terminal,(std::string("0000 ")+mnemonic).c_str()),
          "complete frozen English vocabulary still assembles");
    check(core_61::memory[0]==opcode,"historic English mnemonic keeps its opcode");
  }
  check(legacy_count>200,"legacy oracle covers the full instruction set");
  for(unsigned opcode=0;opcode<256;++opcode) {
    terminal_mnemonics::english((u8)opcode,mnemonic);
    check(assemble(terminal,(std::string("0000 ")+mnemonic).c_str()),
          "every printed English mnemonic or hex fallback assembles");
    check(core_61::memory[0]==opcode&&terminal.AT==1,"English byte round-trip");
  }
  TerminalMnemonicTable table;
  check(table.ok()&&std::strcmp(table.data(),ISA_61)==0,"complete F401 mnemonic decode");
  usize spaced=0;
  for(unsigned opcode=0;opcode<240;++opcode) {
    terminal_mnemonics::csv(table.data(),opcode,mnemonic);
    if(std::strchr(mnemonic,' ')==nullptr)continue;
    ++spaced;
    check(assemble(terminal,(std::string("0000 ")+mnemonic).c_str()),
          "every spaced calculator alias assembles");
    check(core_61::memory[0]==opcode,"spaced alias preserves opcode");
    std::string tabs(mnemonic);
    tabs.replace(tabs.find(' '),1,"\t  ");
    check(assemble(terminal,(std::string("0000 ")+tabs).c_str()),"alias whitespace normalization");
  }
  check(spaced==60,"all sixty indirect conditional aliases tested");
  check(assemble(terminal,"0000 jnz[R4] jlz"),"historic and documented alternate spellings");
  check(core_61::memory[0]==0xE4&&core_61::memory[1]==0x59,"alternate spelling opcodes");
  check(!assemble(terminal,"0000 Kx!=0 00"),"alias register token boundary");
  check(!assemble(terminal,"0000 hltx"),"English token boundary");
  check(assemble(terminal,"0000 1f 2f ff"),"lowercase raw hex fallback");
  check(core_61::memory[0]==0x1F&&core_61::memory[2]==0xFF,"hex fallback bytes");
}
static void prefixes_and_bank_seams() {
  class_terminal terminal;
  for(unsigned subcode=0;subcode<256;++subcode) {
    reset({0x2F,(u8)subcode,0x50});core_61::steps=112;
    terminal.lasm_mk61_code_page();
    check(line(Serial.text,"0002").find("hlt")!=std::string::npos,"every display subcode is data");
  }
  for(u8 subcode:{u8{0x51},u8{0x53},u8{0x57},u8{0x58},u8{0x59},u8{0x5A},
                  u8{0x5B},u8{0x5C},u8{0x5D},u8{0x5E}}) {
    reset({0x1F,subcode,0,0,0x50});core_61::steps=112;
    terminal.lasm_mk61_code_page();
    check(line(Serial.text,"0004").find("hlt")!=std::string::npos,"four-byte far instruction");
    check(line(Serial.text,"0002").find(" 0 ")==std::string::npos,"far zero operand stays data");
  }
  reset({0x1F,0x56,0x18,0x50});core_61::steps=112;terminal.lasm_mk61_code_page();
  check(line(Serial.text,"0003").find("hlt")!=std::string::npos,"three-byte far Ms exchange");
  reset({0x1F,0x8A,0x50});core_61::steps=112;terminal.lasm_mk61_code_page();
  check(line(Serial.text,"0002").find("hlt")!=std::string::npos,"two-byte indirect far instruction");
  reset({0x1F,0x51,0,0});core_61::steps=112;terminal.lasm_mk61_code_page();
  check(Serial.text.find("0003 00")!=std::string::npos,"trailing zero far operands are retained");
  reset();core_61::steps=112;
  core_61::memory[110]=0x1F;core_61::memory[111]=0x51;
  core_61::memory[112]=0x02;core_61::memory[113]=0x50;
  const auto saved=core_61::memory;terminal.lasm_mk61_code_page();
  check(line(Serial.text,"00B0").find("51 02 50")!=std::string::npos,"far operand lookahead into next bank");
  check(core_61::memory==saved&&core_61::bank==0&&core_61::writes==0,"listing is read-only");
  reset({0x27});core_61::steps=112;core_61::memory[111]=0x51;
  core_61::memory[112]=0x50;terminal.lasm_mk61_code_page();
  check(line(Serial.text,"00B1").find("jmp      27")!=std::string::npos,"local branch operand wraps within its bank");
  reset();core_61::steps=112;core_61::memory[112]=0x50;
  terminal.lasm_mk61_code_page();check(Serial.text.empty(),"next bank does not extend an empty listing");
}
static void fixed_columns_and_busy_scratch() {
  reset();class_terminal terminal;core_61::steps=112;
  std::fill_n(core_61::memory.begin(),112,0xAA);terminal.lasm_mk61_code_page();
  for(usize row=0;row<30;++row) {
    char address[5];std::snprintf(address,sizeof(address),"00%02u",(unsigned)row);
    const auto text=line(Serial.text,address);
    check(text.size()==(row<22?112:84),"LASM fixed width includes long mnemonics");
    check(text.substr(28,4)==std::string("00")+std::to_string(row+30),"second column alignment");
    check(text.substr(56,4)==std::string("00")+std::to_string(row+60),"third column alignment");
  }
  reset();terminal.echo_ISA_61();
  check(Serial.text.substr(16,4)=="01 1"&&Serial.text.substr(32,4)=="02 2"&&
        Serial.text.substr(48,4)=="03 3","ISA has four fixed columns");
  reset({0x50});shared_scratch::busy=true;
  terminal.lasm_mk61_code_page();
  check(Serial.text.find("hlt")!=std::string::npos,"LASM needs no shared scratch");
#if MK61_F401_PRODUCT_BUILD
  Serial.text.clear();check(!assemble(terminal,"0000 1"),"assembler reports busy mnemonic workspace");
  check(core_61::writes==0,"busy workspace does not modify program");
#endif
}
int main() {
  basic_assembly();mnemonics_and_extensions();operand_boundaries();addresses_and_unknown_bytes();
  vocabulary_round_trip();prefixes_and_bank_seams();fixed_columns_and_busy_scratch();
  std::puts("production ASM/ISA/LASM/PUB regression tests PASS");
}
'''
production = mnemonics
production += '\nnamespace core_61 {\n' + function(
    (ROOT / 'code/mk61emu_core.cpp').read_text(), 'usize len_code_command(') + '}\n'
production += function((ROOT / 'code/tools.cpp').read_text(), 'usize seek_program_END(')
for name in ('print_address_as_MK61', 'lasm_mk61_code_page', 'pub_mk61_code_page',
             'list_mk61_code_page', 'echo_ISA_61', 'Assembler'):
    production += function(terminal, 'class_terminal::' + name + '(')
with tempfile.TemporaryDirectory(prefix='mk61-terminal-assembly-') as temp:
    cpp = Path(temp) / 'test.cpp'
    exe = Path(temp) / 'test'
    cpp.write_text(prelude + production + fixture)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS') == '1' else []
    for product in (0, 1):
        subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        *flags, f'-DMK61_F401_PRODUCT_BUILD={product}', '-I', str(ROOT / 'code'),
                        '-I', str(ROOT / 'tests'),
                        str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
