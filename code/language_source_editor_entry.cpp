#if defined(MK61_BUILD_SOURCE_EDITOR_MODULE)
#include "language_source_editor.hpp"
#include "mk8_literal.hpp"
#include "language_compiler_flow.hpp"
#include "focal_editor.hpp"
#include "mk61_app.h"
#include <stdio.h>
namespace {
using namespace language_vm;
Language language;
bool message(const char* error) {
  const char* rows[]={error,language==Language::BASIC?"TinyBASIC":"FOCAL"};
  portable_system::text_rows(rows,2);return false;
}
bool confirm() {
  const bool ru=library_mk61::language_is_ru();
  const char* rows[]={ru?M8("Сохранить?"):language==Language::BASIC?"Save TinyBASIC?":"Save FOCAL?",
                       ru?M8("OK=да ESC=нет"):"OK=yes ESC=no"};
  portable_system::text_rows(rows,2);
  for(;;) {
    const auto key=kbd::get_key_wait();
    if(key==KEY_OK || key==KEY_OK_PRESS)return true;
    if(key==KEY_ESC || key==KEY_ESC_PRESS)return false;
  }
}
text_editor::KeyResult basic_key(text_editor::Buffer& editor,const char* enter,i32 key,u32 now) {
  return text_editor::portable_handle_default_key(editor,enter,key,now);
}
uint32_t edit(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow) || flow->context_size!=sizeof(CompilerContext) ||
     flow->current.phase!=FLOW_EDIT_SOURCE)return 0;
  auto& c=*static_cast<CompilerContext*>(flow->context);
  if(c.prepared || c.compile.magic!=FLOW_CONTEXT_MAGIC || !c.compile.values ||
     (c.language!=Language::BASIC && c.language!=Language::FOCAL))return 0;
  auto& request=c.compile.request;
  if(!compatible(&request) || request.edit_requested!=1)return 0;
  language=c.language;
  constexpr unsigned bytes=sizeof(source::Document)+source::Document::WINDOW_SIZE+1;
  static_assert(bytes<=COMPILER_WORKSPACE_SIZE,"source editor must retain all VM values");
  // This ordinary APP borrows the active language's compiler prefix.
  // APPLICATION ownership cannot replace a protected VM transaction; the
  // optional file-cache owner is also unavailable in cache-free builds.
  struct Workspace {
    mk61_service_lease lease={};
    Workspace(u32 size,u32 kind) {
      lease.image_crc=portable_system::image_crc;
      (void)portable_system::call(MK61_SERVICE_MEMORY_ACQUIRE,0,kind,size,&lease);
    }
    ~Workspace() {if(lease.data)(void)portable_system::call(MK61_SERVICE_MEMORY_RELEASE,0,0,0,&lease);}
  } memory(bytes,language==Language::BASIC?MK61_APP_KIND_TINYBASIC:MK61_APP_KIND_FOCAL);
  if(!memory.lease.data || memory.lease.size<bytes) {mk61_app_flow_exit(flow,0,MK61_FLOW_BUSY);return 1;}
  if(portable_system::call(MK61_SERVICE_CAPABILITIES)&MK61_SERVICE_CAP_TEXT_FONT)
    (void)portable_system::call(MK61_SYS_TEXT_FONT,MK61_SYS_TEXT_FONT_ACTIVATE);
  const bool fresh=request.source_id==0xFFFF;
  program_store::Entry entry={};
  if(!fresh && (!program_store::entry_by_id(request.source_id,entry) ||
     entry.kind!=program_store::NodeKind::FILE ||
     entry.type!=(language==Language::BASIC?program_store::ProgramType::TINYBASIC:program_store::ProgramType::FOCAL))) {
    mk61_app_flow_exit(flow,0,MK61_FLOW_IO_ERROR);return 1;
  }
  char name[program_store::NAME_SIZE];
  if(fresh)snprintf(name,sizeof(name),"%s0",language==Language::BASIC?"TINY":"FOCAL");
  else memcpy(name,entry.name,sizeof(name));
  source::File file={request.source_id,fresh?u16(0):entry.data_len,0};
  uint16_t saved=0xFFFF;
  const bool success=language==Language::BASIC
      ? source::edit<Language::BASIC>(file,memory.lease.data,name,u16(request.compiled.line),request.source_id,
          request.compiled.source_offset,saved,confirm,message,basic_key)
      : source::edit<Language::FOCAL>(file,memory.lease.data,name,u16(request.compiled.line),request.source_id,
          request.compiled.source_offset,saved,confirm,message,basic_key);
  if(success) {
    c.compile.values->selected[language==Language::BASIC?0:1]=saved;
    request.source_id=saved;
    const char* rows[]={library_mk61::language_is_ru()?M8("Сохранено"):"Saved",name};
    portable_system::text_rows(rows,2);delay(700);
  }
  mk61_app_flow_exit(flow,1,MK61_FLOW_OK);return 1;
}
}
extern "C" u32 mk61_app_initialize(const mk61_app_api* api,u32 crc,u32 kind) {
  return portable_system::bind(api,crc,kind)?0:MK61_APP_RUNTIME_ERROR;
}
extern "C" u32 mk61_app_command(u32 command,u32 argument0,u32,u32,u32) {
  if(command==MK61_APP_FLOW_INFO)return MK61_APP_FLOW_MAGIC;
  if(command==MK61_APP_FLOW_STEP)return edit(reinterpret_cast<mk61_app_flow*>(argument0));
  return 0;
}
#endif
