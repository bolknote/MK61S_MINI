#include "language_cache.hpp"
#include "language_vm_image_cache.hpp"
#include "language_vm_file_cache.hpp"
#include "script.hpp"
#include "storage.hpp"
#include "crc32.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
extern "C" {
#include "ff.h"
}
#ifndef MK61_PICOCALC_BUILD_ID
#define MK61_PICOCALC_BUILD_ID 0x50434831U
#endif

namespace picocalc::language_cache {
namespace {
namespace vm=language_vm;
namespace disk=language_vm::file_cache;
using Cache=vm::ImageCache<32768,32,vm::CachePolicy::REUSE_DENSITY,true>;
static_assert(sizeof(Cache)<=32768,"Pico VM cache must fit the borrowed source tail");
Cache* memory=nullptr;
void* storage_owner=nullptr;
void* storage=nullptr;
unsigned storage_capacity=0;
unsigned pins=0;
bool discard_pending=false;
Statistics counts;
constexpr char DIRECTORY[]="/System/VMCache/Pico";
constexpr unsigned PREFIX=12,MAX_FILE=files::PATH_SIZE+vm::MAX_MODULE+256;
constexpr unsigned OWNER_BYTES=PREFIX+files::PATH_SIZE;

u16 word(const u8* p) { return (u16)(p[0]|(u16(p[1])<<8)); }
void word(u8* p,u16 n) { p[0]=(u8)n;p[1]=(u8)(n>>8); }
u32 dword(const u8* p) { return u32(p[0])|(u32(p[1])<<8)|(u32(p[2])<<16)|(u32(p[3])<<24); }
void dword(u8* p,u32 n) { for(unsigned i=0;i<4;++i) p[i]=(u8)(n>>(8*i)); }
u32 owner_crc(const u8* p,u16 n) {
    auto state=mk61_crc32::extend(mk61_crc32::INITIAL_STATE,p,8);
    return mk61_crc32::finish(mk61_crc32::extend(state,p+PREFIX,n+1));
}
bool cacheable(const vm::View& v) {
    return v.bytes && !v.reader && !v.wide && !v.expression && v.size<=vm::MAX_MODULE &&
        (!(v.bytes[7]&vm::RESOURCE_FLAG) || (v.bytes[7]&vm::OWNED_RESOURCE_FLAG));
}
bool identity(const char* path,char normalized[files::PATH_SIZE],u16& id) {
    program_store::Entry entry{};
    if(!script::normalize_path("/",path,normalized) || !script::register_file(normalized,entry) ||
       entry.kind!=program_store::NodeKind::FILE) return false;
    id=entry.id;return true;
}
disk::Key key(const char* path,vm::Language language,bool rf,const char* source,u16 length) {
    const auto hash=mk61_crc32::calculate((const u8*)path,std::strlen(path));
    return {MK61_PICOCALC_BUILD_ID^(rf?0x80000000U:0),
        mk61_crc32::calculate((const u8*)source,length),(u16)(hash%65535),length,language};
}
void filename(const char* path,vm::Language language,bool rf,char out[files::PATH_SIZE]) {
    std::snprintf(out,files::PATH_SIZE,"%s/%08lX-%u-%u.cache",DIRECTORY,
        (unsigned long)mk61_crc32::calculate((const u8*)path,std::strlen(path)),(unsigned)language,rf?1:0);
}
bool read_file(const char* path,u8* bytes,unsigned capacity,unsigned& used) {
    used=0;if(!files::ready()) return false;
    FIL file{};if(f_open(&file,path,FA_READ)!=FR_OK) return false;
    const auto size=f_size(&file);UINT got=0;
    const bool ok=size<=capacity && f_read(&file,bytes,(UINT)size,&got)==FR_OK && got==size;
    const auto closed=f_close(&file);if(ok && closed==FR_OK) used=got;
    return ok && closed==FR_OK;
}
bool envelope(const u8* bytes,unsigned size,const char*& path,u16& length,const u8*& file,u16& file_size,unsigned physical=0) {
    if(size<PREFIX || std::memcmp(bytes,"PCC1",4)) return false;
    length=word(bytes+4);file_size=word(bytes+6);
    if(!length || length>=files::PATH_SIZE || size<PREFIX+length+1U ||
       (physical?physical:size)!=PREFIX+length+1U+file_size ||
       bytes[PREFIX+length] || std::memchr(bytes+PREFIX,0,length) ||
       dword(bytes+8)!=owner_crc(bytes,length)) return false;
    path=(const char*)bytes+PREFIX;file=bytes+PREFIX+length+1;return true;
}
bool owned(const u8* bytes,unsigned size,unsigned physical) {
    const char* path;const u8* file;u16 n,used;
    if(!envelope(bytes,size,path,n,file,used,physical) || used<disk::PROBE_BYTES) return false;
    // The separately checked owner survives a damaged/interrupted payload.
    // Unknown files and hash collisions without this marker remain untouched.
    return path[0]=='/';
}
bool read_owner(const char* path,u8* bytes,unsigned& used,unsigned& size) {
    used=size=0;if(!files::ready()) return false;
    FIL file{};if(f_open(&file,path,FA_READ)!=FR_OK) return false;
    const auto total=f_size(&file);UINT got=0;
    const unsigned n=total<OWNER_BYTES?(unsigned)total:OWNER_BYTES;
    const bool ok=total<=MAX_FILE && f_read(&file,bytes,n,&got)==FR_OK && got==n;
    const auto closed=f_close(&file);
    if(ok && closed==FR_OK) { used=got;size=(unsigned)total;return true; }
    return false;
}
bool make_directory(const char* path) {
    FILINFO info{};
    const auto status=f_stat(path,&info);
    return status==FR_OK ? (info.fattrib&AM_DIR)!=0 : status==FR_NO_FILE && f_mkdir(path)==FR_OK;
}
bool room(const char* target,unsigned size,u8* scratch) {
    // Only positively identified generated entries are eligible for eviction.
    for(unsigned attempt=0;attempt<disk::MAX_FILES+1;++attempt) {
        DIR dir{};if(f_opendir(&dir,DIRECTORY)!=FR_OK) return false;
        unsigned count=0,total=0;char victim[files::PATH_SIZE]{};FILINFO info{};
        FRESULT status;
        while((status=f_readdir(&dir,&info))==FR_OK && info.fname[0]) {
            if(info.fattrib&AM_DIR) continue;
            char candidate[files::PATH_SIZE];
            const int n=std::snprintf(candidate,sizeof(candidate),"%s/%s",DIRECTORY,info.fname);
            if(n<0 || n>=(int)sizeof(candidate) || !std::strcmp(candidate,target)) continue;
            unsigned used=0,physical=0;
            if(!read_owner(candidate,scratch,used,physical) || !owned(scratch,used,physical)) continue;
            ++count;total+=(unsigned)info.fsize;
            if(!*victim) std::snprintf(victim,sizeof(victim),"%s",candidate);
        }
        const auto closed=f_closedir(&dir);
        if(status!=FR_OK || closed!=FR_OK) return false;
        if(count<disk::MAX_FILES && total+size<=disk::MAX_TOTAL_BYTES) return true;
        if(!*victim || f_unlink(victim)!=FR_OK) return false;
        ++counts.evictions;
    }
    return false;
}
void store(const char* path,bool rf,const char* source,u16 length,const vm::View& v) {
    if(!files::ready() || !cacheable(v)) return;
    // Cache writes use private FatFs transactions. They change no source
    // file and therefore do not invalidate the source/media revision. All
    // ordinary editor/terminal/USB writes still advance files::revision().
    if(!make_directory("/System") || !make_directory("/System/VMCache") || !make_directory(DIRECTORY)) return;
    u8 scratch[OWNER_BYTES];
    std::unique_ptr<u8[]> output(new(std::nothrow) u8[MAX_FILE]);
    if(!output) return;
    char target[files::PATH_SIZE];filename(path,v.language,rf,target);
    FILINFO info{};const auto exists=f_stat(target,&info);
    if(exists==FR_OK) {
        unsigned used=0,physical=0;const char* previous;const u8* file;u16 n,size;
        if(!read_owner(target,scratch,used,physical) || !owned(scratch,used,physical) ||
           !envelope(scratch,used,previous,n,file,size,physical) || std::strcmp(previous,path)) {
            ++counts.rejected;return;
        }
    } else if(exists!=FR_NO_FILE) return;
    const unsigned n=(unsigned)std::strlen(path),offset=PREFIX+n+1;
    u16 written=0;
    if(!disk::pack(key(path,v.language,rf,source,length),v.bytes,(u16)v.size,
                   output.get()+offset,(u16)(MAX_FILE-offset),written)) return;
    std::memcpy(output.get(),"PCC1",4);word(output.get()+4,(u16)n);word(output.get()+6,written);
    std::memcpy(output.get()+PREFIX,path,n+1);
    dword(output.get()+8,owner_crc(output.get(),(u16)n));
    const unsigned size=offset+written;
    if(!room(target,size,scratch)) return;
    char temporary[files::PATH_SIZE],backup[files::PATH_SIZE];
    FIL file{};bool created=false;
    for(unsigned i=0;i<100 && !created;++i) {
        std::snprintf(temporary,sizeof(temporary),"%s/.PCC-%u.tmp",DIRECTORY,i);
        const auto status=f_open(&file,temporary,FA_WRITE|FA_CREATE_NEW);
        if(status==FR_OK) created=true;else if(status!=FR_EXIST) return;
    }
    if(!created) return;
    UINT wrote=0;bool ok=f_write(&file,output.get(),size,&wrote)==FR_OK && wrote==size && f_sync(&file)==FR_OK;
    ok=f_close(&file)==FR_OK && ok;
    bool moved=false;
    if(ok && exists==FR_OK) {
        for(unsigned i=0;i<100;++i) {
            std::snprintf(backup,sizeof(backup),"%s/.PCC-%u.bak",DIRECTORY,i);
            if(f_stat(backup,&info)==FR_NO_FILE) { moved=f_rename(target,backup)==FR_OK;break; }
        }
        ok=moved;
    }
    if(ok) ok=f_rename(temporary,target)==FR_OK;
    if(moved) { if(ok) (void)f_unlink(backup);else (void)f_rename(backup,target); }
    if(!ok) (void)f_unlink(temporary);else ++counts.stores;
}
vm::ValidatedImage certificate(const vm::View& v) {
    return {vm::VALIDATED_MAGIC,v.size,v.code,v.source_size,v.end,v.lines,v.stack,
        v.bytes[7],v.language,v.wide};
}
}
void bind(void* owner,void* bytes,unsigned capacity) {
    if(owner!=storage_owner || bytes!=storage) {
        if(pins) return;
        discard();storage_owner=owner;storage=bytes;
    }
    if(capacity<sizeof(Cache) || (reinterpret_cast<uintptr_t>(bytes)&7U)) {
        discard();storage_capacity=0;
    } else storage_capacity=capacity;
}
void revoke(void* owner) {
    if(owner==storage_owner) { discard();storage_capacity=0; }
}
void detach(void* owner) {
    if(owner!=storage_owner) return;
    discard();storage_owner=storage=nullptr;storage_capacity=0;
}
Prepared find(const char* path,vm::Language language,bool rf,u8* scratch,unsigned scratch_size) {
    Prepared result;
    if(!memory || !files::ready()) { ++counts.ram_misses;return result; }
    char normalized[files::PATH_SIZE];u16 id;
    if(!identity(path,normalized,id)) { ++counts.ram_misses;return result; }
    // The caller lends its inactive compiler image only for this lookup.
    // No source, numeric state or scratch pointer is retained by the cache.
    auto handle=memory->find({files::revision(),id,language,0},{scratch,scratch_size});
    if(!handle) { ++counts.ram_misses;return result; }
    const auto* c=memory->certificate(handle);const auto* image=memory->image(handle);
    if(!c || !image || ((c->flags&2) && !rf)) {
        (void)memory->release(handle);++counts.ram_misses;return result;
    }
    result.view={image,c->size,c->code,c->lines,c->source_size,c->stack,c->language,
        false,(c->flags&2)!=0,c->end,nullptr,c->wide};
    result.generation=handle.generation;result.slot=handle.slot;++pins;++counts.ram_hits;
    return result;
}
void release(Prepared& prepared) {
    if(!prepared) return;
    if(memory) (void)memory->release({prepared.generation,prepared.slot});
    prepared={};if(pins) --pins;if(!pins && discard_pending) discard();
}
bool load(const char* path,vm::Language language,bool rf,const char* source,u16 length,u8* image,vm::View& v) {
    ++counts.disk_misses;
    if(!files::ready()) return false;
    char normalized[files::PATH_SIZE];u16 id;
    if(!identity(path,normalized,id)) return false;
    char name[files::PATH_SIZE];filename(normalized,language,rf,name);
    std::unique_ptr<u8[]> bytes(new(std::nothrow) u8[MAX_FILE]);unsigned used=0;
    if(!bytes || !read_file(name,bytes.get(),MAX_FILE,used)) return false;
    const char* cached_path;const u8* file;u16 n,size;
    const u8* payload=nullptr;u16 image_size=0;
    if(!envelope(bytes.get(),used,cached_path,n,file,size) || std::strcmp(cached_path,normalized) ||
       !disk::view(key(normalized,language,rf,source,length),file,size,payload,image_size)) {
        ++counts.rejected;return false;
    }
    std::memcpy(image,payload,image_size);
    if(vm::inspect(image,image_size,v)!=vm::Error::NONE || v.language!=language ||
       !cacheable(v) || ((v.bytes[7]&2) && !rf)) { ++counts.rejected;return false; }
    --counts.disk_misses;++counts.disk_hits;return true;
}
void remember(const char* path,bool rf,u32 revision,const char* source,u16 length,const vm::View& v,bool persist) {
    if(!cacheable(v) || revision!=files::revision() || !files::ready()) return;
    char normalized[files::PATH_SIZE];u16 id;
    if(!identity(path,normalized,id) || revision!=files::revision()) return;
    if(!memory && storage && storage_capacity>=sizeof(Cache)) memory=new(storage) Cache;
    if(memory) {
        const auto existing=memory->find({revision,id,v.language,0});
        if(existing) (void)memory->release(existing);
        else if(const auto h=memory->reserve({revision,id,v.language,0},(u16)v.size)) {
            std::memcpy(memory->building(h),v.bytes,v.size);
            (void)memory->publish(h,certificate(v));(void)memory->release(h);
        }
    }
    if(persist) store(normalized,rf,source,length,v);
}
void compilation() { ++counts.compiles; }
void discard() {
    if(pins) { discard_pending=true;return; }
    if(memory) {
        const auto packed=memory->packing_statistics();
        counts.packs+=packed.packs;counts.thaws+=packed.thaws;
        memory->~Cache();
    }
    memory=nullptr;discard_pending=false;
}
Statistics statistics() {
    auto result=counts;
    if(memory) {
        result.allocated=sizeof(Cache);result.used=memory->used();
        const auto packed=memory->packing_statistics();
        result.packs+=packed.packs;result.thaws+=packed.thaws;result.packed=packed.packed;
    }
    return result;
}
}
