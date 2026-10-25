#ifndef MK61_LANGUAGE_SOURCE_DOCUMENT_HPP
#define MK61_LANGUAGE_SOURCE_DOCUMENT_HPP
#include "language_source.hpp"
#include "text_editor.hpp"

namespace language_vm { namespace source {
// Two private banks in the existing power-safe staging journal. No inode or
// directory entry is published until the user saves. Each page keeps its old
// bank until the new page map commits; cancellation only forgets these keys.
static constexpr unsigned DRAFT_PAGE_SIZE = 512;
static constexpr unsigned DRAFT_PAGES = (MAX_SIZE+DRAFT_PAGE_SIZE-1)/DRAFT_PAGE_SIZE;
static constexpr uint32_t DRAFT_FIRST_KEY = 0x007FF000U;
struct DraftIO {
  void* context;
  bool (*begin)(void*,uint32_t* index,uint16_t capacity);
  bool (*read)(void*,uint32_t key,uint8_t*);
  bool (*write)(void*,uint32_t key,const uint8_t*);
  bool (*forget)(void*,uint32_t key,uint16_t pages);
  void (*end)(void*);
};
class Document {
public:
  static constexpr unsigned WINDOW_SIZE = 1024;
  char window[WINDOW_SIZE+1];
private:
  DraftIO io_;
  Input initial_;
  uint32_t index_[DRAFT_PAGES*2];
  uint8_t page_[DRAFT_PAGE_SIZE];
  uint16_t base_size_,start_=0,old_=0,used_=0,load_;
  uint32_t hash_=0,generation_=0;
  uint8_t banks_[(DRAFT_PAGES+7)/8]={};
  bool open_=false,staged_=false,dirty_=false;
  static uint32_t hash(const char* text,unsigned n) {
    uint32_t value=2166136261U;
    while(n--)value=(value^uint8_t(*text++))*16777619U;
    return value;
  }
  static bool word(char ch) {return (ch>='A' && ch<='Z') || (ch>='a' && ch<='z') || ch=='.';}
  bool base(uint16_t offset,uint8_t* output,uint16_t n) {
    if(!staged_) {
      while(n) {
        const uint16_t count=n>PAGE_SIZE?PAGE_SIZE:n;
        if(!initial_.read(initial_.context,offset,output,count))return false;
        offset=uint16_t(offset+count);output+=count;n=uint16_t(n-count);
      }
      return true;
    }
    while(n) {
      const unsigned page=offset/DRAFT_PAGE_SIZE,in=offset%DRAFT_PAGE_SIZE;
      const unsigned bank=(banks_[page/8]>>(page%8))&1U;
      if(!io_.read(io_.context,DRAFT_FIRST_KEY+bank*DRAFT_PAGES+page,page_))return false;
      unsigned count=DRAFT_PAGE_SIZE-in;if(count>n)count=n;
      memcpy(output,page_+in,count);output+=count;offset=uint16_t(offset+count);n=uint16_t(n-count);
    }
    return true;
  }
public:
  Document(Input initial,DraftIO io,unsigned load=WINDOW_SIZE*3/4):io_(io),initial_(initial),base_size_(initial.size),load_(uint16_t(load)) {}
  ~Document() {
    if(open_) {
      (void)io_.forget(io_.context,DRAFT_FIRST_KEY,DRAFT_PAGES*2);
      io_.end(io_.context);
    }
  }
  bool open() {
    if(open_ || base_size_>MAX_SIZE || (!initial_.read && base_size_))return false;
    open_=io_.begin(io_.context,index_,DRAFT_PAGES*2);
    return open_;
  }
  uint16_t size() const {return uint16_t(unsigned(base_size_)-old_+used_);}
  uint16_t start() const {return start_;}
  uint16_t used() const {return used_;}
  uint32_t generation() const {return generation_;}
  static bool read(void* raw,uint16_t offset,uint8_t* output,uint16_t n) {
    return static_cast<Document*>(raw)->read(offset,output,n);
  }
  Input input() {return {this,read,size()};}
  bool read(uint16_t offset,uint8_t* output,uint16_t n) {
    if(!open_ || offset>size() || n>unsigned(size()-offset))return false;
    while(n) {
      unsigned count;
      if(offset<start_) {
        count=start_-offset;if(count>n)count=n;
        if(!base(offset,output,uint16_t(count)))return false;
      } else if(offset<unsigned(start_)+used_) {
        count=start_+used_-offset;if(count>n)count=n;
        memcpy(output,window+(offset-start_),count);
      } else {
        count=n;
        if(!base(uint16_t(unsigned(offset)-used_+old_),output,uint16_t(count)))return false;
      }
      output+=count;offset=uint16_t(offset+count);n=uint16_t(n-count);
    }
    return true;
  }
  bool fits(uint16_t length) const {return length<=WINDOW_SIZE && unsigned(base_size_)-old_+length<=MAX_SIZE;}
  bool accept(uint16_t length) {
    if(!fits(length))return false;
    used_=length;
    dirty_=dirty_ || hash(window,used_)!=hash_;
    return true;
  }
  bool flush() {
    if(!dirty_)return true;
    const unsigned length=size(),old_pages=(base_size_+DRAFT_PAGE_SIZE-1)/DRAFT_PAGE_SIZE;
    const unsigned pages=(length+DRAFT_PAGE_SIZE-1)/DRAFT_PAGE_SIZE;
    uint8_t next[sizeof(banks_)];memcpy(next,banks_,sizeof(next));
    // read() also needs page_ for the old bank: the output page must be
    // separate so a cross-page read cannot overwrite its own prefix.
    uint8_t output[DRAFT_PAGE_SIZE];
    for(unsigned at=0;at<length;at+=DRAFT_PAGE_SIZE) {
      unsigned n=length-at;if(n>DRAFT_PAGE_SIZE)n=DRAFT_PAGE_SIZE;
      memset(output,0,sizeof(output));
      if(!read(uint16_t(at),output,uint16_t(n)))return false;
      const unsigned page=at/DRAFT_PAGE_SIZE,mask=1U<<(page%8);
      const unsigned previous=(banks_[page/8]>>(page%8))&1U;
      const bool exists=staged_ && page<old_pages;
      if(exists) {
        if(!io_.read(io_.context,DRAFT_FIRST_KEY+previous*DRAFT_PAGES+page,page_))return false;
        // Keep unchanged pages in their current bank. Editing a tail must
        // not require a second full-file snapshot on a small NOR volume.
        if(!memcmp(output,page_,sizeof(output)))continue;
      }
      const unsigned bank=exists?previous^1U:0;
      const uint32_t key=DRAFT_FIRST_KEY+bank*DRAFT_PAGES+page;
      if(!io_.forget(io_.context,key,1) || !io_.write(io_.context,key,output))return false;
      next[page/8]=uint8_t((next[page/8]&~mask)|(bank?mask:0));
    }
    // Publish the page map only after every changed page is durable. A failed
    // write leaves the old map and the current RAM edit readable for retry.
    uint8_t previous[sizeof(banks_)];memcpy(previous,banks_,sizeof(previous));
    const bool had_bank=staged_;
    memcpy(banks_,next,sizeof(banks_));staged_=true;base_size_=uint16_t(length);old_=used_;
    hash_=hash(window,used_);dirty_=false;
    if(had_bank)for(unsigned page=0;page<old_pages;++page) {
      const unsigned bank=(previous[page/8]>>(page%8))&1U;
      if(page>=pages || bank!=unsigned((banks_[page/8]>>(page%8))&1U))
        if(!io_.forget(io_.context,DRAFT_FIRST_KEY+bank*DRAFT_PAGES+page,1))return false;
    }
    return true;
  }
  bool seek(text_editor::Buffer& editor,uint16_t absolute) {
    if(absolute>size())absolute=size();
    if(!flush())return false;
    unsigned begin=absolute>load_/3?absolute-load_/3:0;
    // Prefer physical line boundaries, preserving operator-key context and
    // the ordinary full-screen editor for all lines shorter than a window.
    const unsigned lookback=begin<load_/3?begin:load_/3;
    if(lookback && !base(uint16_t(begin-lookback),reinterpret_cast<uint8_t*>(window),uint16_t(lookback)))return false;
    unsigned boundary=lookback;
    while(boundary && window[boundary-1]!='\n' && window[boundary-1]!='\r')--boundary;
    if(boundary || begin==lookback)begin=begin-lookback+boundary;
    else {
      // Keep short operator names whole when a physical line spans windows.
      boundary=lookback;
      while(boundary && lookback-boundary<16 && word(window[boundary-1]))--boundary;
      if(boundary && !word(window[boundary-1]))begin=begin-lookback+boundary;
    }
    unsigned n=base_size_-begin;
    if(n>load_)n=load_;
    if(absolute>begin+n)begin=absolute-load_/3;
    const unsigned available=base_size_-begin;
    n=available;if(n>load_)n=load_;
    unsigned read=n+16;if(read>available)read=available;if(read>WINDOW_SIZE)read=WINDOW_SIZE;
    if(read && !base(uint16_t(begin),reinterpret_cast<uint8_t*>(window),uint16_t(read)))return false;
    unsigned finish=n;
    while(finish && finish<read && word(window[finish-1]) && word(window[finish]))++finish;
    if(finish<read || read==available)n=finish;
    ++generation_;
    window[n]=0;start_=uint16_t(begin);old_=used_=uint16_t(n);hash_=hash(window,n);
    const auto shift=editor.shift;
    text_editor::init(editor,window,sizeof(window));
    editor.shift=shift;editor.cursor=uint16_t(absolute-begin);
    return true;
  }
  bool prepare(text_editor::Buffer& editor) {
    if(!accept(editor.len))return false;
    const unsigned cursor=start_+editor.cursor;
    const unsigned margin=load_/4<128?load_/4:128;
    if((editor.cursor<64 && start_) ||
       (editor.cursor+margin>used_ && unsigned(start_)+used_<size()) ||
       used_+64U>WINDOW_SIZE) return seek(editor,uint16_t(cursor));
    // The shared keyboard editor cannot insert beyond the wire-format limit.
    const unsigned remaining=MAX_SIZE-size();
    editor.capacity=uint16_t(remaining<WINDOW_SIZE-used_?used_+remaining+1:WINDOW_SIZE+1);
    return true;
  }
  bool erase(uint16_t begin,uint16_t end,text_editor::Buffer& editor) {
    if(begin>end || end>size() || !flush())return false;
    start_=begin;old_=uint16_t(end-begin);used_=0;window[0]=0;dirty_=true;
    return seek(editor,begin);
  }
};
}}
#endif
