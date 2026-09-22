// Drives the generated calculator program through the real ROM/core.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <iomanip>
#include "mk61emu_core.h"

unsigned elite_load_game(const char* directory);

static const char symbols[]="0123456789-     ";
static bool input_frame_stable=true;
static void press(int x,int y) {
  core_61::clear_displayed();
  for(int i=0;i<4;i++) { MK61Emu_SetKeyPress(x,y); core_61::step(); if(core_61::is_RUN()) break; }
  MK61Emu_SetKeyPress(0,0);
  for(int i=0;i<512;i++) { core_61::step(); if(core_61::is_RUN()||core_61::is_displayed()) break; }
}
static double number(const char* v) {
  std::string s=v[0]=='-'?"-":"";
  for(int i=1;i<=9;i++) if(v[i]!=' ') s+=v[i];
  s+='e'; s+=v[11]=='-'?'-':'+'; s+=v[12]; s+=v[13];
  return std::strtod(s.c_str(),nullptr);
}
static double memory(int r) { char v[15]={}; MK61Emu_ReadRegister(r,v,symbols); return number(v); }
static double xvalue() { char v[15]={}; read_stack_register(stack::X,v,symbols); return number(v); }
static bool trace_boundary(const core_61::Mk61ProgramBoundaryContext& context,void*) {
  if(std::getenv("ELITE_TRACE")) {
    char v[15]={};read_stack_register(stack::X,v,symbols);
    std::cerr<<unsigned(core_61::active_program_bank())*112+context.address
             <<" op="<<std::hex<<unsigned(context.opcode)<<std::dec<<" X="<<v<<'\n';
  }
  return false;
}
static void page_word(int bank,int field,long long value) {
  bool neg=value<0; if(neg)value=-value;
  std::string digits=std::to_string(value); int exp=value?digits.size()-1:0;
  digits.resize(8,'0'); u8 t[14]={};
  for(int i=0;i<8;i++)t[i]=digits[7-i]-'0';
  t[8]=neg?9:0; t[9]=exp%10; t[10]=exp/10;
  int h[]={13,1,3,5,7,9,11};
  for(int i=0;i<7;i++) if(!core_61::write_absolute_program(bank*112+field*7+i,(t[h[i]]<<4)|t[h[i]-1]))std::exit(4);
}
static long long page_value(int bank,int field) {
  u8 t[14]={},byte=0; int h[]={13,1,3,5,7,9,11};
  for(int i=0;i<7;i++){core_61::read_absolute_program(bank*112+field*7+i,byte);t[h[i]]=byte>>4;t[h[i]-1]=byte&15;}
  long long n=0; for(int i=7;i>=0;i--)n=n*10+t[i];
  int exp=t[10]*10+t[9]; for(int i=exp;i<7;i++)n/=10;
  return t[8]? -n:n;
}
static void dump(unsigned steps) {
  std::cout<<"{\"steps\":"<<steps<<",\"running\":"<<(core_61::is_RUN()?"true":"false")
    <<",\"error\":"<<(core_61::extended_program_error()||core_61::has_error()?"true":"false")
    <<",\"pc\":"<<unsigned(core_61::active_program_bank())*112+core_61::get_IP()
    <<",\"input_frame_stable\":"<<(input_frame_stable?"true":"false")
    <<",\"auto_display\":"<<(core_61::extended_display_auto()?"true":"false")
    <<",\"segmented\":"<<(core_61::extended_display_segmented()?"true":"false")
    <<",\"revision\":"<<core_61::extended_display_revision()
    <<",\"x\":"<<std::setprecision(12)<<xvalue()<<",\"regs\":[";
  for(int i=0;i<16;i++){if(i)std::cout<<',';std::cout<<memory(i);}
  std::cout<<"],\"frame\":[";const u8* f=core_61::segment_display_frame();
  for(int i=0;i<12;i++){if(i)std::cout<<',';std::cout<<(f?unsigned(f[i]):0);}
  std::cout<<"],\"pages\":[";
  for(int b=24;b<30;b++){if(b!=24)std::cout<<',';std::cout<<'[';for(int i=0;i<9;i++){if(i)std::cout<<',';std::cout<<page_value(b,i);}std::cout<<']';}
  std::cout<<"]}"<<std::endl;
}
int main(int argc,char**argv){
  if(argc!=2)return 2;
  const unsigned initial_steps=elite_load_game(argv[1]);
  bool initial_pending=true;
  if(std::getenv("ELITE_TRACE"))core_61::set_mk61_program_boundary_hook(trace_boundary);
  std::string line;
  while(std::getline(std::cin,line)){
    std::istringstream in(line);std::string op;in>>op;
    if(op=="set"){int b,f;long long v;in>>b>>f>>v;page_word(b,f,v);continue;}
    if(initial_pending) {
      initial_pending=false;
      if(op=="run" || op=="dump") { dump(initial_steps); continue; }
    }
    if(op=="input"){
      u8 before[12];std::memcpy(before,core_61::segment_display_frame(),12);
      std::string value;in>>value;press(10,8); // Cx
      for(char c:value){if(c>='0'&&c<='9')press(c-'0'+2,1);else if(c=='.')press(7,8);}
      if(value[0]=='-')press(8,8);
      input_frame_stable=std::memcmp(before,core_61::segment_display_frame(),12)==0;
    }
    unsigned steps=0;
    if(op=="run"||op=="input"){
      press(2,9);
      while(core_61::is_RUN()&&steps<2000000){core_61::step();steps++;}
    }
    dump(steps);
  }
}
