#ifndef MK61_LANGUAGE_FLASH_HPP
#define MK61_LANGUAGE_FLASH_HPP
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <limits.h>

namespace language_vm { namespace flash {
// Logical files are independent of C9's per-inode length. The resident backs
// them with bounded, ordinary binary chunks; no source-sized RAM is borrowed.
enum Space : uint8_t { INDEX_A, INDEX_B, IMAGE, BOUNDARIES };
struct IO {
  void* context;
  bool (*read)(void*,Space,uint32_t,uint8_t*,uint16_t);
  bool (*write)(void*,Space,uint32_t,const uint8_t*,uint16_t);
  bool (*truncate)(void*,Space,uint32_t);
  bool (*service)(void*) = nullptr;
  // Shared resident passes: language 1/2 builds the index; 0x80 marks
  // integer spans after emission. The Program object remains caller-owned.
  bool (*prepare)(void*,void*,uint8_t) = nullptr;
  bool (*lookup)(void*,uint32_t,bool,uint32_t*) = nullptr;
  bool poll() const {return !service || service(context);}
};
static constexpr unsigned READ_BYTES=256, WRITE_BYTES=1024;
inline uint16_t word(const uint8_t* p) {return uint16_t(p[0]|uint16_t(p[1])<<8);}
inline uint32_t dword(const uint8_t* p) {return word(p)|uint32_t(word(p+2))<<16;}
inline void word(uint8_t* p,uint16_t n) {p[0]=uint8_t(n);p[1]=uint8_t(n>>8);}
inline void dword(uint8_t* p,uint32_t n) {word(p,uint16_t(n));word(p+2,uint16_t(n>>16));}
struct Input {
  void* context;
  bool (*read)(void*,uint32_t,uint8_t*,uint16_t);
  uint32_t size;
};
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
// Keep a bounded opcode window for this invocation. Its bytes remain valid
// when resident line-map reads displace the C9 page; no pointer survives APP
// replacement. Opcode and operand reads share this bounded window.
class Reader {
  // Narrow immediates keep fast opcode/operand hits inside the APP budget.
  static constexpr unsigned WINDOW_BYTES=128;
  mutable Input input_;
  mutable uint32_t begin_=UINT32_MAX;mutable uint8_t page_[WINDOW_BYTES];
public:
  explicit Reader(Input input):input_(input) {}
  bool good() const {return input_.read!=nullptr;}
  void fail() const {input_.read=nullptr;begin_=UINT32_MAX;}
  uint32_t size() const {return input_.size;}
  void invalidate() const {begin_=UINT32_MAX;}
  __attribute__((noinline)) bool read(uint32_t at,void* output,size_t n) const {
    if(!good() || at>size() || n>size()-at || (!output && n))return false;
    if(!n)return true;
    auto* out=static_cast<uint8_t*>(output);
    const uint32_t offset=at-begin_;
    if(at>=begin_ && n+offset<=WINDOW_BYTES) {
      memcpy(out,page_+offset,n);return true;
    }
    do {
      const uint16_t count=uint16_t(n<READ_BYTES?n:READ_BYTES);
      if(!input_.read(input_.context,at,out,count)){fail();return false;}
      at+=count;out+=count;n-=count;
    } while(n);
    return true;
  }
  uint8_t at(uint32_t offset) const {
    if(offset>=size())return 0;
    const uint32_t begin=offset/WINDOW_BYTES*WINDOW_BYTES;
    if(begin_!=begin) {
      const uint32_t remaining=size()-begin;
      const uint16_t count=uint16_t(remaining<WINDOW_BYTES?remaining:WINDOW_BYTES);
      if(!read(begin,page_,count))return 0;
      begin_=begin;
    }
    return page_[offset%WINDOW_BYTES];
  }
};
#else
class Reader {
  Input input_;
  mutable uint8_t page_[2][READ_BYTES];
  mutable uint32_t begin_[2]={UINT32_MAX,UINT32_MAX};
  mutable uint16_t used_[2]={0,0};
  mutable uint8_t recent_=0;
  mutable bool good_=true;
public:
  explicit Reader(Input input):input_(input) {good_=input.read!=nullptr;}
  bool good() const {return good_;}
  void fail() const {good_=false;}
  uint32_t size() const {return input_.size;}
  void invalidate() const {begin_[0]=begin_[1]=UINT32_MAX;used_[0]=used_[1]=0;}
  bool read(uint32_t at,void* out,size_t n) const {
    if(!good_ || at>size() || n>size()-at || (!out && n))return false;
    auto* bytes=static_cast<uint8_t*>(out);
    while(n) {
      unsigned slot=0;
      for(;slot<2;++slot)if(begin_[slot]!=UINT32_MAX && at>=begin_[slot] && at-begin_[slot]<used_[slot])break;
      if(slot==2) {
        slot=1-recent_;begin_[slot]=at/READ_BYTES*READ_BYTES;
        const uint32_t remaining=size()-begin_[slot];
        used_[slot]=uint16_t(remaining<READ_BYTES?remaining:READ_BYTES);
        if(!input_.read(input_.context,begin_[slot],page_[slot],used_[slot])) {good_=false;return false;}
      }
      recent_=uint8_t(slot);
      unsigned count=used_[slot]-(at-begin_[slot]);if(count>n)count=unsigned(n);
      memcpy(bytes,page_[slot]+(at-begin_[slot]),count);at+=count;bytes+=count;n-=count;
    }
    return true;
  }
  uint8_t at(uint32_t position) const {uint8_t b=0;(void)read(position,&b,1);return b;}
};
#endif
// A cursor never exposes a pointer into a replaceable page. Raw expression
// images use the same decoder without copying their operands.
class Cursor {
  const uint8_t* bytes_;const Reader* reader_;uint32_t offset_;
public:
  Cursor(const uint8_t* bytes,const Reader* reader,uint32_t offset):bytes_(bytes),reader_(reader),offset_(offset) {}
  __attribute__((noinline)) uint8_t operator[](uint32_t n) const {return reader_?reader_->at(offset_+n):bytes_[offset_+n];}
  uint8_t operator*() const {return (*this)[0];}
  Cursor operator+(uint32_t n) const {return {bytes_,reader_,offset_+n};}
  const uint8_t* raw() const {return reader_?nullptr:bytes_+offset_;}
  bool read(void* out,uint16_t n) const {
    if(reader_)return reader_->read(offset_,out,n);
    memcpy(out,bytes_+offset_,n);return true;
  }
};
inline uint16_t word(Cursor p) {uint8_t bytes[2]={};(void)p.read(bytes,sizeof(bytes));return word(bytes);}
inline uint32_t dword(Cursor p) {uint8_t bytes[4]={};(void)p.read(bytes,sizeof(bytes));return dword(bytes);}
// One dirty page, with exact random patching for forward IF/FOR operands.
// The caller owns publication: failure never publishes a partial manifest.
class Writer {
  IO io_;Space space_;
  uint8_t page_[WRITE_BYTES];
  uint32_t begin_=UINT32_MAX,size_=0;
  bool dirty_=false,good_=true;
  bool load(uint32_t at) {
    const uint32_t begin=at/WRITE_BYTES*WRITE_BYTES;
    if(begin==begin_)return true;
    if(!flush())return false;
    memset(page_,0,sizeof(page_));
    if(begin<size_) {
      const uint32_t remaining=size_-begin;
      const uint16_t n=uint16_t(remaining<WRITE_BYTES?remaining:WRITE_BYTES);
      if(!io_.read(io_.context,space_,begin,page_,n))return good_=false;
    }
    begin_=begin;return true;
  }
public:
  Writer(IO io,Space space,uint32_t size=0):io_(io),space_(space),size_(size) {}
  bool good() const {return good_;}
  uint32_t size() const {return size_;}
  bool flush() {
    if(!good_)return false;
    if(dirty_) {
      if(!io_.write(io_.context,space_,begin_,page_,sizeof(page_)) || !io_.poll())return good_=false;
      dirty_=false;
    }
    return true;
  }
  bool write(uint32_t at,const void* input,size_t n) {
    if(!good_ || n>UINT32_MAX-at)return false;
    const auto* bytes=static_cast<const uint8_t*>(input);
    while(n) {
      if(!load(at))return false;
      unsigned count=WRITE_BYTES-(at-begin_);if(count>n)count=unsigned(n);
      memcpy(page_+(at-begin_),bytes,count);dirty_=true;
      at+=count;bytes+=count;n-=count;if(at>size_)size_=at;
    }
    return true;
  }
  bool reset(Space space,uint32_t size=0) {
    if(!flush())return false;
    space_=space;size_=size;begin_=UINT32_MAX;dirty_=false;return true;
  }
  bool byte(uint32_t at,uint8_t value) {return write(at,&value,1);}
  bool read(uint32_t at,void* output,size_t n) const {
    if(!good_ || at>size_ || n>size_-at || (!output && n))return false;
    auto* bytes=static_cast<uint8_t*>(output);
    while(n) {
      const uint32_t begin=at/WRITE_BYTES*WRITE_BYTES;
      unsigned count=WRITE_BYTES-(at-begin);if(count>n)count=unsigned(n);
      if(begin==begin_)memcpy(bytes,page_+(at-begin),count);
      else if(!io_.read(io_.context,space_,at,bytes,uint16_t(count)))return false;
      at+=count;bytes+=count;n-=count;
    }
    return true;
  }
};

struct Line {uint32_t number,pc;uint16_t begin,end;};
// Sixteen bytes per disk record keep patches within one output page. No C++
// padding/layout is written to Flash. Counts are bounded only by source size.
static constexpr unsigned LINE_BYTES=16;
class LineIndex {
  IO io_;Space space_;
  uint16_t count_=0;
  bool good_=true;
public:
  LineIndex(IO io,Space space,uint16_t count=0):io_(io),space_(space),count_(count) {}
  uint16_t size() const {return count_;}
  Space space() const {return space_;}
  bool good() const {return good_;}
  static void encode(uint8_t* p,Line line) {
    dword(p,line.number);dword(p+4,line.pc);word(p+8,line.begin);word(p+10,line.end);memset(p+12,0,4);
  }
  static Line decode(const uint8_t* p) {return {dword(p),dword(p+4),word(p+8),word(p+10)};}
  bool get(uint16_t i,Line& line) const {
    uint8_t record[LINE_BYTES];
    if(i>=count_ || !io_.read(io_.context,space_,uint32_t(i)*LINE_BYTES,record,sizeof(record)))return false;
    line=decode(record);return true;
  }
  bool set(Writer& output,uint16_t i,Line line) {
    uint8_t record[LINE_BYTES];encode(record,line);
    if(i>count_ || (i==count_ && count_==UINT16_MAX) || !output.write(uint32_t(i)*LINE_BYTES,record,sizeof(record)))return good_=false;
    if(i==count_)++count_;
    return true;
  }
  // Bottom-up external merge; all runs stay on Flash. Two one-record heads
  // and a single output page suffice even for reverse-ordered source files.
  bool sort(bool ordered) {
    if(ordered)return true;
    Writer output(io_,space_==INDEX_A?INDEX_B:INDEX_A);
    return sort(ordered,output);
  }
  bool sort(bool ordered,Writer& output) {
    if(ordered)return true;
    for(uint32_t run=1;run<count_;run*=2) {
      const Space target=space_==INDEX_A?INDEX_B:INDEX_A;
      if(!output.reset(target) || !io_.truncate(io_.context,target,0))return good_=false;
      uint16_t written=0;
      for(uint32_t first=0;first<count_;first+=run*2) {
        uint32_t left=first;
        const uint32_t middle=first+run<count_?first+run:count_;
        uint32_t right=middle;
        const uint32_t last=first+run*2<count_?first+run*2:count_;
        while(left<middle || right<last) {
          Line a{},b{},line;
          if(left<middle && !get(uint16_t(left),a))return good_=false;
          if(right<last && !get(uint16_t(right),b))return good_=false;
          if(right==last || (left<middle && a.number<=b.number)) {line=a;++left;}
          else {line=b;++right;}
          uint8_t record[LINE_BYTES];encode(record,line);
          if(!output.write(uint32_t(written++)*LINE_BYTES,record,sizeof(record)))return good_=false;
        }
      }
      if(!output.flush())return good_=false;
      space_=target;
    }
    return true;
  }
  int find(uint32_t number) const {
    uint32_t low=0,high=count_;
    while(low<high) {
      const uint16_t mid=uint16_t(low+(high-low)/2);Line line;
      if(!get(mid,line))return -2;
      if(line.number<number)low=mid+1U;else high=mid;
    }
    if(low==count_)return -1;
    Line line;if(!get(uint16_t(low),line))return -2;
    return line.number==number?int(low):-1;
  }
};
}}
#endif
