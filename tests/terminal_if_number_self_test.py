#!/usr/bin/env python3
"""Compare the real IF operand reader with its frozen string-only predecessor.

The terminal operand methods and hexadecimal-digit reader are extracted from
production. The real core, formatters, numeric fast reader and ring are compiled
unchanged; only the unrelated terminal class surface is omitted.
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
production = ''.join(function(terminal, 'class_terminal::' + name + '(')
                     for name in ('operand_delimiter', 'parse_mk_display_value',
                                  'parse_if_reference', 'read_if_reference',
                                  'parse_if_operand'))
hexadecimal = function((ROOT / 'code/tools.hpp').read_text(),
                       'isize HexdecimalDigit(')

prelude = r'''
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <string>
#include <vector>
#include "mk61emu_core.cpp"
#include "mk61_ref.hpp"
#include "terminal_core.hpp"
static constexpr char terminal_symbols[16] = {
 '0','1','2','3','4','5','6','7','8','9','-','L','C','\303','E',' '
};
class class_terminal {
public:
 static bool operand_delimiter(char);
 static bool parse_mk_display_value(const char*,double&);
 static u8 parse_if_reference(const char*&);
 static bool read_if_reference(u8,double&);
 static bool parse_if_operand(const char*&,double&);
};
'''

fixture = r'''
// Frozen pre-fast-reader operand semantics. Delimiter/decimal/display parsing
// are unchanged production functions, while register I/O is the real core.
static bool legacy_operand(const char*& p,double& out) {
 p=terminal_core::skip_spaces(p);
 const char c=(*p>='A'&&*p<='Z')?(char)(*p-'A'+'a'):*p;
 if(c=='r') {
  const isize reg=HexdecimalDigit(p[1]);
  if(reg>=0&&class_terminal::operand_delimiter(p[2])) {
   if(reg==15&&!core_61::expanded_program_is_on())return false;
   char value[15];value[14]=0;
   MK61Emu_ReadRegister((int)reg,value,terminal_symbols);
   p+=2;return class_terminal::parse_mk_display_value(value,out);
  }
  return false;
 }
 if(c=='x'||c=='y'||c=='z'||c=='t') {
  stack reg=stack::X;usize advance=1;
  if(c=='x'&&p[1]=='1'){reg=stack::X1;advance=2;}
  else if(c=='x')reg=stack::X;
  else if(c=='y')reg=stack::Y;
  else if(c=='z')reg=stack::Z;
  else reg=stack::T;
  if(!class_terminal::operand_delimiter(p[advance]))return false;
  char value[15];value[14]=0;
  read_stack_register(reg,value,terminal_symbols);
  p+=advance;return class_terminal::parse_mk_display_value(value,out);
 }
 return terminal_core::parse_decimal(p,out);
}

using Word=std::array<u8,12>;
struct Entry{bool is_stack;int index;std::string token;};
static u64 cases=0, successes=0, failures=0, signed_zeros=0;
static bool expanded=false;
static u32 random_state=0x49464e55U;
static Word current_word={};
static const char* scenario="initialization";
static u32 random_word(){
 random_state^=random_state<<13;random_state^=random_state>>17;
 random_state^=random_state<<5;return random_state;
}
static double sentinel(){
 const u64 bits=0x405edd2f1a9fbe77ULL;double out;
 std::memcpy(&out,&bits,sizeof(out));return out;
}
[[noreturn]] static void fail(const std::string& text,const char* reason,
 double actual,double expected,isize a,isize e){
 std::fprintf(stderr,"FAIL production IF numeric %s expanded=%d: %s "
  "actual=%016llx/%ld expected=%016llx/%ld token=",
  scenario,expanded,reason,(unsigned long long)mk_math::binary64_bits(actual),(long)a,
  (unsigned long long)mk_math::binary64_bits(expected),(long)e);
 for(unsigned char c:text)std::fprintf(stderr,"%02x,",(unsigned)c);
 std::fputs(" word=",stderr);
 for(u8 cell:current_word)std::fprintf(stderr,"%02x,",(unsigned)cell);
 std::fputc('\n',stderr);std::exit(1);
}
static void fixture(const Entry& e,const Word& word){
 current_word=word;
 const usize base=e.is_stack?core_61::stack_address((stack)e.index)+1:(usize)e.index*42;
 for(usize i=0;i<8;++i)ringM[base+(7-i)*3]=word[i];
 ringM[base+24]=word[8];ringM[base+33]=word[9];
 ringM[base+30]=word[10];ringM[base+27]=word[11];
}
static Word decimal_word(u32 mantissa,int exponent,bool negative){
 Word word={};
 for(int i=7;i>=0;--i){word[i]=(u8)(mantissa%10);mantissa/=10;}
 word[8]=negative?9:0;
 if(exponent<0){exponent+=100;word[9]=9;}
 word[10]=(u8)(exponent/10);word[11]=(u8)(exponent%10);return word;
}
static void check(const std::string& text){
 std::array<u8,SIZE_RING_M> before;
 std::memcpy(before.data(),ringM,sizeof(ringM));
 const char* expected_tail=text.c_str();double expected=sentinel();
 const bool expected_ok=legacy_operand(expected_tail,expected);
 const char* actual_tail=text.c_str();double actual=sentinel();
 const bool actual_ok=class_terminal::parse_if_operand(actual_tail,actual);
 const isize a=actual_tail-text.c_str(),e=expected_tail-text.c_str();
 if(actual_ok!=expected_ok||mk_math::binary64_bits(actual)!=mk_math::binary64_bits(expected)||a!=e)
  fail(text,"status, value or pointer advance differs",actual,expected,a,e);
 if(std::memcmp(before.data(),ringM,sizeof(ringM)))
  fail(text,"operand read changed calculator ring",actual,expected,a,e);
 ++cases;if(actual_ok)++successes;else ++failures;
 if(actual_ok&&mk_math::binary64_bits(actual)==0x8000000000000000ULL)++signed_zeros;
}
static std::vector<std::string> names(const Entry& entry){
 std::vector<std::string> result={entry.token};
 std::string upper=entry.token;
 for(char& c:upper)if(c>='a'&&c<='z')c=(char)(c-'a'+'A');
 result.push_back(upper);
 if(!entry.is_stack&&entry.index>=10){
  result.push_back(std::string("r")+upper[1]);
  result.push_back(std::string("R")+entry.token[1]);
 }
 return result;
}
static void test_numeric_words(const std::vector<Entry>& entries){
 scenario="all canonical orders and mantissas";
 for(const Entry& entry:entries)
  for(int exponent=-99;exponent<=99;++exponent)
   for(u32 mantissa:{0U,1U,9U,10U,10000000U,12345678U,50000000U,99999999U})
    for(bool negative:{false,true}){
     fixture(entry,decimal_word(mantissa,exponent,negative));
     check(" \t"+entry.token+"==1 open ignored.tbi");
    }
}
static void test_raw_cells(const std::vector<Entry>& entries){
 scenario="all raw byte cell mutations";
 for(const Entry& entry:entries)
  for(const Word original:{decimal_word(0,0,false),decimal_word(10000000U,0,false),
                          decimal_word(12345678U,-99,true),decimal_word(99999999U,99,true)})
   for(usize cell=0;cell<12;++cell){
    Word word=original;
    for(unsigned value=0;value<256;++value){
     word[cell]=(u8)value;fixture(entry,word);check(entry.token+"<=0");
    }
   }
}
static void test_token_boundaries(const std::vector<Entry>& entries){
 scenario="token case, whitespace, boundary and raw fallback";
 std::vector<Word> words={decimal_word(0,0,false),decimal_word(0,0,true),
  decimal_word(10000000U,0,false),decimal_word(12345678U,-99,true),
  decimal_word(12345678U,99,false)};
 Word word=decimal_word(10000000U,0,false);
 word[8]=1;words.push_back(word); // R negative, stack positive: different legacy signs.
 word[9]=9;word[10]=word[11]=0;words.push_back(word); // -100: strict rejection.
 word[10]=10;words.push_back(word); // Odd -00 may be accepted by formatter/parser.
 word=decimal_word(10000000U,0,false);word[3]=15;words.push_back(word); // Skipped space.
 word[3]=10;words.push_back(word); // Nondecimal sign inside mantissa rejects.
 for(const Entry& entry:entries)for(const Word& value:words){
  fixture(entry,value);
  for(const std::string& name:names(entry))
   for(const char* prefix:{""," ","\t"," \t ","\r"," \n"})
    for(const char* suffix:{""," ","\t","\r","\n","<","<=",">",">=","=","==0","!","!=1",
                           ":","1","a",".","/","_","\v","\xff"})
     check(std::string(prefix)+name+suffix);
 }
}
static void test_literals_and_malformed(){
 scenario="numeric literals and malformed names";
 for(const char* text:{""," ","\t","0","-0","+0","-0.0000000","1.25e-99","9.9999999e99",
  "1e100","1e","1e-","1e+","+","-",".","1.2.3","r","R","rg","r-1","r00","r000",
  "rf","RF","rf==0","x","x1","x2","x11","X1x","yfoo","z0","t0","re_","r0;","r0\v"})
  for(const char* prefix:{""," ","\t"," \t"})check(std::string(prefix)+text);
}
static void test_random_words(const std::vector<Entry>& entries){
 scenario="deterministic multicell fallback";
 for(unsigned sample=0;sample<10000U;++sample){
  const Entry& entry=entries[random_word()%entries.size()];Word word;
  for(u8& cell:word)cell=(u8)(random_word()&(sample&1?15U:255U));
  fixture(entry,word);check("\t"+entry.token+" != 0");
 }
}
int main(){
 for(bool mode:{false,true}){
  expanded=mode;core_61::set_expanded_program_mode(mode);
  for(u8& cell:ringM)cell=(u8)random_word();
  std::vector<Entry> entries;
  // Include RF even in classic mode to exercise the terminal's availability
  // precheck and, specifically, its unchanged pointer on this early failure.
  for(int reg=0;reg<16;++reg)
   entries.push_back({false,reg,std::string("r")+"0123456789abcdef"[reg]});
  for(int reg=0;reg<5;++reg)
   entries.push_back({true,reg,std::array<const char*,5>{"x1","x","y","z","t"}[reg]});
  test_numeric_words(entries);test_raw_cells(entries);test_token_boundaries(entries);
  test_literals_and_malformed();test_random_words(entries);
 }
 if(!successes||!failures||!signed_zeros){
  std::fputs("FAIL production IF operand fixture did not cover success/error/-0\n",stderr);return 1;
 }
 std::printf("production IF numeric operands backend=%d: %llu cases, success=%llu error=%llu "
  "negative_zero=%llu; exact status/binary64/pointer/ring PASS\n",MK61_MATH_BACKEND,
  (unsigned long long)cases,(unsigned long long)successes,(unsigned long long)failures,
  (unsigned long long)signed_zeros);
}
'''

with tempfile.TemporaryDirectory(prefix='mk61-if-number-') as directory:
    work = Path(directory)
    cpp = work / 'test.cpp'
    exe = work / 'test'
    cpp.write_text(prelude + hexadecimal + production + fixture)
    sanitizer = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                 '-fno-omit-frame-pointer'] if os.getenv('MK61_TEST_SANITIZERS') == '1' else []
    for backend in (0, 1):
        subprocess.run([
            'clang++', '-std=c++17', '-O2', '-Wall', '-Wextra', '-Wno-unused',
            '-Wno-unused-parameter', '-Wno-cpp', *sanitizer,
            '-DMK61_MATH_BACKEND=' + str(backend), '-DMK61_CORE_NATIVE_HOT_PATHS=1',
            '-DMK61_CORE_PACKED_AMK=0', '-DMK61_CORE_HOT_TABLES_IN_SRAM=0',
            '-DMK61_DISPLAY_UC1609', '-include', str(ROOT / 'tests/mk_math_shim/debug.h'),
            '-I' + str(ROOT / 'tests/mk_math_shim'), '-I' + str(ROOT / 'code'), str(cpp),
            *(str(ROOT / 'code' / name) for name in (
                'language_workspace.cpp', 'shared_memory.cpp', 'workspace_swap.cpp',
                'zx0.cpp', 'zx0_encode.cpp')),
            '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
