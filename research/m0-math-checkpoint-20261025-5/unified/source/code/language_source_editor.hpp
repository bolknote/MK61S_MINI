#ifndef MK61_LANGUAGE_SOURCE_EDITOR_HPP
#define MK61_LANGUAGE_SOURCE_EDITOR_HPP
#include "language_bytecode.hpp"
#include "language_source_file.hpp"
#include "focal_editor.hpp"
namespace language_vm { namespace source {
inline uint16_t line_start(Reader& source,unsigned at) {
  while(at && source.at(uint16_t(at-1))!='\n' && source.at(uint16_t(at-1))!='\r')--at;
  return uint16_t(at);
}
inline unsigned after_separator(Reader& source,unsigned at) {
  if(at<source.size()) {
    const char ch=source.at(uint16_t(at++));
    if(at<source.size() && (ch=='\n'||ch=='\r') &&
       (source.at(uint16_t(at))=='\n'||source.at(uint16_t(at))=='\r') && source.at(uint16_t(at))!=ch)++at;
  }
  return at;
}
inline bool line_key(Document& document,text_editor::Buffer& editor,bool clear,int delta) {
  Reader source(document.input());
  const unsigned cursor=document.start()+editor.cursor;
  unsigned begin=line_start(source,cursor),end=begin+source.line_end(begin,source.size());
  if(clear) {
    if(begin==end) {
      if(end<source.size())end=after_separator(source,end);
      else if(begin) {
        --begin;
        if(begin && source.at(uint16_t(begin-1))!=source.at(uint16_t(begin)) &&
           (source.at(uint16_t(begin-1))=='\r'||source.at(uint16_t(begin-1))=='\n'))--begin;
      }
    }
    return source.good() && document.erase(uint16_t(begin),uint16_t(end),editor);
  }
  const unsigned column=cursor-begin;
  if(delta>0) {
    begin=after_separator(source,end);
    end=begin+source.line_end(begin,source.size());
  } else if(begin) {
    end=begin-1;
    if(end && source.at(uint16_t(end-1))!=source.at(uint16_t(end)) &&
       (source.at(uint16_t(end-1))=='\r'||source.at(uint16_t(end-1))=='\n'))--end;
    begin=line_start(source,end);
  }
  unsigned next=begin+column;if(next>end)next=end;
  return source.good() && document.seek(editor,uint16_t(next));
}
template <Language Lang>
bool edit(File file,void* workspace,char* name,uint16_t parent,uint16_t previous,
          uint16_t initial_cursor,uint16_t& saved,bool (*confirm)(),
          bool (*error)(const char*),
          text_editor::KeyResult (*key)(text_editor::Buffer&,const char*,i32,u32)) {
  constexpr bool focal=Lang==Language::FOCAL;
  constexpr auto type=focal?program_store::ProgramType::FOCAL:program_store::ProgramType::TINYBASIC;
  file.catalog=true;file.revision=portable_system::call(MK61_SYS_RESOURCE_READ,4);
  auto& document=*new(workspace) Document(file.input(),draft_io(),focal?256:768);
  struct Scope {Document& document;~Scope(){document.~Document();}}scope{document};
  if(!document.open())return error("BUSY");
  text_editor::Buffer editor{};
  if(!document.seek(editor,initial_cursor))return error("I/O?");
  char* view=reinterpret_cast<char*>(workspace)+sizeof(Document);
  text_editor::DisplaySession display(main_lcd());
  bool dirty=true;
  u32 display_revision=main_lcd().displayModeRevision();
  u32 context_generation=UINT32_MAX;focal_editor::Context context{};
  while(true) {
    idle_main_process();
    if(portable_system::call(MK61_SYS_RESOURCE_READ,4)!=file.revision)return error("SOURCE CHANGED");
    if(display_revision!=main_lcd().displayModeRevision()) {display_revision=main_lcd().displayModeRevision();dirty=true;}
    if(!document.prepare(editor))return error("I/O?");
    const u16 original_cursor=editor.cursor,original_top=editor.view_top;
    if constexpr(focal) {
      if(context_generation!=document.generation()) {
        Reader input(document.input());CursorScope cursor_scope(input);
        context.initial=focal_text::initial_line(Cursor(input),document.start());
        if(!input.good())return error("I/O?");
        context_generation=document.generation();
      }
      if(!expand_focal(document,editor,view,&context.initial))return error("FULL?");
      context.field=focal_editor::context_field(editor.source,editor.cursor,context.initial);
      context.macro_blocked=focal_editor::context_literal(editor.source,editor.cursor,context.initial);
    }
    const u32 now=millis();
    if(editor.sms.active && text_editor::time_reached(now,editor.sms.deadline_ms)) {text_editor::sms_reset(editor.sms);dirty=true;}
    if(dirty) {
      text_editor::ensure_cursor_visible(main_lcd(),editor.source,editor.len,editor.cursor,editor.view_top);
      text_editor::draw(main_lcd(),editor.source,editor.len,editor.cursor,editor.view_top,editor.sms.active);
    }
    kbd::scan();const i32 code=kbd::get_key(key_state::PRESSED);
    if(code<0) {
      if constexpr(focal) {if(!fold_focal(document,editor,&context.initial))return error("FULL?");}
      main_lcd().flush();delay(1);continue;
    }
    if(code==KEY_CX && kbd::is_key_pressed(KEY_ALPHA))editor.shift=text_editor::Shift::ALPHA;
    if((code==KEY_LEFT || code==KEY_LEFT_PRESS) &&
       (editor.shift==text_editor::Shift::ALPHA || kbd::is_key_pressed(KEY_ALPHA))) {
      text_editor::sms_reset(editor.sms);editor.shift=text_editor::Shift::NONE;dirty=true;
      if constexpr(focal) {if(!fold_focal(document,editor,&context.initial))return error("FULL?");}
      continue;
    }
    const bool clear=code==KEY_CX && editor.shift==text_editor::Shift::ALPHA;
    const bool vertical=editor.shift==text_editor::Shift::NONE &&
        (code==KEY_SHG_LEFT_PRESS || code==KEY_SHG_RIGHT_PRESS);
    if(clear || vertical) {
      if constexpr(focal) {if(!fold_focal(document,editor,&context.initial))return error("FULL?");}
      if(!document.accept(editor.len) || !line_key(document,editor,clear,code==KEY_SHG_LEFT_PRESS?-1:1))return error("I/O?");
      editor.shift=text_editor::Shift::NONE;text_editor::sms_reset(editor.sms);dirty=true;continue;
    }
    const auto result=[&]() {
      if constexpr(focal)return focal_editor::handle(editor,"\n",code,now,&context);
      else return key(editor,"\n",code,now);
    }();
    dirty=result!=text_editor::KeyResult::NONE;
    if constexpr(focal) {
      if(!fold_focal(document,editor,&context.initial)) {
        editor.source=document.window;editor.len=document.used();
        editor.cursor=original_cursor;editor.view_top=original_top;
        editor.shift=text_editor::Shift::NONE;text_editor::sms_reset(editor.sms);
        dirty=true;continue;
      }
    }
    if(!document.accept(editor.len))return error("FULL?");
    if(result!=text_editor::KeyResult::SAVE)continue;
    kbd::handoff(kbd::Event(code));main_lcd().cursorOff();
    if(!confirm())return false;
    if(!program_store_choose_save_target(type,parent,name,program_store::NAME_SIZE,parent)) {dirty=true;continue;}
    if(save(document,type,parent,previous,name,saved))return true;
    (void)error("I/O?");delay(700);dirty=true;
  }
}
}}
#endif
