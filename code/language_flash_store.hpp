#ifndef MK61_LANGUAGE_FLASH_STORE_HPP
#define MK61_LANGUAGE_FLASH_STORE_HPP
#include "language_vm_abi.hpp"
#include "language_flash_program.hpp"
#include "language_flash_cache.hpp"
#include "program_store.hpp"
#include "storage_path.hpp"
#include "crc32.hpp"
#include <stdio.h>
#include <new>

namespace language_vm { namespace flash {
// Resident-owned C9 adapter. Every logical file is a directory of 1 KiB raw
// chunks, so neither inode lengths nor APP/USB buffers limit program size.
// The manifest is the only publication point. Failed builds use the other
// bank; a reset cannot make an unfinished image executable.
class Store {
  using Type=program_store::ProgramType;
  static constexpr uint16_t INVALID=program_store::INVALID_ID;
  uint16_t* source_;
  uint16_t source_id_=INVALID,parent_=INVALID,root_=INVALID,dirs_[4]={INVALID,INVALID,INVALID,INVALID};
  uint32_t fingerprint_,stamp_=0,size_=0;
  uint8_t bank_=0;
  bool opened_=false,building_=false,committed_=false;
  bool (*service_)();
  uint8_t* cache_;
  ReadCache* shared_cache_;
#if !defined(ARDUINO_ARCH_STM32)
  uint8_t fallback_[WRITE_BYTES];
#endif
  uint32_t cached_=UINT32_MAX,cache_revision_=0;
  Space cached_space_=IMAGE;
  static bool find(uint16_t parent,bool directory,Type type,const char* name,uint16_t& id) {
    id=INVALID;
    // C9 reports a successful search with INVALID when no child exists.
    return program_store::fat_find_child(parent,directory,type,name,id) && id!=INVALID;
  }
  bool directory(uint16_t parent,const char* name,uint16_t& id) {
    return find(parent,true,Type::TEXT,name,id) ||
        program_store::create_directory(parent,name,INVALID,&id);
  }
  static void name(uint32_t chunk,char* out) {snprintf(out,16,"%08lX",(unsigned long)chunk);}
  static bool page(const program_store::Entry& entry) {
    if(entry.kind!=program_store::NodeKind::FILE || entry.type!=Type::MK61_BINARY ||
       entry.data_len!=WRITE_BYTES || strlen(entry.name)!=8)return false;
    for(unsigned i=0;i<8;++i)if(!((entry.name[i]>='0' && entry.name[i]<='9') ||
        (entry.name[i]>='A' && entry.name[i]<='F')))return false;
    return true;
  }
  bool owned_cache(uint16_t id) {
    const int count=program_store::child_count(id);
    for(int i=0;i<count;++i) {
      program_store::Entry entry;
      if(!program_store::child(id,i,entry))return false;
      if(entry.kind==program_store::NodeKind::FILE) {
        if(entry.type!=Type::MK61_BINARY || !((!strcmp(entry.name,"Manifest") && entry.data_len==64) ||
            (!strcmp(entry.name,"Owner") && entry.data_len==16)))return false;
      } else {
        if(entry.kind!=program_store::NodeKind::DIRECTORY ||
           (strcmp(entry.name,"IndexA") && strcmp(entry.name,"IndexB") && strcmp(entry.name,"Image0") &&
            strcmp(entry.name,"Image1") && strcmp(entry.name,"Boundaries")))return false;
        const int pages=program_store::child_count(entry.id);
        for(int j=0;j<pages;++j) {program_store::Entry child;if(!program_store::child(entry.id,j,child) || !page(child))return false;}
        if(pages<0)return false;
      }
    }
    return count>=0;
  }
  bool erase(uint16_t id) {
    if(id==INVALID)return true;
    while(program_store::child_count(id)>0) {
      program_store::Entry entry;
      if(!program_store::child(id,0,entry) || !page(entry) || !program_store::remove_id(entry.id))return false;
      if(service_ && !service_())return false;
    }
    return program_store::child_count(id)==0;
  }
  bool root() {
    if(opened_)return true;
    if(!source_ || (*source_!=INVALID && !program_store::content_stamp(*source_,stamp_)))return false;
    source_id_=*source_;
    if(storage_path::create_directory(program_store::ROOT_ID,"/System/VMCache/Pages",true,parent_)!=storage_path::Status::OK)return false;
    char source_name[16];snprintf(source_name,sizeof(source_name),"%04X",unsigned(*source_));
    if(!directory(parent_,source_name,root_))return false;
    opened_=true;return true;
  }
  bool begin() {
    if(building_)return true;
    if(!root())return false;
    uint16_t owner=INVALID;uint8_t marker[16]={};
    memcpy(marker,"LFW1",4);word(marker+4,source_id_);dword(marker+12,mk61_crc32::calculate(marker,12));
    if(!find(root_,false,Type::MK61_BINARY,"Owner",owner) &&
       !program_store::write_file(root_,INVALID,Type::MK61_BINARY,"Owner",marker,sizeof(marker)))return false;
    // An invalid/stale manifest still identifies which bank must survive a
    // failed recompile. Never overwrite that bank before publication.
    uint16_t manifest;uint8_t old[64];uint16_t n=0;
    if(find(root_,false,Type::MK61_BINARY,"Manifest",manifest) &&
       program_store::read_source_range_id(manifest,0,old,sizeof(old),&n) && n==sizeof(old) &&
       !memcmp(old,"LFP1",4) && old[4]<2)bank_=uint8_t(1-old[4]);
    // A source/compiler change already invalidated this derived image.
    // Reclaim it before building, so an unusable cache cannot consume the
    // capacity needed by the new program. User source files are untouched.
    if(n==sizeof(old) && !memcmp(old,"LFP1",4) && old[4]<2 &&
       mk61_crc32::calculate(old,60)==dword(old+60) &&
       (dword(old+8)!=stamp_ || dword(old+12)!=fingerprint_)) {
      uint16_t stale;
      if(find(root_,true,Type::TEXT,old[4]?"Image1":"Image0",stale) && !erase(stale))return false;
    }
    const char* names[]={"IndexA","IndexB",bank_?"Image1":"Image0","Boundaries"};
    for(unsigned i=0;i<4;++i)if(!directory(root_,names[i],dirs_[i]) || !erase(dirs_[i]))return false;
    building_=true;cached_=UINT32_MAX;return true;
  }
  bool evict_cache() {
    // Only positively identified generated caches are candidates. Scratch
    // and the active source's bank remain pinned through publication.
    uint16_t victim=INVALID;
    const int count=program_store::child_count(parent_);
    for(int i=0;i<count;++i) {
      program_store::Entry entry;uint16_t file,copied=0,source=INVALID;uint8_t m[64];bool identified=false;
      if(!program_store::child(parent_,i,entry))return false;
      if(entry.kind!=program_store::NodeKind::DIRECTORY || entry.id==root_)continue;
      if(find(entry.id,false,Type::MK61_BINARY,"Manifest",file) &&
         program_store::read_source_range_id(file,0,m,sizeof(m),&copied) && copied==sizeof(m) &&
         !memcmp(m,"LFP1",4) && m[4]<2 && mk61_crc32::calculate(m,60)==dword(m+60)) {source=word(m+6);identified=true;}
      else if(find(entry.id,false,Type::MK61_BINARY,"Owner",file) &&
         program_store::read_source_range_id(file,0,m,16,&copied) && copied==16 &&
         !memcmp(m,"LFW1",4) && mk61_crc32::calculate(m,12)==dword(m+12)) {source=word(m+4);identified=true;}
      // FFFF identifies an unsaved draft, too. A verified owner marker
      // makes its interrupted build just as reclaimable as a saved file.
      if(!identified)continue;
      char expected[16];snprintf(expected,sizeof(expected),"%04X",unsigned(source));
      if(!strcmp(expected,entry.name) && owned_cache(entry.id))victim=entry.id;
    }
    return victim!=INVALID && program_store::remove_tree(victim);
  }
  bool read(Space space,uint32_t at,uint8_t* out,uint16_t n) {
    if(!cache_ || space>BOUNDARIES || dirs_[space]==INVALID)return false;
    while(n) {
      const uint32_t chunk=at/WRITE_BYTES;
      const uint32_t revision=program_store::media_revision();
      if(cached_!=chunk || cached_space_!=space || cache_revision_!=revision) {
        if(!shared_cache_ || !shared_cache_->get(revision,dirs_[space],chunk,cache_)) {
          char text[16];name(chunk,text);uint16_t file,copied=0;
          if(!find(dirs_[space],false,Type::MK61_BINARY,text,file) ||
             !program_store::read_source_range_id(file,0,cache_,WRITE_BYTES,&copied) || copied!=WRITE_BYTES)return false;
          if(shared_cache_)shared_cache_->put(revision,dirs_[space],chunk,cache_);
        }
        cached_=chunk;cached_space_=space;cache_revision_=revision;
      }
      unsigned count=WRITE_BYTES-at%WRITE_BYTES;if(count>n)count=n;
      memcpy(out,cache_+at%WRITE_BYTES,count);out+=count;at+=count;n=uint16_t(n-count);
    }
    return true;
  }
  bool write(Space space,uint32_t at,const uint8_t* in,uint16_t n) {
    if(space>BOUNDARIES || at%WRITE_BYTES || n!=WRITE_BYTES || !begin())return false;
    char text[16];name(at/WRITE_BYTES,text);uint16_t file=INVALID;
    (void)find(dirs_[space],false,Type::MK61_BINARY,text,file);
    while(!program_store::write_file(dirs_[space],file,Type::MK61_BINARY,text,in,n)) {
      if(program_store::last_write_failure()!=program_store::WriteFailure::RECORD || !evict_cache())return false;
      if(service_ && !service_())return false;
    }
    cached_=UINT32_MAX;return true;
  }
  bool truncate(Space space,uint32_t n) {
    if(n || space>BOUNDARIES)return false;
    if(space==BOUNDARIES && !building_) {
      if(!root() || !directory(root_,"Boundaries",dirs_[space]))return false;
    } else if(!begin())return false;
    cached_=UINT32_MAX;return erase(dirs_[space]);
  }
  bool lookup(uint32_t key,bool by_number,uint32_t* result) {
    uint8_t header[32],record[8];
    if(!result || !read(IMAGE,0,header,sizeof(header)))return false;
    uint32_t low=0,high=word(header+18);
    while(low<high) {
      const uint32_t mid=low+(high-low)/2;
      if(!read(IMAGE,32+mid*8,record,sizeof(record)))return false;
      const uint32_t found=dword(record+(by_number?0:4));
      if(by_number && found==key){*result=dword(record+4);return true;}
      if(by_number?found<key:found<=key)low=mid+1;else high=mid;
    }
    *result=by_number?UINT32_MAX:0;
    if(!by_number && low) {
      if(!read(IMAGE,32+(low-1)*8,record,sizeof(record)))return false;
      *result=dword(record);
    }
    return true;
  }
public:
  Store(uint16_t* source,uint32_t fingerprint,bool (*service)()=nullptr,uint8_t* cache=nullptr,ReadCache* shared_cache=nullptr)
      :source_(source),fingerprint_(fingerprint),service_(service),cache_(cache),shared_cache_(shared_cache) {
#if !defined(ARDUINO_ARCH_STM32)
    if(!cache_)cache_=fallback_;
#endif
  }
  // WORKSPACE owner changes can clear the borrowed page. Its metadata stays
  // resident; invalidate before the first read under the new owner.
  void invalidate(){cached_=UINT32_MAX;}
  Store(const Store&)=delete;
  ~Store() {
    // Best-effort rollback/temporary cleanup. Committed chunks and the old
    // manifest remain valid even when removal itself runs out of journal.
    if(opened_) {
      (void)erase(dirs_[INDEX_A]);(void)erase(dirs_[INDEX_B]);(void)erase(dirs_[BOUNDARIES]);
      if(building_ && !committed_)(void)erase(dirs_[IMAGE]);
    }
  }
  uint32_t source_stamp() const {return stamp_;}
  IO io() {
    return {this,[](void* raw,Space s,uint32_t at,uint8_t* out,uint16_t n){return static_cast<Store*>(raw)->read(s,at,out,n);},
      [](void* raw,Space s,uint32_t at,const uint8_t* in,uint16_t n){return static_cast<Store*>(raw)->write(s,at,in,n);},
      [](void* raw,Space s,uint32_t n){return static_cast<Store*>(raw)->truncate(s,n);},
      [](void* raw){auto& s=*static_cast<Store*>(raw);return !s.service_ || s.service_();},
      [](void*,void* program,uint8_t operation){auto& p=*static_cast<Program*>(program);return operation==0x80?p.optimize():p.prepare_index(Language(operation));},
      [](void* raw,uint32_t key,bool number,uint32_t* result){return static_cast<Store*>(raw)->lookup(key,number,result);}};
  }
  Input input(uint32_t size) {
    size_=size;
    return {this,[](void* raw,uint32_t at,uint8_t* out,uint16_t n) {
      auto& s=*static_cast<Store*>(raw);
      return at<=s.size_ && n<=s.size_-at && s.read(IMAGE,at,out,n);
    },size};
  }
  bool load(ValidatedImage& certificate) {
    ReadCache::Image cached;
    if(shared_cache_ && source_ && *source_!=INVALID &&
       shared_cache_->image(program_store::media_revision(),*source_,fingerprint_,cached)) {
      source_id_=*source_;stamp_=cached.stamp;parent_=cached.parent;root_=cached.root;
      dirs_[IMAGE]=cached.directory;bank_=cached.bank;opened_=true;
      certificate=cached.validated;size_=certificate.size;return true;
    }
    if(!root())return false;
    uint16_t file,copied=0;uint8_t m[64];
    if(!find(root_,false,Type::MK61_BINARY,"Manifest",file) ||
       !program_store::read_source_range_id(file,0,m,sizeof(m),&copied) || copied!=sizeof(m) ||
       memcmp(m,"LFP1",4) || m[4]>1 || m[5]!=14 || word(m+6)!=source_id_ ||
       dword(m+8)!=stamp_ || dword(m+12)!=fingerprint_ ||
       mk61_crc32::calculate(m,60)!=dword(m+60))return false;
    bank_=m[4];
    if(!find(root_,true,Type::TEXT,bank_?"Image1":"Image0",dirs_[IMAGE]))return false;
    uint8_t h[32];
    if(!read(IMAGE,0,h,sizeof(h)) || memcmp(h,m+16,sizeof(h)) || memcmp(h,"LBV2",4) || h[4]!=14)return false;
    size_=dword(h+8);
    certificate={VALIDATED_MAGIC,size_,dword(h+12),word(h+16),dword(h+28),word(h+18),h[6],h[7],Language(h[5]),true};
    if(shared_cache_)shared_cache_->remember_image(program_store::media_revision(),
        {fingerprint_,stamp_,0,source_id_,parent_,root_,dirs_[IMAGE],bank_,certificate});
    return true;
  }
  bool publish(const ValidatedImage& certificate) {
    if(!building_ || !certificate.wide || certificate.size!=size_)return false;
    uint32_t current;
    if(!program_store::content_stamp(source_id_,current) || current!=stamp_)return false;
    uint8_t m[64]={};memcpy(m,"LFP1",4);m[4]=bank_;m[5]=14;word(m+6,source_id_);
    dword(m+8,stamp_);dword(m+12,fingerprint_);
    if(!read(IMAGE,0,m+16,32))return false;
    dword(m+60,mk61_crc32::calculate(m,60));uint16_t file=INVALID;
    (void)find(root_,false,Type::MK61_BINARY,"Manifest",file);
    if(!program_store::write_file(root_,file,Type::MK61_BINARY,"Manifest",m,sizeof(m)))return false;
    committed_=true;
    // The superseded bank is only a cache. Reclaim it after atomic publish.
    uint16_t previous;
    if(find(root_,true,Type::TEXT,bank_?"Image0":"Image1",previous))(void)erase(previous);
    return true;
  }
};
#if defined(ARDUINO_ARCH_STM32)
static_assert(sizeof(Store)<256,"resident Flash metadata must remain small");
#endif
}}
#endif
