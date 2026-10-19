/* PicoCalc-only presentation. Editor keys and DOCTOR still use the shared
 * services/engine; every visible glyph is the resident native 16px strike.
 * The bitmap is borrowed from the host, never allocated in the APP arena. */
#define PICO_VIEW_LEFT 8U
#define PICO_VIEW_WIDTH 304U
#define PICO_VIEW_TOP 40U
#define PICO_VIEW_PITCH 24U
#define PICO_VIEW_ROWS 11U
#define PICO_VIEW_ASCENT 14U

static const mk61_app_services* pico_view_services;

static int pico_view_begin(const mk61_app_services* services) {
  mk61_service_framebuffer frame = {0};
  mk61_service_ui_glyph probe;
  if(!(mk61_api->capabilities & MK61_APP_CAP_GRAPHICS) ||
     !(services->call(MK61_SERVICE_CAPABILITIES,0,0,0,NULL) & MK61_SERVICE_CAP_UI_FONT) ||
     !mk61_api->graphics_available || !mk61_api->graphics_available() ||
     !mk61_api->graphics_width || !mk61_api->graphics_height ||
     mk61_api->graphics_width()!=HELP_WIDTH || mk61_api->graphics_height()!=HELP_HEIGHT ||
     !mk61_api->graphics_begin || !mk61_api->graphics_present || !mk61_api->graphics_end ||
     !help_glyph(services,'M',&probe) || !mk61_api->graphics_begin()) return 0;
  if(!services->call(MK61_SERVICE_DISPLAY,MK61_SERVICE_DISPLAY_FRAMEBUFFER,sizeof(frame),0,&frame) ||
     !frame.pixels || frame.width!=HELP_WIDTH || frame.height!=HELP_HEIGHT || frame.bytes!=HELP_FRAME_BYTES) {
    mk61_api->graphics_end();return 0;
  }
  help_frame=frame.pixels;pico_view_services=services;return 1;
}

static void pico_view_end(void) {
  if(pico_view_services) mk61_api->graphics_end();
  pico_view_services=NULL;help_frame=NULL;
}

/* Return a word boundary when possible, with a bounded character split for a
 * single overlong word. take excludes trailing spaces; next always advances. */
static const char* pico_wrap(const char* text,uint32_t* take) {
  uint32_t count=0,width=0,space=0;
  while(text[count] && text[count]!='\r' && text[count]!='\n') {
    mk61_service_ui_glyph g;
    if(!help_glyph(pico_view_services,(uint8_t)text[count],&g)) return NULL;
    if(width+g.advance>PICO_VIEW_WIDTH) break;
    if(text[count]==' ') space=count;
    width+=g.advance;++count;
  }
  *take=count;
  if(text[count] && text[count]!=' ' && text[count]!='\r' && text[count]!='\n' && space) {
    *take=count=space;
  }
  while(*take && text[*take-1]==' ') --*take;
  return skip_separators(text+count);
}

static const char* pico_draw_page(const char* text) {
  uint32_t row;
  text=skip_separators(text);help_clear();
  if(!help_draw_header(pico_view_services,"REPLY")) return NULL;
  for(row=0;row<PICO_VIEW_ROWS && *text;++row) {
    char line[PICO_VIEW_WIDTH+1];uint32_t take,index;
    const char* next=pico_wrap(text,&take);
    if(!next || next==text || take>PICO_VIEW_WIDTH) return NULL;
    for(index=0;index<take;++index) line[index]=text[index];
    line[take]=0;
    if(!help_draw_text(pico_view_services,PICO_VIEW_LEFT,
         PICO_VIEW_TOP+row*PICO_VIEW_PITCH+PICO_VIEW_ASCENT,line)) return NULL;
    text=next;
  }
  if(!help_draw_centered(pico_view_services,316,*text?"ENTER: MORE   ESC: EXIT":"ENTER: TYPE   ESC: EXIT") ||
     !mk61_api->graphics_present(help_frame,HELP_FRAME_BYTES)) return NULL;
  return text;
}

static int pico_editor_position(const mk61_service_edit_key* editor,uint32_t at,
                                uint32_t* column,uint32_t* row,uint32_t* advance) {
  uint32_t index,pen=0,line=0;
  for(index=0;index<=at;++index) {
    mk61_service_ui_glyph g;
    if(!help_glyph(pico_view_services,index<editor->length?(uint8_t)editor->source[index]:' ',&g)) return 0;
    if(pen+g.advance>PICO_VIEW_WIDTH) {pen=0;++line;}
    if(index==at) {*column=pen;*row=line;*advance=g.advance;return 1;}
    pen+=g.advance;
  }
  return 0;
}

static int pico_draw_editor(mk61_service_edit_key* editor) {
  uint32_t cursor=editor->cursor,caret_x,caret_row,caret_width;
  uint32_t index,pen=0,line=0,first;
  if(editor->sms_active && cursor) --cursor;
  if(!pico_editor_position(editor,cursor,&caret_x,&caret_row,&caret_width)) return 0;
  first=caret_row>=PICO_VIEW_ROWS?caret_row-PICO_VIEW_ROWS+1:0;
  help_clear();
  if(!help_draw_header(pico_view_services,"YOU")) return 0;
  for(index=0;index<editor->length;++index) {
    mk61_service_ui_glyph g;char ch[2]={editor->source[index],0};
    if(!help_glyph(pico_view_services,(uint8_t)ch[0],&g)) return 0;
    if(pen+g.advance>PICO_VIEW_WIDTH) {pen=0;++line;}
    if(line>=first && line<first+PICO_VIEW_ROWS &&
       !help_draw_text(pico_view_services,PICO_VIEW_LEFT+pen,
          PICO_VIEW_TOP+(line-first)*PICO_VIEW_PITCH+PICO_VIEW_ASCENT,ch)) return 0;
    pen+=g.advance;
  }
  help_horizontal_line(PICO_VIEW_LEFT+caret_x,
      PICO_VIEW_TOP+(caret_row-first)*PICO_VIEW_PITCH+19,caret_width);
  if(!help_draw_centered(pico_view_services,316,"ENTER: SEND   ESC: EXIT")) return 0;
  return mk61_api->graphics_present(help_frame,HELP_FRAME_BYTES)!=0;
}
