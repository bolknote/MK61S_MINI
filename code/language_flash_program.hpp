#ifndef MK61_LANGUAGE_FLASH_PROGRAM_HPP
#define MK61_LANGUAGE_FLASH_PROGRAM_HPP
#include "language_vm_abi.hpp"
#include "focal_syntax.hpp"
#include "language_integer_spans.hpp"

namespace language_vm { namespace flash {
static constexpr uint32_t HEADER_BYTES=language_vm::HEADER_SIZE, MAP_BYTES=8, NO_ADDRESS=UINT32_MAX;
class Program {
  IO io_;
  source::Reader const& source_;
  LineIndex index_;
  Writer writer_;
  Error error_=Error::NONE;
  uint32_t source_crc_=0,code_end_=0,image_size_=0;
  uint8_t* positions_data_=nullptr;
  uint16_t source_window_=0,positions_size_=0;
  struct Finish {
    uint32_t bytes;
    uint16_t positions;
    uint8_t language,stack,flags;
  } finish_{};
  enum Pass : uint8_t { POSITIONS=0x80, IMAGE_START, IMAGE_FINISH, READ_LINE };
  struct LineCall {Program* program;uint16_t index;Line value;};
  bool shared(uint8_t pass) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(MK61_LANGUAGE_VM_COMPILER)
    return io_.prepare && io_.prepare(io_.context,this,pass);
#else
    return io_.prepare?io_.prepare(io_.context,this,pass):prepare_pass(pass);
#endif
  }
public:
  Program(const source::Reader& source,IO io):io_(io),source_(source),index_(io,INDEX_A),writer_(io,INDEX_A) {}
  ~Program(){if(source_window_)source_.restore_window(source_window_);}
  bool reserve_positions(uint32_t bytes) {
    if(bytes>UINT16_MAX)return false;
    positions_data_=source_.borrow_tail(uint16_t(bytes),source_window_);
    positions_size_=uint16_t(bytes);return positions_data_!=nullptr;
  }
  Error error() const {return error_;}
  void fail(Error e=Error::IO) {if(error_==Error::NONE)error_=e;}
  bool poll() {
    if(error_!=Error::NONE)return false;
    if(!io_.poll()){fail(Error::STOPPED);return false;}
    return true;
  }
  uint16_t count() const {return index_.size();}
  uint32_t code() const {return HEADER_BYTES+uint32_t(count())*MAP_BYTES;}
  uint32_t size() const {return image_size_?image_size_:writer_.size();}
  bool prepare(Language language) {
    return shared(uint8_t(language));
  }
  static bool prepare_shared(void* raw,uint8_t pass) {
    if(pass==READ_LINE) {
      auto& call=*static_cast<LineCall*>(raw);call.value=call.program->line_impl(call.index);
      return call.program->error()==Error::NONE;
    }
    return static_cast<Program*>(raw)->prepare_pass(pass);
  }
  bool prepare_pass(uint8_t pass) {
    switch(pass) {
      case uint8_t(Language::BASIC):case uint8_t(Language::FOCAL):return prepare_index(Language(pass));
      case POSITIONS:return begin_positions_impl();
      case IMAGE_START:return begin_image_impl();
      case IMAGE_FINISH:return finish_image();
      default:fail();return false;
    }
  }
  bool prepare_index(Language language) {
    if(!source_.good() || source_.contains_nul()) {fail(source_.good()?Error::SYNTAX:Error::IO);return false;}
    if(!io_.truncate(io_.context,INDEX_A,0) || !io_.truncate(io_.context,IMAGE,0)) {fail();return false;}
    source::CursorScope scope(source_);source::Cursor p(source_);
    const source::Cursor end(source_,source_.size());
    bool ordered=true;uint32_t previous=0;
    while(p<end) {
      const auto physical=p+p.line_end(end);const auto line_end=physical;
      p=focal_next::skip(p,line_end);
      if(p<line_end) {
        uint32_t number=0;
        if(language==Language::BASIC) {
          if(!focal_next::digit(*p)) {fail(Error::LINE);return false;}
          do {number=number*10+unsigned(*p++-'0');if(number>32767){fail(Error::LINE);return false;}}
          while(p<line_end && focal_next::digit(*p));
        } else {
          focal_next::Address address;
          if(!focal_next::address(p,line_end,address) || !address.exact) {fail(Error::LINE);return false;}
          number=focal_next::key(address);
        }
        if(!number || p==line_end || !focal_next::space(*p)) {fail(Error::LINE);return false;}
        p=focal_next::skip(p,line_end);
        if(p==line_end) {fail(Error::SYNTAX);return false;}
        ordered=ordered && number>previous;previous=number;
        if(!index_.set(writer_,count(),{number,0,uint16_t(p-source::Cursor(source_)),uint16_t(line_end-source::Cursor(source_))})) {fail();return false;}
      }
      p=physical+(physical<end);
      if(!poll())return false;
    }
    if(!count()) {fail(Error::LINE);return false;}
    if(!writer_.flush() || !index_.sort(ordered,writer_)) {fail();return false;}
    if(!writer_.reset(index_.space(),uint32_t(count())*LINE_BYTES)){fail();return false;}
    uint32_t last=0;
    for(uint16_t i=0;i<count();++i) {
      const auto record=line_impl(i);if(error_!=Error::NONE)return false;
      if(record.number<=last) {fail(Error::LINE);return false;}last=record.number;
    }
    source_crc_=source_.checksum();
    if(!source_.good()) {fail();return false;}
    return true;
  }
  Line line(uint16_t n) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(MK61_LANGUAGE_VM_COMPILER)
    LineCall call;call.program=this;call.index=n;
    if(!io_.prepare || !io_.prepare(io_.context,&call,READ_LINE)) {fail();return {};}
    return call.value;
#else
    return line_impl(n);
#endif
  }
  Line line_impl(uint16_t n) {
    // Labels/source ranges are immutable. Layout may read a not-yet-flushed
    // PC, which cannot affect fixed-width sizing. begin_image flushes every
    // final PC before emission reads it, so the shared index reader suffices.
    Line record{};
    if(!poll() || !index_.get(n,record)) {fail();return {};}
    return record;
  }

  void pc(uint16_t n,uint32_t pc) {
    auto record=line(n);record.pc=pc;
    if(error_==Error::NONE && !index_.set(writer_,n,record))fail();
  }
  int find(uint32_t number,bool group=false) {
    uint32_t low=0,high=count();
    while(low<high) {
      const uint16_t mid=uint16_t(low+(high-low)/2);const auto record=line(mid);
      if((group?record.number/1000:record.number)<number)low=mid+1U;else high=mid;
    }
    if(low==count())return -1;
    const auto record=line(uint16_t(low));
    return (group?record.number/1000:record.number)==number?int(low):-1;
  }
  bool begin_image() {
    return shared(IMAGE_START);
  }
  bool begin_image_impl() {
    if(!writer_.reset(IMAGE)) {fail();return false;}
    uint8_t header[HEADER_BYTES]={};
    if(!writer_.write(0,header,sizeof(header))) {fail();return false;}
    for(uint16_t i=0;i<count();++i) {
      const auto record=line_impl(i);uint8_t bytes[MAP_BYTES];
      dword(bytes,record.number);dword(bytes+4,record.pc);
      if(!writer_.write(HEADER_BYTES+uint32_t(i)*MAP_BYTES,bytes,sizeof(bytes))) {fail();return false;}
    }
    return error_==Error::NONE;
  }
  void byte(uint32_t at,uint8_t b) {if(!writer_.byte(at,b))fail();}
  bool begin_positions() {
    return shared(POSITIONS);
  }
  bool begin_positions_impl() {
    if(!writer_.flush() || !io_.truncate(io_.context,BOUNDARIES,0) ||
       !writer_.reset(BOUNDARIES)) {fail();return false;}
    return true;
  }
  bool source_bytes(uint32_t at,const uint8_t* bytes,uint16_t n) {
    if(positions_data_) {
      if(at>positions_size_ || n>positions_size_-at)fail(Error::FULL);
      else memcpy(positions_data_+at,bytes,n);
    } else if(!writer_.write(at,bytes,n))fail();
    return error_==Error::NONE;
  }
  void address(uint32_t at,uint32_t value) {uint8_t bytes[4];dword(bytes,value);if(!writer_.write(at,bytes,sizeof(bytes)))fail();}
  bool optimize() {
    auto read=[&](uint32_t at) {uint8_t b=0;if(!writer_.read(at,&b,1))fail();return b;};
    unsigned budget=0;
    detail::integer_spans(code(),code_end_,read,
        [&](uint32_t pc,Op op) {
          if(error_!=Error::NONE || ((budget++&31U)==0 && !poll()))return uint32_t(0);
          const uint8_t width=wire_widths[unsigned(op)];
          if(width!=255)return pc+width;
          uint8_t bytes[4];const unsigned prefix=op==Op::DATA?5:3;
          if(!writer_.read(pc+1,bytes,prefix-1)) {fail();return uint32_t(0);}
          const uint32_t n=prefix==5?dword(bytes):word(bytes);
          return pc+prefix+((op==Op::ON_GOTO || op==Op::ON_GOSUB)?n*2:n);
        },[&](uint32_t pc,Op op){byte(pc,uint8_t(op));});
    return error_==Error::NONE && writer_.good();
  }
  bool finish(Language language,uint32_t size,uint8_t stack,bool rf,
              uint16_t positions=0,uint32_t position_bytes=0) {
    code_end_=size;
    finish_={position_bytes,positions,uint8_t(language),stack,uint8_t(rf?2:0)};
    return shared(IMAGE_FINISH);
  }
  bool finish_image() {
    uint32_t size=code_end_;const auto& f=finish_;
    const auto positions=f.positions;const auto position_bytes=f.bytes;
    if(!optimize()){fail();return false;}
    if(positions) {
      uint8_t buffer[64];
      for(uint32_t at=0;at<position_bytes;) {
        const uint16_t n=uint16_t(position_bytes-at<sizeof(buffer)?position_bytes-at:sizeof(buffer));
        if(positions_data_)memcpy(buffer,positions_data_+at,n);
        else if(!io_.read(io_.context,BOUNDARIES,at,buffer,n)) {fail();return false;}
        if(!writer_.write(size+at,buffer,n) || !poll()) {fail();return false;}
        at+=n;
      }
      size+=position_bytes;dword(buffer,position_bytes);
      if(!writer_.write(size,buffer,4)){fail();return false;}
      size+=4;
    }
    image_size_=size;
    uint32_t crc=~uint32_t(0);uint8_t bytes[64];
    for(uint32_t at=HEADER_BYTES;at<size;) {
      const uint16_t n=uint16_t(size-at<sizeof(bytes)?size-at:sizeof(bytes));
      if(!writer_.read(at,bytes,n)) {fail();return false;}
      for(unsigned i=0;i<n;++i) {crc^=bytes[i];for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xEDB88320U&(0U-(crc&1U)));}
      at+=n;
      if(!io_.poll()) {fail(Error::STOPPED);return false;}
    }
    uint8_t header[HEADER_BYTES]={};memcpy(header,"LBV2",4);
    header[4]=VERSION;header[5]=f.language;header[6]=f.stack?f.stack:1;header[7]=f.flags;
    dword(header+8,size);dword(header+12,code());word(header+16,source_.size());word(header+18,count());
    dword(header+20,source_crc_);dword(header+24,~crc);dword(header+28,code_end_);word(header+38,positions);
    if(!writer_.write(0,header,sizeof(header)) || !writer_.flush())fail();
    return error_==Error::NONE;
  }
};
// Runtime, Program and resident page have fixed, disjoint homes. Lend only
// the unused gap after Program to the source reader, including large files.
static constexpr uint16_t SOURCE_WINDOW_OFFSET =
    uint16_t((FLASH_FRONTEND_BYTES+sizeof(Program)+7U)&~size_t(7U));
static_assert(SOURCE_WINDOW_OFFSET < FLASH_COMPILER_WORKSPACE_SIZE,
              "Flash compiler must leave a bounded source window");
static constexpr uint16_t SOURCE_WINDOW_BYTES =
    FLASH_COMPILER_WORKSPACE_SIZE-SOURCE_WINDOW_OFFSET;
}}
#endif
