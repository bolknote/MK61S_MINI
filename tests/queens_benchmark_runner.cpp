// Execute stock MK-61 instructions; the observer never changes calculator state.
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include "mk61emu_core.h"

static unsigned long long commands=0, steps=0;
static bool trace=false,reference_trace=false,trace_started=false,trace_ended=false;
static bool pending_write=false,pending_flag=false,pending_y=false;
static int previous_opcode=-1,before_previous_opcode=-1;
static const char symbols[]="0123456789-     ";
static double number(const char* v) {
  std::string s=v[0]=='-'?"-":"";
  for(int i=1;i<=9;i++)if(v[i]!=' ')s+=v[i];
  s+='e';s+=v[11]=='-'?'-':'+';s+=v[12];s+=v[13];
  return std::strtod(s.c_str(),nullptr);
}
static double memory(int r) {
  char v[15]={};MK61Emu_ReadRegister(r,v,symbols);return number(v);
}
static double xvalue() {
  char v[15]={};read_stack_register(stack::X,v,symbols);return number(v);
}
static int integer(double x) {
  if(!std::isfinite(x)||x!=std::round(x)||std::abs(x)>100000000)std::exit(6);
  return static_cast<int>(x);
}
static int depth(){return integer(memory(12));}
static int scan_row(){return integer(memory(reference_trace?13:0));}
static int column(int row) {
  if(row<1||row>8)std::exit(7);
  return integer(memory(row));
}
static bool boundary(const core_61::Mk61ProgramBoundaryContext& c,void*) {
  ++commands;
  if(!trace||trace_ended)return false;
  // Observe completed stores at the following boundary, using memory rather
  // than an arithmetic result still being transferred through the X ring.
  if(pending_write) {
    const int n=depth();
    std::cout<<"E [\"write\","<<n<<','<<column(n)<<"]\n";
    pending_write=false;
    trace_started=true;
  }
  if(pending_flag) {
    std::cout<<"E [\"flag\","<<integer(memory(11))<<"]\n";
    pending_flag=false;
  }
  if(pending_y) {
    std::cout<<"E [\"reset_y\","<<depth()<<','<<scan_row()<<"]\n";
    pending_y=false;
  }
  if(c.opcode==0xBC&&depth()>0)pending_write=true;
  if(trace_started) {
    if(c.opcode==0x4B)pending_flag=true;
    // Both programs have the same prefix through RC -> scan pointer.
    if(c.address==21)pending_y=true;
    if(c.address==25) {
      const int n=depth(),y=scan_row();
      std::cout<<"E [\"while_y\","<<n<<','<<y<<','<<(y>1?"true":"false")<<"]\n";
    }
    if(c.opcode==0x11&&previous_opcode==(reference_trace?0xDD:0xD0)) {
      const int n=depth(),y=scan_row();
      std::cout<<"E [\"pair\","<<n<<','<<y<<','<<column(n)<<','<<column(y)<<"]\n";
    }
    if(c.opcode==0x5E&&previous_opcode==0xBC) {
      const int n=depth(),q=column(n);
      std::cout<<"E [\"while_a\","<<n<<','<<q<<','<<(q==0?"true":"false")<<"]\n";
    }
    if(c.opcode==0x5E&&previous_opcode==0x11&&before_previous_opcode==1) {
      const int b=integer(memory(11));
      std::cout<<"E [\"until_flag\","<<b<<','<<(b==1?"true":"false")<<"]\n";
    }
    if(c.opcode==0x5E&&previous_opcode==0x11&&before_previous_opcode==8) {
      const int n=depth();
      std::cout<<"E [\"until_x\","<<n<<','<<(n==8?"true":"false")<<"]\n";
      if(n==8)trace_ended=true;
    }
  }
  before_previous_opcode=previous_opcode;
  previous_opcode=c.opcode;
  return false;
}
static void step(){core_61::step();++steps;}
int main(int argc,char** argv) {
  if(argc<2||argc>3)return 2;
  if(argc==3) {
    const std::string mode=argv[2];
    if(mode!="trace"&&mode!="reference")return 2;
    trace=true;reference_trace=mode=="reference";
  }
  std::cout<<std::setprecision(15);
  uint8_t code[105]={};unsigned extent=0;
  std::ifstream input(argv[1]);std::string line;
  if(!input)return 3;
  while(std::getline(input,line)) {
    std::istringstream in(line);std::string command,payload;unsigned at;
    in>>command;
    if(command=="reinit"||command=="run")continue;
    if(command!="hin"||!(in>>at>>payload)||at!=extent||payload.empty()||
       payload.size()%2||payload.size()>48||at+payload.size()/2>105)return 4;
    for(unsigned i=0;i<payload.size();i+=2)
      code[at+i/2]=std::stoi(payload.substr(i,2),nullptr,16);
    extent+=payload.size()/2;
  }
  core_61::set_expanded_program_mode(false);
  core_61::enable();core_61::set_code_page(code);core_61::set_IP(0);
  if(!core_61::set_mk61_program_boundary_hook(boundary))return 5;
  core_61::clear_displayed();
  for(int i=0;i<4;i++){MK61Emu_SetKeyPress(2,9);step();if(core_61::is_RUN())break;}
  MK61Emu_SetKeyPress(0,0);
  for(int i=0;i<512;i++){step();if(core_61::is_RUN()||core_61::is_displayed())break;}
  while(core_61::is_RUN()&&steps<100000)step();
  std::cout<<"{\"commands\":"<<commands<<",\"core_steps\":"<<steps
    <<",\"running\":"<<(core_61::is_RUN()?"true":"false")
    <<",\"error\":"<<(core_61::has_error()?"true":"false")
    <<",\"ip\":"<<unsigned(core_61::get_IP())<<",\"x\":"<<xvalue()<<",\"regs\":[";
  for(int r=0;r<15;r++){if(r)std::cout<<',';std::cout<<memory(r);}
  std::cout<<"]}\n";
}
