#ifndef MK61_LANGUAGE_SOURCE_FILE_HPP
#define MK61_LANGUAGE_SOURCE_FILE_HPP
#include "language_source_document.hpp"
#include "focal_text.hpp"
#include "focal_source.hpp"
#include <new>

namespace language_vm { namespace source {
struct File {
  uint16_t id,size;
  uint32_t revision;
  bool catalog=false;
  bool stable=false;
  bool pin() {stable=portable_system::call(MK61_SYS_RESOURCE_READ,6,id,0,&revision)!=0;return stable;}
  static bool read(void* raw,uint16_t at,uint8_t* out,uint16_t n) {
    const auto& f=*static_cast<File*>(raw);
    if(at>f.size || n>unsigned(f.size-at))return false;
    const mk61_service_resource request={f.revision,f.id,at,out,n,u16(f.stable?2:f.catalog?1:0)};
    return portable_system::call(MK61_SYS_RESOURCE_READ,5,0,0,(void*)&request)!=0;
  }
  Input input() {return {this,read,size};}
};
inline DraftIO draft_io() {
  return {nullptr,
    [](void*,uint32_t* index,uint16_t capacity) {
      if(!program_store::vfat_stage_lock(true))return false;
      // Remove only abandoned editor pages. A pending USB or terminal
      // transaction must never be discarded to start an editor session.
      program_store::vfat_stage_forget(DRAFT_FIRST_KEY,DRAFT_PAGES*2);
      if(program_store::vfat_stage_count()) {program_store::vfat_stage_unlock();return false;}
      if(!program_store::vfat_stage_narrow_matching(
          [](void*,u32){return true;},nullptr,index,capacity)) {
        program_store::vfat_stage_unlock();return false;
      }
      return true;
    },
    [](void*,uint32_t key,uint8_t* out){return program_store::vfat_stage_read(key,out);},
    [](void*,uint32_t key,const uint8_t* in){return program_store::vfat_stage_write(key,in);},
    [](void*,uint32_t key,uint16_t count){
      program_store::vfat_stage_forget(key,count);
      for(unsigned i=0;i<count;++i)if(program_store::vfat_stage_exists(key+i))return false;
      return true;
    },
    [](void*){program_store::vfat_stage_unlock();}
  };
}
inline bool write(Input input,program_store::ProgramType type,uint16_t parent,
                 uint16_t previous,const char* name,uint16_t& id) {
  const program_store::FileSource source={&input,
    [](void* raw,u32 offset,u8* out,usize size){
      const auto& in=*static_cast<Input*>(raw);
      return offset<=in.size && size<=in.size-offset && in.read(in.context,u16(offset),out,u16(size));
    }};
  return program_store::write_file_from_source(parent,previous,type,name,input.size,source,
                                               nullptr,0,&id);
}
inline bool save(Document& document,program_store::ProgramType type,uint16_t parent,
                 uint16_t previous,const char* name,uint16_t& id) {
  auto input=document.input();
  if(type==program_store::ProgramType::FOCAL) {
    Reader source(input);focal_text::CompactSource compact(source);
    return compact.good() && write(compact.input(),type,parent,previous,name,id);
  }
  return write(input,type,parent,previous,name,id);
}
inline unsigned focal_cursor(const char* text,unsigned length,unsigned cursor,bool expand,const focal_text::InitialLine* initial=nullptr) {
  int change=0;
  focal_text::visit(text,length,[&](focal_text::Token t){
    if(t.begin>=cursor)return false;
    char short_name[2];
    const unsigned n=strlen(focal_text::spelling(t.command,expand,short_name));
    change+=int(n)-int(t.end-t.begin);
    if(cursor<t.end)change+=int(t.end-cursor);
    return t.end<cursor;
  },initial);
  return unsigned(int(cursor)+change);
}
// FOCAL's compact file spelling and expanded operator-key view share a single
// bounded window. Folding happens before paging, validation and persistence.
inline bool fold_focal(Document& document,text_editor::Buffer& editor,const focal_text::InitialLine* initial=nullptr) {
  const unsigned cursor=focal_cursor(editor.source,editor.len,editor.cursor,false,initial);
  const unsigned top=focal_cursor(editor.source,editor.len,editor.view_top,false,initial);
  if(!focal_text::transform(editor.source,Document::WINDOW_SIZE+1,false,initial))return false;
  const u16 length=u16(strlen(editor.source));
  if(!document.fits(length))return false;
  memcpy(document.window,editor.source,length+1);
  editor.source=document.window;editor.len=length;editor.cursor=u16(cursor);
  editor.view_top=u16(top);
  return document.accept(editor.len);
}
inline bool expand_focal(Document& document,text_editor::Buffer& editor,char* view,const focal_text::InitialLine* initial=nullptr) {
  const unsigned cursor=focal_cursor(document.window,editor.len,editor.cursor,true,initial);
  const unsigned top=focal_cursor(document.window,editor.len,editor.view_top,true,initial);
  if(!focal_text::editor_copy(document.window,view,Document::WINDOW_SIZE+1,initial))return false;
  editor.source=view;editor.len=u16(strlen(view));editor.cursor=u16(cursor);editor.view_top=u16(top);
  editor.capacity=Document::WINDOW_SIZE+1;
  return true;
}
}}
#endif
