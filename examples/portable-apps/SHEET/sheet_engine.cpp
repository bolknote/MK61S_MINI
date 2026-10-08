#include "sheet_engine.hpp"
// Only use the pure helpers from this header. Transcendentals are supplied
// by Host, so a freestanding APP must not include the hosted C++ libm header.
#ifndef MK61_MATH_BACKEND
#define MK61_MATH_BACKEND 1
#endif
#include "mk_math.hpp"
#include "number_format.hpp"
#include "mk8_codec.hpp"
#include <string.h>

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize ("Oz")
#endif

namespace sheet {
namespace {
constexpr double PI = 3.14159265358979323846;
ParseNumber parse_number;
FormatNumber format_number;
struct Word { const char* text; Op op; };
constexpr Word WORDS[] = {
  {"ENT",Op::ENTER},{"+",Op::ADD},{"-",Op::SUB},{"*",Op::MUL},{"/",Op::DIV},
  {"NEG",Op::NEG},{"SWAP",Op::SWAP},{"ROLL",Op::ROLL},
  {"SIN",Op::SIN},{"COS",Op::COS},{"TAN",Op::TAN},{"ASIN",Op::ASIN},
  {"ACOS",Op::ACOS},{"ATAN",Op::ATAN},{"LN",Op::LN},{"LG",Op::LG},
  {"EXP",Op::EXP},{"SQRT",Op::SQRT},{"POW",Op::POW},{"INV",Op::INV},
  {"SQR",Op::SQR},{"TEN",Op::TEN},{"ABS",Op::ABS},{"INT",Op::INT},
  {"FRAC",Op::FRAC},{"PI",Op::PI}
};
bool equal(const char* text, uint16_t length, const char* word) {
  uint16_t i = 0;
  while(i < length && word[i] && text[i] == word[i]) ++i;
  return i == length && word[i] == 0;
}
bool reference(const char* text, uint16_t length, uint16_t& position, uint8_t& anchor) {
  uint16_t at = 0; anchor = 0;
  if(at < length && text[at] == '$') { anchor |= 1; ++at; }
  if(at == length || text[at] < 'A' || text[at] >= 'A' + COLUMNS) return false;
  const uint8_t column = (uint8_t) (text[at++] - 'A');
  if(at < length && text[at] == '$') { anchor |= 2; ++at; }
  if(at == length || text[at] < '1' || text[at] > '9') return false;
  uint16_t row = 0;
  while(at < length && text[at] >= '0' && text[at] <= '9') {
    row = (uint16_t) (row * 10U + (uint8_t)(text[at++] - '0'));
    if(row > ROWS) return false;
  }
  if(at != length || row == 0) return false;
  position = (uint16_t) ((row - 1U) * COLUMNS + column); return true;
}
void affected(Book& book, uint16_t changed) {
  // A fixed point over at most MAX_CELLS vertices. Deletion uses the address,
  // not a sparse-array index, so dependants of a now-empty cell are updated.
  for(uint8_t pass = 0; pass < book.count; ++pass) {
    bool progress = false;
    for(uint8_t i = 0; i < book.count; ++i) {
      Cell& cell = book.cells[i];
      if(cell.dirty || (Kind)cell.kind != Kind::FORMULA) continue;
      uint16_t cursor = 0; Token token = {};
      while(cursor < cell.length) {
        if(next(book.pool + cell.offset, cell.length, cursor, token) != Error::OK) break;
        if(token.op != Op::REFERENCE) continue;
        const int dependency = find(book, token.position);
        if(token.position == changed || (dependency >= 0 && book.cells[dependency].dirty)) {
          cell.dirty = 1; progress = true; break;
        }
      }
    }
    if(!progress) break;
  }
}
void push(double (&s)[4], double x) { s[3]=s[2]; s[2]=s[1]; s[1]=s[0]; s[0]=x; }
void drop(double (&s)[4], double x) { s[0]=x; s[1]=s[2]; s[2]=s[3]; }
uint16_t get16(const uint8_t* p) { return (uint16_t)(p[0] | (uint16_t)p[1]<<8); }
void put16(uint8_t* p, uint16_t n) { p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8); }
uint32_t checksum(const uint8_t* data, uint16_t size) {
  uint32_t crc = 0xffffffffU;
  for(uint16_t i=0;i<size;++i) {
    if(i>=16 && i<20) continue;
    crc ^= data[i];
    for(uint8_t b=0;b<8;++b) crc=(crc>>1)^((crc&1U)?0xedb88320U:0);
  }
  return ~crc;
}
}

void clear(Book& book) { memset(&book,0,sizeof(book)); }
void number_io(ParseNumber parse, FormatNumber format) { parse_number=parse; format_number=format; }
int find(const Book& book, uint16_t position) {
  for(uint8_t i=0;i<book.count;++i) if(book.cells[i].position==position) return i;
  return -1;
}
bool source(const Book& book, uint16_t position, char* output) {
  const int index=find(book,position);
  output[0]=0;
  if(index<0) return false;
  const Cell& c=book.cells[index];
  memcpy(output,book.pool+c.offset,c.length); output[c.length]=0; return true;
}
bool number(const char* text, uint16_t length, double& value) {
  if(!text || length==0 || length>=SOURCE_BYTES) return false;
  uint16_t at=0;
  if(text[at]=='-' || text[at]=='+') ++at;
  bool digits=false, point=false;
  for(;at<length;++at) {
    const char c=text[at];
    if(c>='0' && c<='9') { digits=true; continue; }
    if(c=='.' && !point) { point=true; continue; }
    break;
  }
  if(!digits) return false;
  if(at<length && (text[at]=='E' || text[at]=='e')) {
    ++at; if(at<length && (text[at]=='-' || text[at]=='+')) ++at;
    const uint16_t start=at;
    while(at<length && text[at]>='0' && text[at]<='9') ++at;
    if(at==start) return false;
  }
  if(at!=length) return false;
  char copy[SOURCE_BYTES]; memcpy(copy,text,length); copy[length]=0;
  if(parse_number) { if(!parse_number(copy,value)) return false; }
#if __STDC_HOSTED__
  else value=mk_math::strtod(copy,nullptr);
#else
  else return false;
#endif
  return mk_math::is_finite(value);
}
Error next(const char* text, uint16_t length, uint16_t& cursor, Token& token) {
  while(cursor<length && text[cursor]==' ') ++cursor;
  token.begin=cursor;
  while(cursor<length && text[cursor]!=' ') ++cursor;
  token.end=cursor;
  const uint16_t size=(uint16_t)(cursor-token.begin);
  if(!size) return Error::SYNTAX;
  const char* word=text+token.begin;
  for(const Word& w:WORDS) if(equal(word,size,w.text)) { token.op=w.op; return Error::OK; }
  if(reference(word,size,token.position,token.anchor)) { token.op=Op::REFERENCE; return Error::OK; }
  if(number(word,size,token.number)) { token.op=Op::NUMBER; return Error::OK; }
  return word[0]=='#' ? Error::REFERENCE : Error::SYNTAX;
}
Error validate(Kind kind, const char* text, uint16_t length) {
  if(length>=SOURCE_BYTES || (length && !text)) return Error::LIMIT;
  if(kind==Kind::EMPTY) return length==0 ? Error::OK : Error::SYNTAX;
  if(!length) return Error::SYNTAX;
  if(kind==Kind::TEXT) {
    for(uint16_t i=0;i<length;++i)
      if(!mk8::valid_byte((uint8_t)text[i]) || text[i]=='\n' || text[i]=='\r' || text[i]=='\t') return Error::SYNTAX;
    return Error::OK;
  }
  if(kind==Kind::NUMBER) { double value; return number(text,length,value)?Error::OK:Error::NUMBER; }
  if(kind!=Kind::FORMULA) return Error::SYNTAX;
  uint16_t cursor=0; Token token={}; uint8_t count=0;
  while(cursor<length) {
    while(cursor<length && text[cursor]==' ') ++cursor;
    if(cursor==length) break;
    // Broken references are a valid formula token after a translated copy.
    const Error error=next(text,length,cursor,token);
    if(error!=Error::OK && !(error==Error::REFERENCE && equal(text+token.begin,token.end-token.begin,"#REF"))) return error;
    if(++count>48) return Error::LIMIT;
  }
  return count?Error::OK:Error::SYNTAX;
}
void address(uint16_t position, uint8_t anchor, char* out) {
  if(anchor&1) *out++='$';
  *out++=(char)('A'+position%COLUMNS);
  if(anchor&2) *out++='$';
  const uint8_t row=(uint8_t)(position/COLUMNS+1);
  if(row>=10) *out++=(char)('0'+row/10);
  *out++=(char)('0'+row%10); *out=0;
}
Error set(Book& book, uint16_t position, Kind kind, const char* text, uint16_t length) {
  if(position>=COLUMNS*ROWS) return Error::REFERENCE;
  const Error valid=validate(kind,text,length); if(valid!=Error::OK) return valid;
  int index=find(book,position);
  if(kind==Kind::EMPTY && index<0) return Error::OK;
  if(index<0 && book.count==MAX_CELLS) return Error::LIMIT;
  const uint16_t old_length=index>=0?book.cells[index].length:0;
  if((uint16_t)(book.used-old_length+length)>POOL_BYTES) return Error::LIMIT;
  char copy[SOURCE_BYTES]; if(length) memcpy(copy,text,length);
  if(index>=0) {
    const uint16_t old_offset=book.cells[index].offset;
    const uint16_t end=(uint16_t)(old_offset+old_length);
    memmove(book.pool+old_offset,book.pool+end,book.used-end);
    book.used=(uint16_t)(book.used-old_length);
    for(uint8_t i=0;i<book.count;++i) if(book.cells[i].offset>old_offset) book.cells[i].offset=(uint16_t)(book.cells[i].offset-old_length);
    if(kind==Kind::EMPTY) {
      memmove(&book.cells[index],&book.cells[index+1],(book.count-index-1)*sizeof(Cell));
      --book.count; affected(book,position); return Error::OK;
    }
  } else index=book.count++;
  Cell& cell=book.cells[index]; cell={}; cell.position=position;
  cell.offset=book.used; cell.length=(uint8_t)length; cell.kind=(uint8_t)kind; cell.dirty=1;
  memcpy(book.pool+book.used,copy,length); book.used=(uint16_t)(book.used+length);
  affected(book,position); return Error::OK;
}
void invalidate(Book& book) { for(uint8_t i=0;i<book.count;++i) book.cells[i].dirty=1; }
Error evaluate(const Book& book, const char* text, uint16_t length, const Host& host, double& value) {
  double s[4]={}; bool lift=true;
  uint16_t cursor=0; uint8_t count=0; Token t={};
  while(cursor<length) {
    while(cursor<length && text[cursor]==' ') ++cursor;
    if(cursor==length) break;
    const Error error=next(text,length,cursor,t); if(error!=Error::OK) return error;
    if(++count>48) return Error::LIMIT;
    if(host.yield && !host.yield(host.context)) return Error::CANCELLED;
    if(t.op==Op::NUMBER || t.op==Op::REFERENCE || t.op==Op::PI) {
      double x=t.op==Op::PI?PI:t.number;
      if(t.op==Op::REFERENCE) {
        const int dependency=find(book,t.position); x=0;
        if(dependency>=0) {
          const Cell& cell=book.cells[dependency];
          if((Kind)cell.kind==Kind::TEXT) return Error::TYPE;
          if(cell.dirty) return Error::CYCLE; // A draft can refer to an unfinished recalculation.
          if(cell.error) return (Error)cell.error;
          x=cell.value;
        }
      }
      if(lift) push(s,x); else s[0]=x;
      lift=false; continue;
    }
    double x=s[0], y=s[1], result=x;
    switch(t.op) {
      case Op::ENTER: push(s,x); lift=false; continue;
      case Op::SWAP: s[0]=y; s[1]=x; lift=true; continue;
      case Op::ROLL: s[0]=s[1]; s[1]=s[2]; s[2]=s[3]; s[3]=x; lift=true; continue;
      case Op::ADD: result=y+x; break;
      case Op::SUB: result=y-x; break;
      case Op::MUL: result=y*x; break;
      case Op::DIV: if(x==0) return Error::NUMBER; result=y/x; break;
      // MK-61 labels this key x^y: X is the base, Y is the exponent.
      case Op::POW: if(!host.math) return Error::NUMBER; result=host.math(host.context,t.op,x,y); break;
      case Op::NEG: result=-x; break;
      case Op::INV: if(x==0) return Error::NUMBER; result=1/x; break;
      case Op::SQR: result=x*x; break;
      case Op::ABS: result=mk_math::fabs(x); break;
      case Op::INT: result=mk_math::trunc(x); break;
      case Op::FRAC: result=x-mk_math::trunc(x); break;
      default: {
        if(!host.math) return Error::NUMBER;
        const double factor=(Angle)book.angle==Angle::DEG?PI/180:((Angle)book.angle==Angle::GRD?PI/200:1);
        if(t.op==Op::SIN || t.op==Op::COS || t.op==Op::TAN) x*=factor;
        if((t.op==Op::LN || t.op==Op::LG) && x<=0) return Error::NUMBER;
        if(t.op==Op::SQRT && x<0) return Error::NUMBER;
        if((t.op==Op::ASIN || t.op==Op::ACOS) && (x < -1 || x > 1)) return Error::NUMBER;
        result=host.math(host.context,t.op,x,0);
        if(t.op==Op::ASIN || t.op==Op::ACOS || t.op==Op::ATAN) result/=factor;
        break;
      }
    }
    if(!mk_math::is_finite(result)) return Error::NUMBER;
    if(t.op==Op::ADD || t.op==Op::SUB || t.op==Op::MUL || t.op==Op::DIV || t.op==Op::POW) drop(s,result);
    else s[0]=result;
    lift=true;
  }
  value=s[0]; return count?Error::OK:Error::SYNTAX;
}
bool recalculate(Book& book, const Host& host) {
  struct Frame { uint16_t cursor; uint8_t index; };
  Frame frames[MAX_CELLS]; uint8_t color[MAX_CELLS]={};
  uint32_t budget=(uint32_t)MAX_CELLS*(SOURCE_BYTES+2U)*3U;
  for(uint8_t root=0;root<book.count;++root) {
    if(!book.cells[root].dirty || color[root]==2) continue;
    uint8_t depth=1; frames[0]={0,root}; color[root]=1; book.cells[root].error=0;
    while(depth) {
      if(!budget-- || (host.yield && !host.yield(host.context))) return false;
      Frame& frame=frames[depth-1]; Cell& cell=book.cells[frame.index];
      bool descended=false;
      if((Kind)cell.kind==Kind::FORMULA) {
        while(frame.cursor<cell.length) {
          Token token={};
          if(next(book.pool+cell.offset,cell.length,frame.cursor,token)!=Error::OK) continue;
          if(token.op!=Op::REFERENCE) continue;
          const int child=find(book,token.position);
          if(child<0 || !book.cells[child].dirty || color[child]==2) continue;
          if(color[child]==1) {
            bool cycle=false;
            for(uint8_t d=0;d<depth;++d) {
              if(frames[d].index==child) cycle=true;
              if(cycle) book.cells[frames[d].index].error=(uint8_t)Error::CYCLE;
            }
          } else {
            if(depth==MAX_CELLS) return false;
            frames[depth++]={0,(uint8_t)child}; color[child]=1; book.cells[child].error=0;
            descended=true; break;
          }
        }
      }
      if(descended) continue;
      double value=0;
      Error error=(Error)cell.error;
      if(error==Error::OK) {
        if((Kind)cell.kind==Kind::NUMBER)
          error=number(book.pool+cell.offset,cell.length,value)?Error::OK:Error::NUMBER;
        else if((Kind)cell.kind==Kind::FORMULA)
          error=evaluate(book,book.pool+cell.offset,cell.length,host,value);
      }
      if(error==Error::CANCELLED) return false;
      cell.value=value; cell.error=(uint8_t)error; cell.dirty=0;
      color[frame.index]=2; --depth;
    }
  }
  return true;
}
Error translate(const char* input, uint16_t length, int columns, int rows, char* output) {
  uint16_t cursor=0, used=0; Token token={};
  while(cursor<length) {
    while(cursor<length && input[cursor]==' ') ++cursor;
    if(cursor==length) break;
    const Error error=next(input,length,cursor,token);
    if(error!=Error::OK && error!=Error::REFERENCE) return error;
    char address_text[8]; const char* text=input+token.begin;
    uint16_t size=(uint16_t)(token.end-token.begin);
    if(error==Error::OK && token.op==Op::REFERENCE) {
      const int c=(int)(token.position%COLUMNS)+((token.anchor&1)?0:columns);
      const int r=(int)(token.position/COLUMNS)+((token.anchor&2)?0:rows);
      if(c<0 || c>=COLUMNS || r<0 || r>=ROWS) { text="#REF"; size=4; }
      else { address((uint16_t)(r*COLUMNS+c),token.anchor,address_text); text=address_text; size=(uint16_t)strlen(text); }
    }
    if(used) { if(used+1>=SOURCE_BYTES) return Error::LIMIT; output[used++]=' '; }
    if(used+size>=SOURCE_BYTES) return Error::LIMIT;
    memcpy(output+used,text,size); used=(uint16_t)(used+size);
  }
  output[used]=0; return Error::OK;
}
uint16_t encode(const Book& book, uint8_t* output, uint16_t capacity) {
  const uint16_t total=(uint16_t)(20U+4U*book.count+book.used);
  if(!output || capacity<total || book.count>MAX_CELLS || book.used>POOL_BYTES) return 0;
  memset(output,0,20); memcpy(output,"MKSH",4);
  output[4]=1; output[5]=COLUMNS; output[6]=ROWS; output[7]=book.angle;
  output[8]=book.compact; output[9]=book.count; put16(output+12,(uint16_t)(total-20));
  uint16_t at=20;
  for(uint8_t i=0;i<book.count;++i) {
    const Cell& cell=book.cells[i]; put16(output+at,cell.position);
    output[at+2]=cell.kind; output[at+3]=cell.length; at+=4;
    memcpy(output+at,book.pool+cell.offset,cell.length); at=(uint16_t)(at+cell.length);
  }
  const uint32_t crc=checksum(output,total);
  for(uint8_t b=0;b<4;++b) output[16+b]=(uint8_t)(crc>>(8*b));
  return total;
}
bool decode(Book& book, const uint8_t* data, uint16_t length) {
  if(!data || length<20 || length>FILE_BYTES || memcmp(data,"MKSH",4) || data[4]!=1 ||
     data[5]!=COLUMNS || data[6]!=ROWS || data[7]>(uint8_t)Angle::GRD || data[8]>1 ||
     data[9]>MAX_CELLS || get16(data+10) || get16(data+14) || get16(data+12)!=length-20) return false;
  uint32_t crc=0; for(uint8_t b=0;b<4;++b) crc|=(uint32_t)data[16+b]<<(8*b);
  if(crc!=checksum(data,length)) return false;
  uint8_t seen[COLUMNS*ROWS/8]={}; uint16_t at=20, used=0;
  for(uint8_t i=0;i<data[9];++i) {
    if(length-at<4) return false;
    const uint16_t position=get16(data+at); const uint8_t kind=data[at+2], size=data[at+3]; at+=4;
    if(position>=COLUMNS*ROWS || kind==0 || kind>(uint8_t)Kind::FORMULA || size>length-at ||
       (seen[position/8] & (1U<<(position%8))) || (uint16_t)(used+size)>POOL_BYTES ||
       validate((Kind)kind,(const char*)data+at,size)!=Error::OK) return false;
    seen[position/8]|=(uint8_t)(1U<<(position%8)); used=(uint16_t)(used+size); at=(uint16_t)(at+size);
  }
  if(at!=length) return false;
  clear(book); book.angle=data[7]; book.compact=data[8]; book.count=data[9]; at=20;
  for(uint8_t i=0;i<book.count;++i) {
    Cell& cell=book.cells[i]; cell.position=get16(data+at); cell.kind=data[at+2]; cell.length=data[at+3]; at+=4;
    cell.offset=book.used; cell.dirty=1;
    memcpy(book.pool+book.used,data+at,cell.length);
    book.used=(uint16_t)(book.used+cell.length); at=(uint16_t)(at+cell.length);
  }
  return true;
}
void format(double value, char* output, uint16_t capacity, uint8_t digits) {
  if(format_number) { if(!format_number(value,output,capacity,digits) && capacity) output[0]=0; return; }
#if __STDC_HOSTED__
  if(!number_format::general(value,digits,output,capacity) && capacity) output[0]=0;
#else
  (void)value; (void)digits; if(capacity) output[0]=0;
#endif
}
const char* error_text(Error error) {
  switch(error) {
    case Error::OK: return ""; case Error::SYNTAX: return "#FORM";
    case Error::REFERENCE: return "#REF"; case Error::TYPE: return "#TYPE";
    case Error::NUMBER: return "#NUM"; case Error::CYCLE: return "#CYCLE";
    case Error::LIMIT: return "#LIMIT"; case Error::CANCELLED: return "...";
  }
  return "#ERR";
}
const char* op_text(Op op) {
  for(const Word& word:WORDS) if(word.op==op) return word.text;
  return "";
}
}
