#ifndef MK61_LANGUAGE_FLASH_PROGRAM_HPP
#define MK61_LANGUAGE_FLASH_PROGRAM_HPP
#include "language_bytecode.hpp"
#include "focal_syntax.hpp"
#include "language_integer_spans.hpp"

namespace language_vm { namespace flash {
static constexpr uint8_t VERSION=14;
static constexpr uint32_t HEADER_BYTES=32, MAP_BYTES=8, NO_ADDRESS=UINT32_MAX;
class Program {
  IO io_;
  source::Reader const& source_;
  LineIndex index_;
  Writer writer_;
  Error error_=Error::NONE;
  bool writing_=false;
  uint32_t source_crc_=0,code_end_=0;
public:
  Program(const source::Reader& source,IO io):io_(io),source_(source),index_(io,INDEX_A),writer_(io,INDEX_A) {}
  Error error() const {return error_;}
  void fail(Error e=Error::IO) {if(error_==Error::NONE)error_=e;}
  uint16_t count() const {return index_.size();}
  uint32_t code() const {return HEADER_BYTES+uint32_t(count())*MAP_BYTES;}
  uint32_t size() const {return writer_.size();}
  bool writing() const {return writing_;}
  bool prepare(Language language) {
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(MK61_LANGUAGE_VM_COMPILER)
    // Source indexing/sorting is shared resident code on the small device.
    // The host fallback executes exactly the same bounded implementation.
    return io_.prepare && io_.prepare(io_.context,this,uint8_t(language));
#else
    return io_.prepare?io_.prepare(io_.context,this,uint8_t(language)):prepare_index(language);
#endif
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
    }
    if(!count()) {fail(Error::LINE);return false;}
    if(!writer_.flush() || !index_.sort(ordered,writer_)) {fail();return false;}
    if(!writer_.reset(index_.space(),uint32_t(count())*LINE_BYTES)){fail();return false;}
    uint32_t last=0;
    for(uint16_t i=0;i<count();++i) {
      const auto record=line(i);if(error_!=Error::NONE)return false;
      if(record.number<=last) {fail(Error::LINE);return false;}last=record.number;
    }
    source_crc_=source_.checksum();
    if(!source_.good()) {fail();return false;}
    return true;
  }
  Line line(uint16_t n) {
    uint8_t bytes[LINE_BYTES];
    const bool read=n<count() && (writing_
        ? io_.read(io_.context,index_.space(),uint32_t(n)*LINE_BYTES,bytes,sizeof(bytes))
        : writer_.read(uint32_t(n)*LINE_BYTES,bytes,sizeof(bytes)));
    if(!read) {fail();return {};}
    return LineIndex::decode(bytes);
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
    if(!writer_.reset(IMAGE)) {fail();return false;}
    writing_=true;
    uint8_t header[HEADER_BYTES]={};
    if(!writer_.write(0,header,sizeof(header))) {fail();return false;}
    for(uint16_t i=0;i<count();++i) {
      const auto record=line(i);uint8_t bytes[MAP_BYTES];
      dword(bytes,record.number);dword(bytes+4,record.pc);
      if(!writer_.write(HEADER_BYTES+uint32_t(i)*MAP_BYTES,bytes,sizeof(bytes))) {fail();return false;}
    }
    return error_==Error::NONE;
  }
  void byte(uint32_t at,uint8_t b) {if(!writer_.byte(at,b))fail();}
  void address(uint32_t at,uint32_t value) {uint8_t bytes[4];dword(bytes,value);if(!writer_.write(at,bytes,sizeof(bytes)))fail();}
  bool optimize() {
    Reader reader({this,[](void* raw,uint32_t at,uint8_t* out,uint16_t n){return static_cast<Program*>(raw)->writer_.read(at,out,n);},code_end_});
    View view={nullptr,code_end_,code(),count(),source_.size(),1,Language::BASIC,false,false,code_end_,&reader,true};
    detail::integer_spans(code(),code_end_,[&](uint32_t pc){return view.byte(pc);},
        [&](uint32_t pc){return reader.good()?instruction_end(view,pc):0;},
        [&](uint32_t pc,Op op){byte(pc,uint8_t(op));reader.invalidate();});
    return reader.good() && writer_.good();
  }
  bool finish(Language language,uint32_t size,uint8_t stack,bool rf) {
    code_end_=size;
#if defined(MK61_BUILD_PORTABLE_SYSTEM) && defined(MK61_LANGUAGE_VM_COMPILER)
    const bool optimized=io_.prepare && io_.prepare(io_.context,this,0x80);
#else
    const bool optimized=io_.prepare?io_.prepare(io_.context,this,0x80):optimize();
#endif
    if(!optimized){fail();return false;}
    uint32_t crc=~uint32_t(0);uint8_t bytes[64];
    for(uint32_t at=HEADER_BYTES;at<size;) {
      const uint16_t n=uint16_t(size-at<sizeof(bytes)?size-at:sizeof(bytes));
      if(!writer_.read(at,bytes,n)) {fail();return false;}
      for(unsigned i=0;i<n;++i) {crc^=bytes[i];for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xEDB88320U&(0U-(crc&1U)));}
      at+=n;
      if(!io_.poll()) {fail(Error::STOPPED);return false;}
    }
    uint8_t header[HEADER_BYTES]={};memcpy(header,"LBV2",4);
    header[4]=VERSION;header[5]=uint8_t(language);header[6]=stack?stack:1;header[7]=rf?2:0;
    dword(header+8,size);dword(header+12,code());word(header+16,source_.size());word(header+18,count());
    dword(header+20,source_crc_);dword(header+24,~crc);dword(header+28,size);
    if(!writer_.write(0,header,sizeof(header)) || !writer_.flush())fail();
    return error_==Error::NONE;
  }
};
}}
#endif
