#ifndef MK61_FOCAL_SOURCE_HPP
#define MK61_FOCAL_SOURCE_HPP
#include "language_source.hpp"
#include "focal_text.hpp"
namespace focal_text {
// Sequential compact spelling over an arbitrary source. A rewind restarts
// lexical scanning; storage can run size/CRC/write passes without a copy.
class CompactSource {
  using Cursor=language_vm::source::Cursor;
  const language_vm::source::Reader& source_;
  language_vm::source::CursorScope scope_;
  Cursor scan_,line_end_;
  unsigned at_=0,output_=0,size_=0,begin_=0,end_=0,replacement_at_=0;
  const char* replacement_=nullptr;
  char short_name_[2]{};
  bool have_=false,line_=false,comment_=false;
  void reset() {
    scan_=Cursor(source_);line_end_=scan_;at_=output_=begin_=end_=replacement_at_=0;
    replacement_=nullptr;have_=line_=comment_=false;
  }
  bool token() {
    const Cursor finish=Cursor(source_)+source_.size();
    while(scan_<finish) {
      if(!line_) {
        while(scan_<finish && (*scan_=='\r'||*scan_=='\n'))++scan_;
        line_end_=scan_+scan_.line_end(finish);
        auto p=scan_;focal_next::Address address;
        if(!focal_next::address(p,line_end_,address) || !address.exact) {scan_=line_end_;continue;}
        scan_=p;line_=true;comment_=false;
      } else if(comment_) {scan_=line_end_;line_=false;continue;}
      scan_=focal_next::skip(scan_,line_end_);
      const Cursor first=scan_;
      const auto command=focal_next::command(scan_,line_end_);
      if(command==focal_next::Command::NONE) {scan_=line_end_;line_=false;continue;}
      begin_=unsigned(first-Cursor(source_));end_=unsigned(scan_-Cursor(source_));
      replacement_=spelling(command,false,short_name_);replacement_at_=0;
      if(command==focal_next::Command::COMMENT)comment_=true;
      else {
        scan_=focal_next::delimiter(scan_,line_end_,';');
        if(scan_<line_end_)++scan_;else line_=false;
      }
      return have_=true;
    }
    begin_=end_=source_.size();replacement_=nullptr;
    return have_=false;
  }
  bool next(uint8_t& value) {
    if(!have_)token();
    if(at_<begin_) {value=uint8_t(source_.at(uint16_t(at_++)));return true;}
    if(have_) {
      if(replacement_[replacement_at_]) {value=uint8_t(replacement_[replacement_at_++]);return true;}
      at_=end_;have_=false;
      return next(value);
    }
    if(at_<source_.size()) {value=uint8_t(source_.at(uint16_t(at_++)));return true;}
    return false;
  }
public:
  explicit CompactSource(const language_vm::source::Reader& source):source_(source),scope_(source),scan_(source),line_end_(source) {
    size_=source.size();
    while(token()) {size_=size_-(end_-begin_)+strlen(replacement_);have_=false;}
    reset();
  }
  unsigned size() const {return size_;}
  bool good() const {return source_.good() && size_<=language_vm::source::MAX_SIZE;}
  static bool read(void* raw,uint16_t offset,uint8_t* out,uint16_t n) {
    auto& s=*static_cast<CompactSource*>(raw);
    if(!s.good() || offset>s.size_ || n>s.size_-offset)return false;
    if(offset<s.output_)s.reset();
    uint8_t value;
    while(s.output_<offset) {if(!s.next(value))return false;++s.output_;}
    while(n--) {if(!s.next(*out++))return false;++s.output_;}
    return s.good();
  }
  language_vm::source::Input input() {return {this,read,uint16_t(size_)};}
};
}
#endif
