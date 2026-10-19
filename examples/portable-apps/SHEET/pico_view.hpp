// PicoCalc presentation in physical pixels. The document, editing commands,
// formula engine and S1 format are shared with the Classic application.
namespace pico_sheet {
constexpr int LEFT=32, GRID_TOP=56, FOOTER=286;
int size() { return app.book.compact?12:16; }
int pitch() { return app.book.compact?18:24; }
int columns() { return app.book.compact?4:3; }
int rows() { return app.book.compact?11:8; }
mk61_service_ui_glyph glyph(uint8_t byte,int pixels=16) {
  mk61_service_ui_glyph g={};g.family=1;g.size=(uint32_t)pixels;
  app.services->call(MK61_SERVICE_UI_FONT,MK61_UI_FONT_GLYPH,
      mk8::codepoint(byte),sizeof(g),&g);
  return g;
}
int width(const char* value,int pixels=16) {
  int result=0;for(;*value;++value) result+=(int)glyph((uint8_t)*value,pixels).advance;
  return result;
}
void box(int x,int y,int w,int h,bool fill=true) {
  for(int dy=0;dy<h;++dy) for(int dx=0;dx<w;++dx)
    if(fill || !dy || dy==h-1 || !dx || dx==w-1) pixel(x+dx,y+dy);
}
int letter(int x,int y,uint8_t byte,bool inverse=false,int pixels=16,int right=320) {
  const auto g=glyph(byte,pixels);const int baseline=y+(pixels==12?10:14);
  for(unsigned gy=0;gy<g.height;++gy) for(unsigned gx=0;gx<g.width;++gx) {
    const int px=x+g.bearing_x+(int)gx;
    if(px>=x && px<right && (g.pixels[gy*((g.width+7)/8)+gx/8]&(0x80U>>(gx&7))))
      pixel(px,baseline-g.bearing_y+(int)gy,!inverse);
  }
  return (int)g.advance;
}
void text(int x,int y,const char* value,bool inverse=false,int pixels=16,int right=316) {
  for(;*value;++value) {
    const int step=(int)glyph((uint8_t)*value,pixels).advance;
    if(x+step>right) break;
    x+=letter(x,y,(uint8_t)*value,inverse,pixels,right);
  }
}
// Fit labels by measured glyph advances; never let ink enter the next cell.
void fit(char* value,int maximum,int pixels,bool mark=true) {
  if(width(value,pixels)<=maximum) return;
  const int tail=mark?width(">",pixels):0;int used=0;unsigned at=0;
  while(value[at] && used+(int)glyph((uint8_t)value[at],pixels).advance+tail<=maximum)
    used+=(int)glyph((uint8_t)value[at++],pixels).advance;
  if(mark && maximum>=tail) value[at++]='>';
  value[at]=0;
}
void header(const char* label,const char* status=nullptr) {
  box(0,0,320,28);const int right=status?312-width(status):316;
  text(8,6,label,true,16,right-4);
  if(status) text(right,6,status,true);
}
void footer(const char* first,const char* second=nullptr) {
  box(0,FOOTER-4,320,1);text(8,FOOTER,first);
  if(second) text(8,FOOTER+18,second);
}
// Pixel wrapping for editor/source text. Include the final space so the end
// caret also wraps when the preceding glyph reaches the right margin.
void flow(const char* value,int top,unsigned first,unsigned last,bool caret=false,
          unsigned visible_rows=6,unsigned page=0) {
  int x=8;unsigned row=0;
  for(unsigned i=0;;++i) {
    const bool end=!value[i];const uint8_t byte=end?' ':(uint8_t)value[i];
    const int step=(int)glyph(byte).advance;
    if(x+step>312) { x=8;++row; }
    if(row>=page*visible_rows && row<(page+1)*visible_rows) {
      const int y=top+(int)(row-page*visible_rows)*24;
      if(!end) letter(x,y,byte);
      if(i>=first && (i<last || (caret && i==first))) box(x,y+18,step,1);
    }
    if(end) break;
    x+=step;
  }
}
}

void table() {
  using namespace pico_sheet;
  visible();char address[8],label[48],value[sheet::SOURCE_BYTES];
  sheet::address(app.selected,app.mode==Mode::REFERENCE?app.reference_anchor:0,address);
  const bool picking=app.mode==Mode::REFERENCE || app.mode==Mode::COPY || app.mode==Mode::FILL;
  copy_text(label,picking?(app.mode==Mode::REFERENCE?M8("ССЫЛКА: "):
      (app.mode==Mode::COPY?M8("КОПИЯ: "):M8("ВНИЗ: "))):"SHEET / ",sizeof(label));
  copy_text(label+length(label),address,sizeof(label)-length(label));
  char status[8];copy_text(status,angle_label(),sizeof(status));
  if(app.modified) copy_text(status+length(status)," *",sizeof(status)-length(status));
  header(label,status);
  const int selected=sheet::find(app.book,app.selected);
  if(picking) {
    char origin[8];sheet::address(app.origin,0,origin);
    copy_text(label,app.mode==Mode::REFERENCE?M8("В ФОРМУЛУ "):M8("ИЗ ЯЧЕЙКИ "),sizeof(label));
    copy_text(label+length(label),origin,sizeof(label)-length(label));text(8,34,label,false,16,176);
    value_text(app.selected,value,sizeof(value));fit(value,128,16);text(312-width(value),34,value);
  } else if(selected>=0) {
    const auto& cell=app.book.cells[selected];
    if((Kind)cell.kind==Kind::FORMULA) {
      formula_text(app.book.pool+cell.offset,cell.length,value,sizeof(value));
      fit(value,288,16);text(8,34,"=");text(24,34,value);
    } else { value_text(app.selected,value,sizeof(value));fit(value,304,16);text(8,34,value); }
  }
  const int count=columns(),row_count=rows(),height=pitch(),pixels=size(),cell_width=288/count;
  box(0,GRID_TOP,320,height);
  for(int col=0;col<count;++col) {
    char name[2]={(char)('A'+app.left_column+col),0};
    text(LEFT+col*cell_width+(cell_width-width(name,pixels))/2,
         GRID_TOP+(height-pixels)/2,name,true,pixels);
  }
  for(int row=0;row<row_count;++row) {
    const uint16_t number=(uint16_t)(app.top_row+row+1);char digits[3];
    digits[0]=(char)('0'+(number>=10?number/10:number));
    digits[1]=number>=10?(char)('0'+number%10):0;digits[2]=0;
    const int y=GRID_TOP+(row+1)*height,ty=y+(height-pixels)/2;
    text(LEFT-4-width(digits,pixels),ty,digits,false,pixels);
    for(int col=0;col<count;++col) {
      const uint16_t position=(uint16_t)((number-1)*sheet::COLUMNS+app.left_column+col);
      const int x=LEFT+col*cell_width,right=x+cell_width-4,maximum=cell_width-8;
      const bool active=position==app.selected;
      if(active) box(x+1,y+1,cell_width-2,height-2);
      const int index=sheet::find(app.book,position);
      const bool is_label=index>=0 && (Kind)app.book.cells[index].kind==Kind::TEXT;
      value_text(position,value,sizeof(value));
      if(!is_label && index>=0 && !app.book.cells[index].error && !app.book.cells[index].dirty)
        for(uint8_t precision=7;width(value,pixels)>maximum && precision>=3;--precision)
          sheet::format(app.book.cells[index].value,value,sizeof(value),precision);
      if(width(value,pixels)>maximum && !is_label) copy_text(value,"###",sizeof(value));
      fit(value,maximum,pixels);
      text(is_label?x+4:right-width(value,pixels),ty,value,active,pixels,right);
      if(picking && position==app.origin) box(x+1,y+1,cell_width-2,height-2,false);
      box(x,y+height-1,cell_width,1);
    }
  }
  for(int col=0;col<=count;++col) box(LEFT+col*cell_width-1,GRID_TOP,1,(row_count+1)*height);
  const char* first=app.mode==Mode::REFERENCE?M8("OK:ВСТАВИТЬ  USER:ФИКСАЦИЯ"):
      (picking?M8("OK:ЗАПИСАТЬ  ESC:НАЗАД"):M8("OK:ПРАВКА  USER:МЕНЮ"));
  if(app.message!=Error::OK) first=error_label(app.message);
  if(app.io_error) first=M8("ОШИБКА ЧТЕНИЯ/ЗАПИСИ");
  footer(first,picking?nullptr:M8("←→:СТОЛБЕЦ  ↑↓:СТРОКА"));
}

void editor() {
  using namespace pico_sheet;
  char address[8],title[32];sheet::address(app.selected,0,address);
  copy_text(title,address,sizeof(title));copy_text(title+length(title),
      app.edit_kind==Kind::TEXT?M8(" / ПОДПИСЬ"):M8(" / ФОРМУЛА"),sizeof(title)-length(title));
  const char* input_mode=app.phone.layout==phone_input::RUSSIAN?
      (app.phone.lowercase?M8("рус"):M8("РУС")):
      (app.phone.layout==phone_input::LATIN?(app.phone.lowercase?"abc":"ABC"):"123");
  header(title,app.edit_kind==Kind::TEXT?input_mode:(app.prefix==1?"F":app.prefix==2?"K":angle_label()));
  box(4,36,312,166,false);
  if(app.edit_kind==Kind::TEXT) {
    const unsigned caret=app.cursor-(app.phone.key && app.cursor?1:0);
    flow(app.edit,44,caret,caret,true);
    if(app.phone.key) {
      char group[16]={(char)('0'+app.phone.key),':',' ',0};const char* letters=phone_input::group(app.phone,app.phone.key);
      unsigned end=3;for(unsigned i=0;letters[i] && end+1<sizeof(group);++i)
        group[end++]=phone_input::letter(app.phone,(uint8_t)letters[i]);
      group[end]=0;text(8,214,group);
    } else text(8,214,app.phone.layout==phone_input::DIGITS?M8("0..9:ЦИФРЫ"):
        M8("2..9:БУКВЫ  0:ПРОБЕЛ  1:ЗНАКИ"));
    text(8,242,M8("K:РУС/ЛАТ/123  F:РЕГИСТР"));text(8,264,M8("Cx:СТЕРЕТЬ  ←→:КУРСОР"));
  } else {
    char display[128];formula_text(app.edit,app.edit_length,display,sizeof(display));
    uint16_t cursor=0,displayed=0,first=length(display),last=first;sheet::Token token={};
    while(cursor<app.edit_length) {
      while(cursor<app.edit_length && app.edit[cursor]==' ') ++cursor;
      if(cursor==app.edit_length) break;
      const auto error=sheet::next(app.edit,app.edit_length,cursor,token);
      const uint16_t count=(error==Error::OK && token.op!=Op::NUMBER && token.op!=Op::REFERENCE)?
          length(op_label(token.op)):(uint16_t)(token.end-token.begin);
      if(app.cursor>=token.begin && app.cursor<=token.end+1) {first=displayed;last=(uint16_t)(first+count);break;}
      displayed=(uint16_t)(displayed+count+1);
    }
    flow(display,44,first,last,true);
    char value[40];sheet::format(app.preview_value,value,sizeof(value));
    const bool valid=app.preview_error==Error::OK;text(8,214,valid?"X = ":M8("ОШИБКА: "));
    text(valid?40:112,214,valid?value:error_label(app.preview_error));
    text(8,242,M8("USER:ССЫЛКА  Cx:УДАЛИТЬ"));text(8,264,M8("←→:КУРСОР  F/K:ФУНКЦИИ"));
  }
  footer(app.message==Error::OK?M8("OK:ЗАПИСАТЬ  ESC:ОТМЕНА"):error_label(app.message));
}

void menu_draw() {
  using namespace pico_sheet;
  header(app.mode==Mode::FUNCTIONS?M8("ОПЕРАЦИИ"):app.mode==Mode::CONFIRM?M8("ЛИСТ ИЗМЕНЁН"):
      app.mode==Mode::SHEET?M8("ЛИСТ / SHEET"):app.mode==Mode::TYPE?M8("ТИП ЯЧЕЙКИ"):M8("ДЕЙСТВИЯ"));
  const unsigned count=menu_count(),top=app.menu>=8?app.menu-7:0;
  for(unsigned line=0;line<8 && top+line<count;++line) {
    const unsigned index=top+line;const int y=38+(int)line*29;
    if(index==app.menu) {box(4,y,312,26);text(8,y+5,M8("→"),true);}
    text(32,y+5,menu_label(app.mode,(uint8_t)index),index==app.menu);
  }
  footer(M8("OK:ВЫБОР  ESC:НАЗАД"),M8("↑↓:ВЫБРАТЬ ПУНКТ"));
}

void help() {
  using namespace pico_sheet;
  header(app.mode==Mode::DETAILS?M8("ЯЧЕЙКА / ЗНАЧЕНИЕ"):M8("SHEET / СПРАВКА"));
  if(app.mode==Mode::DETAILS) {
    char address[8],value[sheet::SOURCE_BYTES];sheet::address(app.selected,0,address);text(8,40,address);
    const int index=sheet::find(app.book,app.selected);
    if(index>=0) {
      const auto& cell=app.book.cells[index];
      if(cell.error) {
        text(8,66,error_label((Error)cell.error));
        const char* why=cell.error==(uint8_t)Error::CYCLE?M8("ЦИКЛ ИЛИ ЗАВИСИМОСТЬ ОТ ЦИКЛА"):
            cell.error==(uint8_t)Error::TYPE?M8("ПОДПИСЬ ИСПОЛЬЗОВАНА КАК ЧИСЛО"):
            cell.error==(uint8_t)Error::REFERENCE?M8("ССЫЛКА ЗА ПРЕДЕЛАМИ ЛИСТА"):M8("ОШИБКА МАТЕМАТИКИ/ФОРМУЛЫ");
        flow(why,92,0,0,false,2);
      } else if((Kind)cell.kind!=Kind::TEXT) {sheet::format(cell.value,value,sizeof(value),14);text(8,66,value);}
      sheet::source(app.book,app.selected,value);flow(value,140,0,0,false,6);
    }
    footer(M8("OK/ESC:НАЗАД"));
  } else {
    const char* lines[5];
    if(!app.page) {
      lines[0]=M8("←→:СТОЛБЕЦ  ↑↓:СТРОКА");lines[1]=M8("OK:ПРАВКА  USER:ДЕЙСТВИЯ");
      lines[2]=M8("В ФОРМУЛЕ USER:ССЫЛКА");lines[3]=M8("В↑ ОТДЕЛЯЕТ ОПЕРАНДЫ");lines[4]=M8("USER В ССЫЛКЕ:ФИКСАЦИЯ $");
    } else {
      lines[0]=M8("16×32 ЯЧЕЕК, 64 ЗАПОЛНЕННЫХ");lines[1]=M8("1536 БАЙТ ДАННЫХ ЛИСТА");
      lines[2]=M8("F USER:СПИСОК ОПЕРАЦИЙ");lines[3]=M8("ФАЙЛЫ .MKS / S1 С CRC32");lines[4]=M8("С/П:ПЕРЕСЧЁТ  ESC:ВЫХОД");
    }
    for(unsigned i=0;i<5;++i) flow(lines[i],40+(int)i*46,0,0,false,2);
    footer(M8("OK:СТРАНИЦА  ESC:НАЗАД"));
  }
}
