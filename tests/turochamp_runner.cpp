// Host transport only: every chess operation executes the shipping BASIC.
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "tinybasic.hpp"
#include "keyboard_layout.hpp"
#include "mk8_codec.hpp"
#ifdef MK61_LANGUAGE_VM_TEST
#include "language_bytecode.hpp"
#endif
#include "../tools/turochamp/layout.hpp"

extern "C" void TinyBasicTestReset();
extern "C" TinyBasicRunStatus TinyBasicTestRunSource(const char*);
extern "C" double TinyBasicTestArray(int);
extern "C" bool TinyBasicTestSetArray(int,double);
extern "C" double TinyBasicTestMkRegister(int);
extern "C" const char* TinyBasicTestError();
extern "C" void TinyBasicTestSetKeys(const int*,int);
extern "C" void TinyBasicTestSetPauseEsc(bool);
extern "C" void TinyBasicTestSetGeometry(int,int);
extern "C" const char* TinyBasicTestLcdLine(int);

namespace {
std::map<int,std::string> parts;
double get(int at) {return TinyBasicTestArray(at);}
void put(int at,double x) {
  if(!TinyBasicTestSetArray(at,x))throw std::runtime_error("array address");
}
int code() {return (int)TinyBasicTestMkRegister(14);}
void part(int id) {
  if(!parts.count(id))throw std::runtime_error("missing BASIC module "+std::to_string(id));
  if(std::getenv("TURO_TRACE"))std::cerr<<"part "<<id<<" phase "<<get(tc::PHASE)
      <<" cursor "<<get(tc::GEN_CURSOR)<<" move "<<get(tc::GLMOVE)<<" sp "<<get(tc::SP)<<'\n';
  const auto result=TinyBasicTestRunSource(parts.at(id).c_str());
  if(result!=TinyBasicRunStatus::COMPLETED)
    throw std::runtime_error("BASIC module "+std::to_string(id)+": "+TinyBasicTestError());
}
void call(int id) {
  put(tc::SP,1);put(tc::RETURNS,0);put(tc::PHASE,0);
  for(unsigned calls=0;calls<50000000;calls++) {
    part(id);id=code();
    if(!id)return;
  }
  throw std::runtime_error("BASIC dispatch limit, nodes "+std::to_string((int)get(tc::NODES))+
                          ", depth "+std::to_string((int)get(tc::DFS)));
}
void init() {
  TinyBasicTestReset();TinyBasicTestSetGeometry(26,9);part(tc::M_INIT);
}
int square(const std::string& s) {
  return 21+(s[0]-'a')+10*(s[1]-'1');
}
std::string name(int s) {
  return std::string{char('a'+s%10-1),char('1'+s/10-2)};
}
std::string uci(int m) {
  std::string x=name(m%128)+name((m/128)%128);
  int p=m/16384;
  if(p)x+=std::string("  nbrq").at(p);
  return x;
}
int encode_move(const std::string& m) {
  int p=0;
  if(m.size()==5)p=(int)std::string("  nbrq").find(m[4]);
  return square(m.substr(0,2))+128*square(m.substr(2,2))+16384*p;
}
void fen(const std::string& value) {
  init();std::istringstream in(value);std::string board,side,rights,ep;
  int half,full;in>>board>>side>>rights>>ep>>half>>full;
  if(!in)throw std::runtime_error("FEN fields");
  for(int r=2;r<=9;r++)for(int f=1;f<=8;f++)put(10*r+f,0);
  int row=9,file=1;
  for(char p:board) {
    if(p=='/'){row--;file=1;continue;}
    if(p>='1'&&p<='8'){file+=p-'0';continue;}
    int piece=(int)std::string(" pnbrqk").find((char)std::tolower(p));
    if(piece<1||piece>6||row<2||file>8)throw std::runtime_error("FEN board");
    if(std::islower(p))piece=-piece;
    int s=10*row+file++;put(s,piece);
    if(piece==6)put(tc::WK,s);
    if(piece==-6)put(tc::BK,s);
  }
  put(tc::SIDE,side=="w"?1:-1);put(tc::RIGHTS,0);
  for(unsigned i=0;i<4;i++)if(rights.find("KQkq"[i])!=std::string::npos)
    put(tc::RIGHTS,get(tc::RIGHTS)+(1U<<i));
  put(tc::EP,ep=="-"?0:square(ep));put(tc::HALF,half);put(tc::FULL,full);
  put(tc::HEP,get(tc::EP));
}
std::string fen() {
  std::string out;
  for(int r=9;r>=2;r--) {
    int empty=0;
    for(int f=1;f<=8;f++) {
      int p=(int)get(10*r+f);
      if(!p){empty++;continue;}
      if(empty){out+=char('0'+empty);empty=0;}
      char c=std::string(" pnbrqk").at(std::abs(p));
      out+=p>0?(char)std::toupper(c):c;
    }
    if(empty)out+=char('0'+empty);
    if(r>2)out+='/';
  }
  out+=get(tc::SIDE)>0?" w ":" b ";
  std::string rights;
  for(int i=0;i<4;i++)if(((int)get(tc::RIGHTS)&(1<<i)))rights+="KQkq"[i];
  out+=rights.empty()?"-":rights;
  out+=' ';out+=get(tc::EP)>0?name((int)get(tc::EP)):"-";
  out+=' ';out+=std::to_string((int)get(tc::HALF));
  out+=' ';out+=std::to_string((int)get(tc::FULL));return out;
}
std::vector<int> moves(int mode=2) {
  put(tc::GEN_CURSOR,0);
  std::vector<int> result;
  for(;;) {
    put(tc::GLSTATE,tc::GEN_CURSOR);put(tc::GLSIDE,get(tc::SIDE));
    put(tc::GLMODE,mode);put(tc::GLPIECE,0);put(tc::GLTYPE,0);
    call(tc::M_LEGAL);
    int m=(int)get(tc::GLMOVE);if(!m)break;
    result.push_back(m);
  }
  return result;
}
void apply_move(int m,int frame) {put(tc::APMOVE,m);put(tc::APFRAME,frame);call(tc::M_MAKE);}
void undo(int frame) {put(tc::APFRAME,frame);call(tc::M_UNMAKE);}
uint64_t perft(int depth) {
  if(!depth)return 1;
  auto list=moves();if(depth==1)return list.size();
  uint64_t n=0;
  for(int m:list) {
    int frame=tc::STACK+7*(depth-1);
    apply_move(m,frame);n+=perft(depth-1);undo(frame);
  }
  return n;
}
int raw_key(int logical) {
  const auto& k=keyboard_layout::ACTIVE;
  if(logical>=0&&logical<=9)return k.digit[logical];
  switch(logical) {
    case 15:return k.left;case 16:return k.right;case 17:return k.shg_left;
    case 18:return k.shg_right;case 19:return k.ok;case 20:return k.esc;
    case 21:return k.run;case 22:return k.cx;case 25:return k.user;
    default:throw std::runtime_error("unknown UI key");
  }
}
void ui(int id,const std::vector<int>& logical) {
  TinyBasicTestSetGeometry(26,9);std::vector<int> keys;
  for(int key:logical)keys.push_back(raw_key(key));
  TinyBasicTestSetKeys(keys.data(),(int)keys.size());TinyBasicTestSetPauseEsc(true);
  for(unsigned calls=0;calls<50000000;calls++) {
    if(!parts.count(id))throw std::runtime_error("missing UI module");
    if(std::getenv("TURO_TRACE"))std::cerr<<"UI part "<<id<<" phase "<<get(tc::PHASE)
        <<" key "<<get(tc::UI_KEY)<<" sp "<<get(tc::SP)<<'\n';
    const auto status=TinyBasicTestRunSource(parts.at(id).c_str());
    if(status==TinyBasicRunStatus::STOPPED)break;
    if(status!=TinyBasicRunStatus::COMPLETED)throw std::runtime_error(
        "UI BASIC module "+std::to_string(id)+": "+TinyBasicTestError());
    id=code();if(id==99)break;
  }
  TinyBasicTestSetPauseEsc(false);
}
}
int main(int argc,char**argv) {
  try {
    if(argc!=2)return 2;
    for(const auto& module:tc::MODULES) {
      std::ifstream file(std::string(argv[1])+"/"+module.name+".tbi");
      if(!file)throw std::runtime_error(std::string("missing BASIC module ")+module.name);
      {
        const std::string utf8(std::istreambuf_iterator<char>(file),{});
        std::string m8(utf8.size(),'\0');usize size=0;
        if(!mk8::from_utf8((const u8*)utf8.data(),utf8.size(),
                           (u8*)m8.data(),m8.size(),size))
          throw std::runtime_error("invalid source encoding");
        m8.resize(size);parts[module.id]=m8;
#ifdef MK61_LANGUAGE_VM_TEST
        const auto result=language_vm::compile(language_vm::Language::BASIC,
            m8.data(),(uint16_t)m8.size(),nullptr,language_vm::MAX_IMAGE);
        if(result.error!=language_vm::Error::NONE)
          throw std::runtime_error(std::string(module.name)+": "+
              language_vm::error_name(result.error)+" at "+std::to_string(result.source_offset));
#endif
      }
    }
    init();std::string line;std::cout<<std::setprecision(17);
    while(std::getline(std::cin,line)) {
      std::istringstream in(line);std::string cmd;in>>cmd;
      if(cmd=="fen") {fen(line.substr(4));std::cout<<"ok\n";}
      else if(cmd=="get") {int n;in>>n;std::cout<<get(n)<<'\n';}
      else if(cmd=="set") {int n;double v;in>>n>>v;put(n,v);std::cout<<"ok\n";}
      else if(cmd=="call") {int n;in>>n;call(n);std::cout<<"ok\n";}
      else if(cmd=="moves") {int mode=2;in>>mode;auto list=moves(mode);std::vector<std::string>x;
        for(int m:list)x.push_back(uci(m));std::sort(x.begin(),x.end());
        for(const auto&m:x)std::cout<<m<<' ';std::cout<<'\n';}
      else if(cmd=="perft") {int n;in>>n;std::cout<<perft(n)<<'\n';}
      else if(cmd=="play") {std::string m;in>>m;apply_move(encode_move(m),tc::ROOTTMP);call(tc::M_HISTORY);std::cout<<fen()<<'\n';}
      else if(cmd=="repeat") {put(tc::REPDEP,0);call(tc::M_REPEAT);std::cout<<get(tc::REPRESULT)<<'\n';}
      else if(cmd=="status") {put(tc::REPDEP,0);call(tc::M_STATUS);
        std::cout<<get(tc::STAT)<<' '<<get(tc::CHECK)<<' '<<get(tc::CLAIM)<<' '
                 <<get(tc::REPS)<<' '<<get(tc::MATW)<<' '<<get(tc::MATB)<<'\n';}
      else if(cmd=="eval") {int side;in>>side;put(tc::PCS,side);call(tc::M_EVAL);
        std::cout<<get(tc::PE)/10<<' '<<get(tc::ETHREAT)<<'\n';}
      else if(cmd=="best") {put(tc::REPDEP,0);call(tc::M_STATUS);call(tc::M_SEARCH);
        int m=(int)get(tc::BEST);std::cout<<(m?uci(m):"draw")<<' '
            <<get(tc::ROOTVAL)<<' '<<get(tc::NODES)<<'\n';}
      else if(cmd=="claims") {call(tc::M_CLAIMS);int m=(int)get(tc::H_MOVE);
        std::cout<<get(tc::CLAIM)<<' '<<(m?uci(m):"-")<<'\n';}
      else if(cmd=="ui"||cmd=="keys") {std::vector<int> keys;int id,k;
        if(cmd=="ui"){init();id=code();}else {in>>id;put(tc::PHASE,0);put(tc::SP,0);}
        while(in>>k)keys.push_back(k);
        ui(id,keys);std::cout<<fen()<<'\n';}
      else if(cmd=="screen") {
        const char* hex="0123456789abcdef";
        for(int r=0;r<9;r++)for(int c=0;c<26;c++) {
          auto byte=(unsigned char)TinyBasicTestLcdLine(r)[c];
          std::cout<<hex[byte>>4]<<hex[byte&15];
        }
        std::cout<<'\n';
      }
      else if(cmd=="undo") {undo(tc::ROOTTMP);std::cout<<fen()<<'\n';}
      else if(cmd=="position")std::cout<<fen()<<'\n';
      else if(cmd=="quit")return 0;
      else throw std::runtime_error("unknown host command");
      std::cout.flush();
    }
  } catch(const std::exception&e) {std::cerr<<e.what()<<'\n';return 1;}
}
