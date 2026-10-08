#include "mk61_app.h"
#include "sheet_engine.hpp"
#include "mk8_literal.hpp"
#include <string.h>

#if defined(__GNUC__) && !defined(__clang__)
// The complete UI and document share a 20-KiB APP allocation.
#pragma GCC optimize ("Oz")
#endif

namespace {
using sheet::Kind; using sheet::Error; using sheet::Op;
enum class Mode : uint8_t { TABLE, EDIT, REFERENCE, ACTIONS, SHEET, TYPE, COPY, FILL, CONFIRM, HELP, DETAILS, FUNCTIONS };
enum class Pending : uint8_t { NONE, EXIT, NEW, OPEN };
struct App {
  sheet::Book book;
  uint8_t archive[20U+4U*sheet::MAX_CELLS+sheet::POOL_BYTES];
  uint8_t* frame;
  mk61_service_lease frame_lease;
  const mk61_app_api* api;
  const mk61_app_services* services;
  mk61_service_edit_key text_editor;
  char edit[sheet::SOURCE_BYTES], copied[sheet::SOURCE_BYTES], file_name[32];
  uint32_t file_id, parent, revision;
  uint16_t selected, top_row, left_column, edit_length, cursor, undo_size, origin;
  uint8_t reference_anchor, prefix, menu, page, copied_kind;
  Kind edit_kind;
  Mode mode;
  Pending pending;
  bool graphics, modified, undo_modified, exit, redraw, io_error;
  Error message;
  Error preview_error;
  double preview_value;
};
App app;

bool parse_number(const char* text,double& value) {
  mk61_service_number_parse request={0,text,0};
  if(!app.services->call(MK61_SERVICE_NUMBER_PARSE,0,0,0,&request) || request.consumed!=strlen(text)) return false;
  value=request.value; return true;
}
bool format_number(double value,char* output,uint16_t capacity,uint8_t digits) {
  mk61_service_number_format request={value,output,capacity,digits};
  return app.services->call(MK61_SERVICE_NUMBER_FORMAT,0,0,0,&request)!=0;
}

const char* error_label(Error error) {
  switch(error) {
    case Error::OK:return ""; case Error::SYNTAX:return M8("#ФОРМ");
    case Error::REFERENCE:return M8("#ССЫЛ"); case Error::TYPE:return M8("#ТИП");
    case Error::NUMBER:return M8("#ЧИСЛО"); case Error::CYCLE:return M8("#ЦИКЛ");
    case Error::LIMIT:return M8("#ЛИМИТ"); case Error::CANCELLED:return "...";
  }
  return "#ERR";
}
void copy_text(char* out, const char* in, size_t capacity) {
  size_t i=0; while(i+1<capacity && in[i]) { out[i]=in[i]; ++i; } out[i]=0;
}
uint16_t length(const char* text) { return (uint16_t)strlen(text); }
void close_graphics() { if(app.graphics) { app.api->graphics_end(); app.graphics=false; } }
bool open_graphics() {
  if(app.graphics) return true;
  if(!app.api->graphics_available() || app.api->graphics_width()!=192 ||
     app.api->graphics_height()!=64 || !app.api->graphics_begin()) return false;
  app.graphics=true; app.revision=app.api->graphics_revision(); return true;
}
void pixel(int x,int y,bool ink=true) {
  if(x<0 || x>=192 || y<0 || y>=64) return;
  uint8_t& byte=app.frame[(y/8)*192+x]; const uint8_t bit=(uint8_t)(1U<<(y%8));
  if(ink) byte|=bit; else byte&=(uint8_t)~bit;
}
void rectangle(int x,int y,int w,int h,bool fill=true) {
  for(int row=0;row<h;++row) for(int col=0;col<w;++col)
    if(fill || row==0 || row==h-1 || col==0 || col==w-1) pixel(x+col,y+row);
}
int advance(bool compact=false) { return compact?4:6; }
void text(int x,int y,const char* value,bool inverse=false,bool compact=false,int maximum=192) {
  const int step=advance(compact);
  for(;*value && x+step<=maximum; ++value,x+=step) {
    mk61_service_glyph glyph={};
    if(!app.services->call(MK61_SERVICE_FONT,compact?1U:0U,mk8::codepoint((uint8_t)*value),sizeof(glyph),&glyph) ||
       glyph.width>8 || glyph.height>8) continue;
    for(uint32_t gy=0;gy<glyph.height;++gy) for(uint32_t gx=0;gx<glyph.width;++gx)
      if(glyph.pixels[gy] & (uint8_t)(0x80U>>gx)) pixel(x+(int)gx,y+(int)gy,!inverse);
  }
}
void band(int y,const char* value) { rectangle(0,y,192,8); text(2,y,value,true); }
const char* angle_label() { return app.book.angle==0?"DEG":(app.book.angle==1?"RAD":"GRD"); }
const char* op_label(Op op) {
  switch(op) {
    case Op::ENTER:return M8("В↑"); case Op::MUL:return M8("×");
    case Op::DIV:return M8("÷"); case Op::SQRT:return M8("√");
    case Op::PI:return M8("π"); case Op::SQR:return M8("x²");
    case Op::INV:return "1/x"; case Op::POW:return "x^y";
    default:return sheet::op_text(op);
  }
}
void formula_text(const char* source,uint16_t size,char* out,uint16_t capacity) {
  uint16_t cursor=0, used=0; sheet::Token token={};
  while(cursor<size) {
    while(cursor<size && source[cursor]==' ') ++cursor;
    if(cursor==size) break;
    const Error error=sheet::next(source,size,cursor,token);
    const bool literal=error!=Error::OK || token.op==Op::NUMBER || token.op==Op::REFERENCE;
    const char* word=literal?source+token.begin:op_label(token.op);
    uint16_t count=literal?(uint16_t)(token.end-token.begin):length(word);
    if(used && used+1<capacity) out[used++]=' ';
    for(uint16_t i=0;i<count && used+1<capacity;++i) out[used++]=word[i];
    if(used+1>=capacity) break;
  }
  out[used]=0;
}
void visible() {
  const uint16_t rows=app.book.compact?7:5, columns=app.book.compact?4:3;
  const uint16_t row=app.selected/sheet::COLUMNS, col=app.selected%sheet::COLUMNS;
  if(row<app.top_row) app.top_row=row;
  if(row>=app.top_row+rows) app.top_row=(uint16_t)(row-rows+1);
  if(col<app.left_column) app.left_column=col;
  if(col>=app.left_column+columns) app.left_column=(uint16_t)(col-columns+1);
}
void value_text(uint16_t position,char* output,uint16_t capacity) {
  output[0]=0; const int index=sheet::find(app.book,position); if(index<0) return;
  const sheet::Cell& cell=app.book.cells[index];
  if((Kind)cell.kind==Kind::TEXT) { sheet::source(app.book,position,output); return; }
  if(cell.dirty || cell.error) { copy_text(output,cell.dirty?"...":error_label((Error)cell.error),capacity); return; }
  sheet::format(cell.value,output,capacity);
}
void table() {
  visible(); const bool compact=app.book.compact!=0;
  const int step=compact?6:8, cols=compact?4:3, rows=compact?7:5;
  const int width=180/cols; char header[40], addr[8], val[sheet::SOURCE_BYTES];
  sheet::address(app.selected,app.mode==Mode::REFERENCE?app.reference_anchor:0,addr);
  if(app.mode==Mode::REFERENCE || app.mode==Mode::COPY || app.mode==Mode::FILL) {
    char origin[8]; sheet::address(app.origin,0,origin);
    copy_text(header,app.mode==Mode::REFERENCE?M8("ССЫЛКА: "):(app.mode==Mode::COPY?M8("КОПИЯ: "):M8("ВНИЗ: ")),sizeof(header));
    const uint16_t n=length(header); copy_text(header+n,addr,sizeof(header)-n);
    text(0,0,header,false,compact);
    text(100,0,app.mode==Mode::REFERENCE?M8("→"):M8("←"),false,compact);
    text(110,0,origin,false,compact); value_text(app.selected,val,sizeof(val));
    text(162,0,val,false,compact);
  } else {
    text(0,0,addr,false,compact);
    const int index=sheet::find(app.book,app.selected);
    if(index>=0) {
      const sheet::Cell& cell=app.book.cells[index];
      if((Kind)cell.kind==Kind::FORMULA) {
        formula_text(app.book.pool+cell.offset,cell.length,header,sizeof(header));
        text(compact?16:24,0,"=",false,compact);
        text(compact?24:36,0,header,false,compact,compact?170:162);
      } else { value_text(app.selected,val,sizeof(val)); text(compact?16:24,0,val,false,compact,162); }
    }
    text(168,0,angle_label(),false,compact); if(app.modified) text(186,0,"*",false,compact);
  }
  rectangle(0,step,192,step);
  for(int col=0;col<cols;++col) {
    char label[2]={(char)('A'+app.left_column+col),0};
    text(13+col*width+(width-advance(compact))/2,step,label,true,compact);
  }
  for(int row=0;row<rows;++row) {
    const uint16_t row_number=(uint16_t)(app.top_row+row+1); char digits[3];
    digits[0]=row_number>=10?(char)('0'+row_number/10):(char)('0'+row_number);
    digits[1]=row_number>=10?(char)('0'+row_number%10):0; digits[2]=0;
    const int y=2*step+row*step; text(0,y,digits,false,compact);
    for(int col=0;col<cols;++col) {
      const uint16_t position=(uint16_t)((row_number-1)*sheet::COLUMNS+app.left_column+col);
      const int x=13+col*width, right=x+width-1;
      const bool selected=position==app.selected;
      if(selected) rectangle(x,y,width-1,step);
      const int index=sheet::find(app.book,position); const bool label=index>=0 && (Kind)app.book.cells[index].kind==Kind::TEXT;
      value_text(position,val,sizeof(val));
      const uint16_t maximum=(uint16_t)((width-3)/advance(compact));
      if(!label && index>=0 && !app.book.cells[index].error && !app.book.cells[index].dirty) {
        for(uint8_t precision=7;length(val)>maximum && precision>=3;--precision)
          sheet::format(app.book.cells[index].value,val,sizeof(val),precision);
      }
      if(length(val)>maximum) {
        if(label) { val[maximum-1]='>'; val[maximum]=0; }
        else { for(uint16_t i=0;i<maximum;++i) val[i]='#'; val[maximum]=0; }
      }
      text(label?x+1:right-(int)length(val)*advance(compact),y,val,selected,compact,right);
      if((app.mode==Mode::REFERENCE || app.mode==Mode::COPY || app.mode==Mode::FILL) && position==app.origin)
        rectangle(x,y,width-1,step,false);
    }
  }
  for(int col=0;col<cols;++col) rectangle(12+col*width,step,1,rows*step+step);
  rectangle(0,55,192,1);
  const char* footer=app.mode==Mode::REFERENCE?M8("OK:ВСТАВИТЬ USER:ФИКС ESC:НАЗАД"):
      ((app.mode==Mode::COPY || app.mode==Mode::FILL)?M8("OK:ЗАПИСАТЬ ESC:НАЗАД"):M8("OK:ПРАВКА USER:МЕНЮ"));
  if(app.message!=Error::OK) footer=error_label(app.message);
  if(app.io_error) footer=M8("ОШИБКА ЧТЕНИЯ/ЗАПИСИ");
  text(0,56,footer);
}
double math(void*,Op op,double x,double y) {
  uint32_t operation;
  switch(op) {
    case Op::SIN:operation=MK61_SERVICE_SIN; break; case Op::COS:operation=MK61_SERVICE_COS; break;
    case Op::TAN:operation=MK61_SERVICE_TAN; break; case Op::ASIN:operation=MK61_SERVICE_ASIN; break;
    case Op::ACOS:operation=MK61_SERVICE_ACOS; break; case Op::ATAN:operation=MK61_SERVICE_ATAN; break;
    case Op::LN:operation=MK61_SERVICE_LN; break; case Op::LG:operation=MK61_SERVICE_LOG10; break;
    case Op::EXP:operation=MK61_SERVICE_EXP; break; case Op::SQRT:operation=MK61_SERVICE_SQRT; break;
    case Op::POW:operation=MK61_SERVICE_POW; break;
    case Op::TEN:operation=MK61_SERVICE_POW; y=x; x=10; break;
    default:return 0;
  }
  return app.services->math(operation,x,y);
}
bool service(void*) { app.api->service(); return true; }
const sheet::Host HOST={nullptr,math,service};
void recalc() { if(!sheet::recalculate(app.book,HOST)) app.message=Error::LIMIT; }
void remember() {
  app.undo_size=sheet::encode(app.book,app.archive,sizeof(app.archive));
  app.undo_modified=app.modified;
}
void undo() {
  if(app.undo_size && sheet::decode(app.book,app.archive,app.undo_size)) {
    app.modified=app.undo_modified; app.undo_size=0; recalc();
  }
}
void begin_edit(Kind kind,bool replace=false) {
  app.edit[0]=0;
  if(!replace) sheet::source(app.book,app.selected,app.edit);
  app.edit_length=length(app.edit); app.cursor=app.edit_length;
  app.edit_kind=kind; app.prefix=0; app.mode=Mode::EDIT;
  app.text_editor={}; app.text_editor.source=app.edit;
  app.text_editor.capacity=sizeof(app.edit); app.text_editor.length=app.edit_length;
  app.text_editor.cursor=app.cursor; app.text_editor.options=1U|2U|4U|8U|16U;
  app.text_editor.ok_text=""; app.text_editor.backspace_key=app.services->keyboard_mapping->cx;
}
bool insert(const char* value,bool token) {
  const uint16_t size=length(value);
  const bool space=token && app.cursor && app.edit[app.cursor-1]!=' ';
  const uint16_t added=(uint16_t)(size+(space?1:0)+(token?1:0));
  if(app.edit_length+added>=sizeof(app.edit)) { app.message=Error::LIMIT; return false; }
  memmove(app.edit+app.cursor+added,app.edit+app.cursor,app.edit_length-app.cursor+1);
  if(space) app.edit[app.cursor++]=' ';
  memcpy(app.edit+app.cursor,value,size); app.cursor=(uint16_t)(app.cursor+size);
  if(token) app.edit[app.cursor++]=' ';
  app.edit_length=(uint16_t)(app.edit_length+added);
  if(token) app.edit_kind=Kind::FORMULA;
  return true;
}
void backspace() {
  uint16_t end=app.cursor; while(end && app.edit[end-1]==' ') --end;
  uint16_t start=end; while(start && app.edit[start-1]!=' ') --start;
  double value;
  if(end>start && sheet::number(app.edit+start,(uint16_t)(end-start),value)) start=(uint16_t)(end-1);
  memmove(app.edit+start,app.edit+app.cursor,app.edit_length-app.cursor+1);
  app.edit_length=(uint16_t)(app.edit_length-(app.cursor-start)); app.cursor=start;
}
void commit() {
  uint16_t end=app.edit_length; while(end && app.edit[end-1]==' ') --end;
  uint16_t start=0; while(start<end && app.edit[start]==' ' && app.edit_kind!=Kind::TEXT) ++start;
  Kind kind=app.edit_kind;
  if(start==end) kind=Kind::EMPTY;
  else if(kind!=Kind::TEXT) { double value; kind=sheet::number(app.edit+start,(uint16_t)(end-start),value)?Kind::NUMBER:Kind::FORMULA; }
  const Error valid=sheet::validate(kind,app.edit+start,(uint16_t)(end-start));
  if(valid!=Error::OK) { app.message=valid; return; }
  remember(); app.message=sheet::set(app.book,app.selected,kind,app.edit+start,(uint16_t)(end-start));
  if(app.message!=Error::OK) { app.undo_size=0; return; }
  app.modified=true; recalc(); app.mode=Mode::TABLE;
}
void editor() {
  char addr[8]; sheet::address(app.selected,0,addr); band(0,addr);
  text(24,0,app.edit_kind==Kind::TEXT?M8("ПОДПИСЬ"):M8("ФОРМУЛА"),true);
  text(168,0,app.prefix==1?"F":(app.prefix==2?"K":angle_label()),true);
  if(app.edit_kind==Kind::TEXT) {
    uint16_t top=app.cursor/32>2?(uint16_t)((app.cursor/32-2)*32):0;
    for(uint16_t i=top;i<app.edit_length && i<top+96;++i) {
      char ch[2]={app.edit[i],0}; text((i-top)%32*6,8+(i-top)/32*8,ch);
    }
    rectangle((app.cursor-top)%32*6,8+(app.cursor-top)/32*8+7,5,1);
    text(0,40,M8("K:БУКВЫ F:СИМВОЛЫ")); text(0,48,M8("Cx:СТЕРЕТЬ ←→:КУРСОР"));
  } else {
    char display[128]; formula_text(app.edit,app.edit_length,display,sizeof(display));
    for(uint16_t i=0;display[i] && i<96;++i) {
      char ch[2]={display[i],0}; text(i%32*6,8+i/32*8,ch);
    }
    // The selected step is highlighted even when its label is a short glyph.
    uint16_t cursor=0, displayed=0; sheet::Token token={};
    while(cursor<app.edit_length) {
      while(cursor<app.edit_length && app.edit[cursor]==' ') ++cursor;
      if(cursor==app.edit_length) break;
      const Error err=sheet::next(app.edit,app.edit_length,cursor,token);
      const uint16_t n=(err==Error::OK && token.op!=Op::NUMBER && token.op!=Op::REFERENCE)?length(op_label(token.op)):(uint16_t)(token.end-token.begin);
      if(app.cursor>=token.begin && app.cursor<=token.end+1 && displayed<96) {
        rectangle(displayed%32*6,8+displayed/32*8+7,n*6,1); break;
      }
      displayed=(uint16_t)(displayed+n+1);
    }
    const double result=app.preview_value; const Error error=app.preview_error;
    char value[32]; sheet::format(result,value,sizeof(value));
    text(0,32,error==Error::OK?M8("X = "):M8("ОШИБКА: "));
    text(error==Error::OK?24:48,32,error==Error::OK?value:error_label(error));
    text(0,40,M8("USER:ССЫЛКА Cx:УДАЛИТЬ")); text(0,48,M8("←→:КУРСОР F/K:ФУНКЦИИ"));
  }
  band(56,app.message==Error::OK?M8("OK:ЗАПИСАТЬ ESC:ОТМЕНА"):error_label(app.message));
}
const char* menu_label(Mode mode,uint8_t index) {
  if(mode==Mode::FUNCTIONS) return op_label((Op)(index+(uint8_t)Op::ENTER));
  if(mode==Mode::ACTIONS) switch(index) {
    case 0:return M8("ОТМЕНИТЬ"); case 1:return M8("КОПИРОВАТЬ"); case 2:return M8("ЗАПОЛНИТЬ ВНИЗ");
    case 3:return M8("ОЧИСТИТЬ"); case 4:return M8("ТИП ЯЧЕЙКИ"); case 5:return M8("ДЕТАЛИ"); default:return M8("ЛИСТ...");
  }
  if(mode==Mode::SHEET) switch(index) {
    case 0:return M8("СОХРАНИТЬ"); case 1:return M8("СОХРАНИТЬ КАК..."); case 2:return M8("ОТКРЫТЬ...");
    case 3:return M8("НОВЫЙ ЛИСТ"); case 4:return M8("ОБЗОР 3×5 / 5×8"); case 5:return M8("УГЛЫ DEG/RAD/GRD");
    case 6:return M8("ПЕРЕСЧИТАТЬ"); default:return M8("СПРАВКА");
  }
  if(mode==Mode::TYPE) return index==0?M8("ЧИСЛО"):(index==1?M8("ПОДПИСЬ"):M8("ФОРМУЛА"));
  return index==0?M8("СОХРАНИТЬ"):(index==1?M8("БЕЗ СОХРАНЕНИЯ"):M8("ОТМЕНА"));
}
uint8_t menu_count() {
  if(app.mode==Mode::FUNCTIONS) return (uint8_t)Op::PI-(uint8_t)Op::ENTER+1;
  return app.mode==Mode::ACTIONS?7:(app.mode==Mode::SHEET?8:3);
}
void menu_draw() {
  band(0,app.mode==Mode::FUNCTIONS?M8("ОПЕРАЦИИ"):app.mode==Mode::CONFIRM?M8("ЛИСТ ИЗМЕНЁН"):
      (app.mode==Mode::SHEET?M8("ЛИСТ / SHEET"):(app.mode==Mode::TYPE?M8("ТИП ЯЧЕЙКИ"):M8("ДЕЙСТВИЯ"))));
  const uint8_t count=menu_count(), top=app.menu>=6?(uint8_t)(app.menu-5):0;
  for(uint8_t line=0;line<6 && top+line<count;++line) {
    const uint8_t index=(uint8_t)(top+line); const int y=8+line*8;
    if(index==app.menu) { rectangle(0,y,192,8); text(0,y,M8("→"),true); }
    text(12,y,menu_label(app.mode,index),index==app.menu);
  }
  band(56,M8("OK:ВЫБОР ESC:НАЗАД"));
}
bool save(bool choose) {
  char name[32]; copy_text(name,app.file_name,sizeof(name));
  uint32_t parent=app.parent, preferred=app.file_id;
  close_graphics();
  if(choose || preferred==MK61_SERVICE_INVALID_ID) {
    mk61_service_save_target target={name,parent};
    if(!app.services->call(MK61_SERVICE_FILE_SAVE_TARGET,MK61_SERVICE_FILE_SHEET,parent,sizeof(name),&target)) return false;
    parent=target.parent; preferred=MK61_SERVICE_INVALID_ID;
    const uint32_t count=app.services->call(MK61_SERVICE_FILE_COUNT,MK61_SERVICE_FILE_SHEET,0,0,nullptr);
    for(uint32_t i=0;i<count && i<4096;++i) {
      mk61_service_file file={};
      if(app.services->call(MK61_SERVICE_FILE_ENTRY,1,i,MK61_SERVICE_FILE_SHEET,&file) &&
         file.parent==parent && strcmp(file.name,name)==0) { preferred=file.id; break; }
    }
  }
  app.undo_size=0;
  const uint16_t size=sheet::encode(app.book,app.archive,sizeof(app.archive));
  mk61_service_write write={name,app.archive,size,MK61_SERVICE_INVALID_ID};
  if(!size || !app.services->call(MK61_SERVICE_FILE_WRITE,parent,preferred,MK61_SERVICE_FILE_SHEET,&write)) {
    app.io_error=true; return false;
  }
  copy_text(app.file_name,name,sizeof(app.file_name)); app.parent=parent; app.file_id=write.id;
  app.modified=false; app.io_error=false; return true;
}
bool load(uint32_t id) {
  mk61_service_file file={};
  if(!app.services->call(MK61_SERVICE_FILE_ENTRY,0,id,0,&file) ||
     file.kind!=0 || file.type!=MK61_SERVICE_FILE_SHEET) return false;
  const uint32_t size=app.api->file_size(id);
  if(size<20 || size>sizeof(app.archive)) return false;
  app.undo_size=0;
  if(app.api->file_read(id,0,app.archive,size)!=size || !sheet::decode(app.book,app.archive,(uint16_t)size)) return false;
  app.parent=file.parent; copy_text(app.file_name,file.name,sizeof(app.file_name));
  app.file_id=id; app.modified=false; app.io_error=false; app.selected=app.top_row=app.left_column=0;
  recalc(); return true;
}
void execute_pending() {
  const Pending pending=app.pending; app.pending=Pending::NONE; app.mode=Mode::TABLE;
  if(pending==Pending::EXIT) { app.exit=true; return; }
  if(pending==Pending::NEW) {
    sheet::clear(app.book); app.file_id=MK61_SERVICE_INVALID_ID; app.parent=MK61_SERVICE_ROOT_ID;
    copy_text(app.file_name,"SHEET",sizeof(app.file_name)); app.modified=false; app.undo_size=0;
    app.selected=app.top_row=app.left_column=0; return;
  }
  if(pending==Pending::OPEN) {
    close_graphics(); mk61_service_choice choice={};
    if(app.services->call(MK61_SERVICE_FILE_CHOOSE,MK61_SERVICE_FILE_SHEET,app.parent,0,&choice)==1 && !load(choice.file.id)) app.io_error=true;
  }
}
void request(Pending pending) {
  app.pending=pending;
  if(app.modified) { app.mode=Mode::CONFIRM; app.menu=0; }
  else execute_pending();
}
void copy_begin(bool fill) {
  const int index=sheet::find(app.book,app.selected);
  app.copied_kind=index<0?(uint8_t)Kind::EMPTY:app.book.cells[index].kind;
  sheet::source(app.book,app.selected,app.copied); app.origin=app.selected;
  app.mode=fill?Mode::FILL:Mode::COPY;
}
void copy_commit() {
  const bool fill=app.mode==Mode::FILL;
  if(fill && app.selected/sheet::COLUMNS<=app.origin/sheet::COLUMNS) { app.mode=Mode::TABLE; return; }
  remember(); const uint16_t first=fill?(uint16_t)(app.origin+sheet::COLUMNS):app.selected;
  const uint16_t step=fill?sheet::COLUMNS:1;
  for(uint16_t destination=first;destination<=app.selected;destination=(uint16_t)(destination+step)) {
    char translated[sheet::SOURCE_BYTES]; const Kind kind=(Kind)app.copied_kind;
    if(kind==Kind::FORMULA) app.message=sheet::translate(app.copied,length(app.copied),
        (int)(destination%sheet::COLUMNS)-(int)(app.origin%sheet::COLUMNS),
        (int)(destination/sheet::COLUMNS)-(int)(app.origin/sheet::COLUMNS),translated);
    else copy_text(translated,app.copied,sizeof(translated));
    if(app.message==Error::OK) app.message=sheet::set(app.book,destination,kind,translated,length(translated));
    if(app.message!=Error::OK) { const Error error=app.message; undo(); app.message=error; app.mode=Mode::TABLE; return; }
    if(!fill) break;
  }
  app.modified=true; recalc(); app.mode=Mode::TABLE;
}
void action() {
  const uint8_t item=app.menu; const Mode mode=app.mode; app.mode=Mode::TABLE;
  if(mode==Mode::FUNCTIONS) {
    app.mode=Mode::EDIT; (void)insert(sheet::op_text((Op)(item+(uint8_t)Op::ENTER)),true); return;
  }
  if(mode==Mode::CONFIRM) {
    if(item==2) { app.pending=Pending::NONE; return; }
    if(item==0 && !save(false)) return;
    execute_pending(); return;
  }
  if(mode==Mode::TYPE) { begin_edit(item==1?Kind::TEXT:(item==0?Kind::NUMBER:Kind::FORMULA),true); return; }
  if(mode==Mode::ACTIONS) switch(item) {
    case 0:undo(); break; case 1:copy_begin(false); break; case 2:copy_begin(true); break;
    case 3:remember(); app.message=sheet::set(app.book,app.selected,Kind::EMPTY,nullptr,0); app.modified=true; recalc(); break;
    case 4:app.mode=Mode::TYPE; app.menu=0; break; case 5:app.mode=Mode::DETAILS; break;
    default:app.mode=Mode::SHEET; app.menu=0; break;
  } else switch(item) {
    case 0:(void)save(false); break; case 1:(void)save(true); break;
    case 2:request(Pending::OPEN); break; case 3:request(Pending::NEW); break;
    case 4:remember(); app.book.compact^=1; app.modified=true; break;
    case 5:remember(); app.book.angle=(uint8_t)((app.book.angle+1)%3); app.modified=true; sheet::invalidate(app.book); recalc(); break;
    case 6:sheet::invalidate(app.book); recalc(); break;
    default:app.mode=Mode::HELP; app.page=0; break;
  }
}
void move(int key,bool vertical_only=false) {
  uint16_t col=app.selected%sheet::COLUMNS, row=app.selected/sheet::COLUMNS;
  if(key==MK61_APP_KEY_SHIFT_LEFT && row) --row;
  if(key==MK61_APP_KEY_SHIFT_RIGHT && row+1<sheet::ROWS) ++row;
  if(key==MK61_APP_KEY_LEFT) { if(vertical_only) { if(row) --row; } else if(col) --col; }
  if(key==MK61_APP_KEY_RIGHT) { if(vertical_only) { if(row+1<sheet::ROWS) ++row; } else if(col+1<sheet::COLUMNS) ++col; }
  app.selected=(uint16_t)(row*sheet::COLUMNS+col);
}
int raw_key(int key) {
  const mk61_service_keyboard& k=*app.services->keyboard_mapping;
  if(key>=0 && key<=9) return k.digit[key];
  if(key>=MK61_APP_KEY_RAW_BASE) return key-MK61_APP_KEY_RAW_BASE;
  switch(key) {
    case MK61_APP_KEY_DECIMAL:return k.dot; case MK61_APP_KEY_ADD:return k.add;
    case MK61_APP_KEY_SUBTRACT:return k.sub; case MK61_APP_KEY_MULTIPLY:return k.mul;
    case MK61_APP_KEY_DIVIDE:return k.div; case MK61_APP_KEY_LEFT:return k.left;
    case MK61_APP_KEY_RIGHT:return k.right; case MK61_APP_KEY_SHIFT_LEFT:return k.shg_left;
    case MK61_APP_KEY_SHIFT_RIGHT:return k.shg_right; case MK61_APP_KEY_OK:return k.ok;
    case MK61_APP_KEY_ESC:return k.esc; case MK61_APP_KEY_CLEAR:return k.cx;
    case MK61_APP_KEY_K:return k.k; case MK61_APP_KEY_F:return k.alpha;
    case MK61_APP_KEY_PP:return k.pp; case MK61_APP_KEY_FORWARD:return k.frw;
    default:return -1;
  }
}
void calculator_key(int key) {
  if(key==MK61_APP_KEY_F || key==MK61_APP_KEY_K) { app.prefix=(uint8_t)(key==MK61_APP_KEY_F?1:2); return; }
  const mk61_service_keyboard& k=*app.services->keyboard_mapping;
  const int raw=raw_key(key); Op op=Op::NUMBER;
  if(app.prefix==1) {
    const Op digits[]={Op::TEN,Op::EXP,Op::LG,Op::LN,Op::ASIN,Op::ACOS,Op::ATAN,Op::SIN,Op::COS,Op::TAN};
    if(key>=0 && key<=9) op=digits[key];
    else if(key==MK61_APP_KEY_SUBTRACT) op=Op::SQRT;
    else if(key==MK61_APP_KEY_DIVIDE) op=Op::INV;
    else if(key==MK61_APP_KEY_ADD) op=Op::PI;
    else if(key==MK61_APP_KEY_MULTIPLY) op=Op::SQR;
    else if(raw==k.xy) op=Op::POW;
  } else if(app.prefix==2) {
    if(key==4) op=Op::ABS; else if(key==7) op=Op::INT; else if(key==8) op=Op::FRAC;
  } else {
    if(key>=0 && key<=9) { char digit[2]={(char)('0'+key),0}; (void)insert(digit,false); return; }
    if(key==MK61_APP_KEY_DECIMAL) { (void)insert(".",false); return; }
    if(raw==k.power) { (void)insert("E",false); return; }
    if(raw==k.neg) {
      uint16_t start=app.cursor; while(start && app.edit[start-1]!=' ') --start;
      uint16_t exponent=start; for(uint16_t i=start;i<app.cursor;++i) if(app.edit[i]=='E') exponent=(uint16_t)(i+1);
      double value;
      if(exponent!=start || sheet::number(app.edit+start,(uint16_t)(app.cursor-start),value)) {
        if(app.edit[exponent]=='-') { memmove(app.edit+exponent,app.edit+exponent+1,app.edit_length-exponent); --app.edit_length; --app.cursor; }
        else { const uint16_t saved=app.cursor; app.cursor=exponent; if(insert("-",false)) app.cursor=(uint16_t)(saved+1); }
        return;
      }
      op=Op::NEG;
    }
    else if(raw==k.bx) op=Op::ENTER;
    else if(raw==k.xy) op=Op::SWAP;
    else if(key==MK61_APP_KEY_FORWARD) op=Op::ROLL;
    else if(key==MK61_APP_KEY_ADD) op=Op::ADD;
    else if(key==MK61_APP_KEY_SUBTRACT) op=Op::SUB;
    else if(key==MK61_APP_KEY_MULTIPLY) op=Op::MUL;
    else if(key==MK61_APP_KEY_DIVIDE) op=Op::DIV;
  }
  app.prefix=0;
  if(op==Op::NUMBER) { app.message=Error::SYNTAX; return; }
  (void)insert(sheet::op_text(op),true);
}
void key(int value) {
  app.message=Error::OK; app.io_error=false; app.redraw=true;
  if(app.mode==Mode::TABLE) {
    if(value==MK61_APP_KEY_ESC) request(Pending::EXIT);
    else if(value==MK61_APP_KEY_USER) { app.mode=Mode::ACTIONS; app.menu=0; }
    else if(value==MK61_APP_KEY_OK) {
      const int index=sheet::find(app.book,app.selected);
      begin_edit(index<0?Kind::NUMBER:(Kind)app.book.cells[index].kind);
    } else if(value>=0 && value<=9) { begin_edit(Kind::NUMBER,true); calculator_key(value); }
    else if(value==MK61_APP_KEY_RUN) { sheet::invalidate(app.book); recalc(); }
    else move(value);
    return;
  }
  if(app.mode==Mode::EDIT) {
    if(value==MK61_APP_KEY_ESC) { app.mode=Mode::TABLE; return; }
    if(value==MK61_APP_KEY_OK) { commit(); return; }
    if(app.edit_kind==Kind::TEXT) {
      auto& editor=app.text_editor; editor.key=raw_key(value); editor.now=app.api->millis_ms();
      app.services->call(MK61_SERVICE_EDITOR_KEY,0,0,0,&editor);
      app.edit_length=(uint16_t)editor.length; app.cursor=(uint16_t)editor.cursor; return;
    }
    if(value==MK61_APP_KEY_USER) {
      if(app.prefix) { app.prefix=0; app.mode=Mode::FUNCTIONS; app.menu=0; }
      else { app.origin=app.selected; app.reference_anchor=0; app.mode=Mode::REFERENCE; }
      return;
    }
    if(value==MK61_APP_KEY_LEFT) { if(app.cursor) --app.cursor; return; }
    if(value==MK61_APP_KEY_RIGHT) { if(app.cursor<app.edit_length) ++app.cursor; return; }
    if(value==MK61_APP_KEY_SHIFT_LEFT) { app.cursor=0; return; }
    if(value==MK61_APP_KEY_SHIFT_RIGHT) { app.cursor=app.edit_length; return; }
    if(value==MK61_APP_KEY_CLEAR) { backspace(); return; }
    calculator_key(value); return;
  }
  if(app.mode==Mode::REFERENCE) {
    if(value==MK61_APP_KEY_ESC) { app.selected=app.origin; app.mode=Mode::EDIT; }
    else if(value==MK61_APP_KEY_USER) app.reference_anchor=(uint8_t)((app.reference_anchor+1)%4);
    else if(value==MK61_APP_KEY_OK) {
      char addr[8]; sheet::address(app.selected,app.reference_anchor,addr);
      app.selected=app.origin; app.mode=Mode::EDIT; (void)insert(addr,true);
    } else move(value);
    return;
  }
  if(app.mode==Mode::COPY || app.mode==Mode::FILL) {
    if(value==MK61_APP_KEY_ESC) { app.selected=app.origin; app.mode=Mode::TABLE; }
    else if(value==MK61_APP_KEY_OK) copy_commit(); else move(value,app.mode==Mode::FILL);
    return;
  }
  if(app.mode==Mode::HELP || app.mode==Mode::DETAILS) {
    if(value==MK61_APP_KEY_ESC || (app.mode==Mode::DETAILS && value==MK61_APP_KEY_OK)) app.mode=Mode::TABLE;
    else if(value==MK61_APP_KEY_OK || value==MK61_APP_KEY_RIGHT) app.page^=1;
    return;
  }
  if(value==MK61_APP_KEY_ESC) { app.mode=app.mode==Mode::FUNCTIONS?Mode::EDIT:Mode::TABLE; app.pending=Pending::NONE; }
  else if(value==MK61_APP_KEY_OK) action();
  else if((value==MK61_APP_KEY_LEFT || value==MK61_APP_KEY_SHIFT_LEFT) && app.menu) --app.menu;
  else if((value==MK61_APP_KEY_RIGHT || value==MK61_APP_KEY_SHIFT_RIGHT) && app.menu+1<menu_count()) ++app.menu;
}
void help() {
  band(0,app.mode==Mode::DETAILS?M8("ЯЧЕЙКА / ЗНАЧЕНИЕ"):M8("SHEET / СПРАВКА"));
  if(app.mode==Mode::DETAILS) {
    char addr[8], value[sheet::SOURCE_BYTES]; sheet::address(app.selected,0,addr); text(0,8,addr);
    const int i=sheet::find(app.book,app.selected);
    if(i>=0) {
      const sheet::Cell& cell=app.book.cells[i];
      if(cell.error) {
        text(0,16,error_label((Error)cell.error));
        const char* why=cell.error==(uint8_t)Error::CYCLE?M8("ЦИКЛ ИЛИ ЗАВИСИМОСТЬ ОТ ЦИКЛА"):
          (cell.error==(uint8_t)Error::TYPE?M8("ПОДПИСЬ ИСПОЛЬЗОВАНА КАК ЧИСЛО"):
          (cell.error==(uint8_t)Error::REFERENCE?M8("ССЫЛКА ЗА ПРЕДЕЛАМИ ЛИСТА"):M8("ОШИБКА МАТЕМАТИКИ/ФОРМУЛЫ")));
        text(0,24,why);
      } else { sheet::format(cell.value,value,sizeof(value),14); text(0,16,value); }
      sheet::source(app.book,app.selected,value);
      for(uint16_t n=0;value[n] && n<64;++n) { char c[2]={value[n],0}; text(n%32*6,32+n/32*8,c); }
    }
  } else {
    const char* lines[5];
    if(!app.page) {
      lines[0]=M8("←→:СТОЛБЕЦ ШГ:СТРОКА"); lines[1]=M8("OK:ПРАВКА USER:ДЕЙСТВИЯ");
      lines[2]=M8("В ФОРМУЛЕ USER:ССЫЛКА"); lines[3]=M8("В↑ ОТДЕЛЯЕТ ОПЕРАНДЫ"); lines[4]=M8("USER В ССЫЛКЕ:ФИКСАЦИЯ $");
    } else {
      lines[0]=M8("16×32 ЯЧЕЕК, 64 ЗАПОЛНЕННЫХ"); lines[1]=M8("1536 БАЙТ ДАННЫХ ЛИСТА");
      lines[2]=M8("F USER:СПИСОК ОПЕРАЦИЙ"); lines[3]=M8("ФАЙЛЫ .MKS / S1 С CRC32"); lines[4]=M8("С/П:ПЕРЕСЧЁТ ESC:ВЫХОД");
    }
    for(uint8_t i=0;i<5;++i) text(0,8+i*8,lines[i]);
  }
  band(56,app.mode==Mode::DETAILS?M8("OK/ESC:НАЗАД"):M8("OK:СТРАНИЦА ESC:НАЗАД"));
}
uint32_t run(uint32_t file_id) {
  memset(&app,0,sizeof(app)); app.api=mk61_api;
  const uint32_t caps=MK61_APP_CAP_TIME|MK61_APP_CAP_KEYBOARD|MK61_APP_CAP_FILES|MK61_APP_CAP_GRAPHICS;
  if(!mk61_app_api_compatible(app.api,sizeof(*app.api),caps)) return MK61_APP_UNSUPPORTED_DISPLAY;
  app.services=mk61_app_get_services(app.api,MK61_SERVICE_CAP_UI|MK61_SERVICE_CAP_FILES|
      MK61_SERVICE_CAP_DIALOGS|MK61_SERVICE_CAP_EDITOR|MK61_SERVICE_CAP_FONT|MK61_SERVICE_CAP_MATH|
      MK61_SERVICE_CAP_NUMBER_IO|MK61_SERVICE_CAP_MEMORY);
  if(!app.services || !app.services->keyboard_mapping) return MK61_APP_RUNTIME_ERROR;
  sheet::number_io(parse_number,format_number);
  app.file_id=MK61_SERVICE_INVALID_ID; app.parent=MK61_SERVICE_ROOT_ID;
  copy_text(app.file_name,"SHEET",sizeof(app.file_name));
  if(file_id!=MK61_SERVICE_INVALID_ID && !load(file_id)) return MK61_APP_INVALID_FILE;
  app.redraw=true;
  uint32_t result=MK61_APP_OK;
  while(!app.exit) {
    if(app.graphics && app.api->graphics_revision()!=app.revision) { close_graphics(); app.redraw=true; }
    if(!open_graphics()) { result=MK61_APP_UNSUPPORTED_DISPLAY; break; }
    if(app.redraw) {
      // A frame only exists during rasterization. Release SCRATCH before
      // calculator math, dialogs and C6, which may need that same arena.
      if(app.mode==Mode::EDIT && app.edit_kind!=Kind::TEXT)
        app.preview_error=sheet::evaluate(app.book,app.edit,app.edit_length,HOST,app.preview_value);
      if(!app.services->call(MK61_SERVICE_MEMORY_ACQUIRE,MK61_SERVICE_SCRATCH,MK61_SERVICE_OWNER_APP,1536,&app.frame_lease)) {
        result=MK61_APP_BUSY; break;
      }
      app.frame=app.frame_lease.data;
      if(!app.frame || app.frame_lease.size<1536) {
        app.services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_SCRATCH,0,0,&app.frame_lease);
        result=MK61_APP_BUSY; break;
      }
      memset(app.frame,0,1536);
      if(app.mode==Mode::EDIT) editor();
      else if(app.mode==Mode::TABLE || app.mode==Mode::REFERENCE || app.mode==Mode::COPY || app.mode==Mode::FILL) table();
      else if(app.mode==Mode::HELP || app.mode==Mode::DETAILS) help(); else menu_draw();
      const bool presented=app.api->graphics_present(app.frame,1536)!=0;
      app.services->call(MK61_SERVICE_MEMORY_RELEASE,MK61_SERVICE_SCRATCH,0,0,&app.frame_lease);
      app.frame=nullptr;
      if(!presented) { result=MK61_APP_RUNTIME_ERROR; break; }
      app.redraw=false;
    }
    app.api->service(); const int32_t input=app.api->key_poll();
    if(input!=MK61_APP_KEY_NONE) key(input); else app.api->delay_ms(5);
  }
  close_graphics(); return result;
}
}
extern "C" uint32_t mk61_app_open_file(uint32_t file_id) { return run(file_id); }
int main() { return (int)run(MK61_SERVICE_INVALID_ID); }
