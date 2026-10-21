// The real FatFs + production journal on a RAM card. Replaying each durable
// sector-write prefix simulates a reset with all process/FatFs caches lost.
#include "storage.hpp"
#include "storage_journal.hpp"
#include "diagnostics.hpp"
#include "mk8_literal.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>
extern "C" {
#include "ff.h"
#include "diskio.h"
}
using namespace picocalc;
namespace {
struct Write { u32 sector;std::array<u8,512> bytes; };
std::vector<u8> disk(64*1024*1024);
std::vector<Write> trace;
std::vector<u32> changed;
bool tracing=false,initialized=false;
int fail_after=-1,fail_sync_after=-1;
unsigned sync_calls=0;
unsigned cuts=0,repair_cuts=0;
void save_sector(u32 sector,const u8* bytes) {
    std::memcpy(disk.data()+(size_t)sector*512,bytes,512);changed.push_back(sector);
}
std::vector<u32> journal_map() {
    FIL file;assert(f_open(&file,storage_journal::FILE_NAME,FA_READ)==FR_OK);
    std::vector<u32> map;
    for(unsigned i=0;i<storage_journal::FILE_SECTORS;++i) {
        assert(f_lseek(&file,i*512+1)==FR_OK);
        const auto* fs=file.obj.fs;
        map.push_back((u32)(fs->database+(file.clust-2)*fs->csize+i%fs->csize));
    }
    assert(f_close(&file)==FR_OK);std::sort(map.begin(),map.end());return map;
}
void restore_changed(const std::vector<u8>& before) {
    for(u32 sector:changed) std::memcpy(disk.data()+(size_t)sector*512,before.data()+(size_t)sector*512,512);
    changed.clear();fail_after=fail_sync_after=-1;
}
void same_filesystem(const std::vector<u8>& expected,const std::vector<u32>& journal) {
    for(u32 sector:changed) if(!std::binary_search(journal.begin(),journal.end(),sector)) {
        if(std::memcmp(disk.data()+(size_t)sector*512,expected.data()+(size_t)sector*512,512)) {
            std::fprintf(stderr,"Unexpected filesystem sector %u (cut %u)\n",sector,cuts);std::abort();
        }
    }
}
bool matches(const std::vector<u8>& expected,const std::vector<u32>& journal) {
    for(u32 sector:changed) if(!std::binary_search(journal.begin(),journal.end(),sector) &&
        std::memcmp(disk.data()+(size_t)sector*512,expected.data()+(size_t)sector*512,512)) return false;
    return true;
}
void mount() {
    if(!files::mount()) { std::fprintf(stderr,"Mount: %s\n",files::error());std::abort(); }
}
void check(const char* name,const std::function<bool()>& operation,bool errors=true) {
    const auto before=disk;changed.clear();trace.clear();tracing=true;sync_calls=0;
    assert(operation());tracing=false;const auto writes=trace;const auto after=disk;const auto syncs=sync_calls;
    const auto journal=journal_map();assert(!writes.empty());
    for(unsigned cut=0;cut<=writes.size();++cut) {
        restore_changed(before);
        for(unsigned i=0;i<cut;++i) save_sector(writes[i].sector,writes[i].bytes.data());
        mount();same_filesystem(cut==writes.size()?after:before,journal);++cuts;
        // A completed repair is a fixed point of another cold mount.
        const auto count=changed.size();mount();assert(changed.size()==count);
    }
    // Also cut every sector of a recovery, including its final decision marker.
    restore_changed(before);
    for(unsigned i=0;i+1<writes.size();++i) save_sector(writes[i].sector,writes[i].bytes.data());
    const auto pending=disk;trace.clear();tracing=true;mount();tracing=false;const auto repairs=trace;
    for(unsigned cut=0;cut<=repairs.size();++cut) {
        restore_changed(pending);
        for(unsigned i=0;i<cut;++i) save_sector(repairs[i].sector,repairs[i].bytes.data());
        mount();same_filesystem(before,journal);++repair_cuts;
    }
    if(errors) for(unsigned at=0;at<writes.size();++at) {
        disk=before;changed.clear();mount();fail_after=(int)at;
        assert(!operation());fail_after=-1;mount();same_filesystem(before,journal);
    }
    if(errors) for(unsigned at=0;at<syncs;++at) {
        disk=before;changed.clear();mount();fail_sync_after=(int)at;
        const bool ok=operation();
        assert(!ok);fail_sync_after=-1;mount();assert(matches(before,journal) || matches(after,journal));
    }
    disk=after;changed.clear();mount();
    std::printf("PASS %s: %zu write cuts, %zu replay cuts%s\n",name,writes.size()+1,repairs.size()+1,errors?", all I/O failures":"");
}
void raw_write(const char* path,const std::string& text) {
    FIL file;UINT n=0;assert(f_open(&file,path,FA_CREATE_ALWAYS|FA_WRITE)==FR_OK);
    assert(f_write(&file,text.data(),text.size(),&n)==FR_OK && n==text.size());assert(f_close(&file)==FR_OK);
}
void format(BYTE type) {
    storage_journal::reset();f_mount(nullptr,"",0);disk.assign(disk.size(),0);trace.clear();changed.clear();
    MKFS_PARM options{};options.fmt=type;u8 work[4096];assert(f_mkfs("",&options,work,sizeof(work))==FR_OK);mount();
}
void suite(BYTE type,const char* name) {
    format(type);
    // Exercise first-use provisioning independently of an already valid journal.
    const std::string original(900,'A');raw_write("/old.txt",original);
    const auto virgin=disk;trace.clear();tracing=true;
    assert(files::write_text("/old.txt","NEW",3));tracing=false;const auto first=trace;
    const auto journal=journal_map();const auto installed=disk;
    for(unsigned cut=0;cut<=first.size();++cut) {
        disk=virgin;changed.clear();
        for(unsigned i=0;i<cut;++i) save_sector(first[i].sector,first[i].bytes.data());
        mount();
        char out[1024];unsigned used=0;assert(files::read_text("/old.txt",out,sizeof(out),used));
        assert(cut==first.size()?std::string(out,used)=="NEW":std::string(out,used)==original);++cuts;
    }
    disk=installed;changed.clear();mount();
    assert(!files::write_text("/MK61JRN.SYS","X",1));
    assert(!files::remove("0:\\mk61jrn.sys") && !files::rename("/old.txt","//MK61JRN.SYS"));
    assert(!files::write_text("0:/mk61jrn.sys. ","X",1) && !files::remove("/MK61JRN.SYS/"));
    files::Entry entries[8];unsigned used=0;bool more=false;
    assert(files::list("/",0,entries,8,used,more) && used==1 && !more);
    assert(files::mkdir("/Исходники"));
    const std::string path="/Исходники/"+std::string(180,'a')+"-ёж.bas";
    const std::string old(4900,'O'),next(7300,'N');
    assert(files::write(path.c_str(),(const u8*)old.data(),old.size()));
    check("overwrite + long UTF-8/LFN",[&] { return files::write(path.c_str(),(const u8*)next.data(),next.size()); });
    check("create empty file",[] { return files::write("/empty.bin",nullptr,0); });
    check("create UTF-8 text",[] { const auto* p=M8("Широкая строка → Ёж\n");return files::write_text("/Исходники/новый.txt",p,std::strlen(p)); });
    check("streamed replacement",[&] {
        auto* writer=files::begin_write(path.c_str());if(!writer) return false;
        for(unsigned i=0;i<17;++i) if(!files::append_write(writer,(const u8*)next.data()+i*97,97)) { files::cancel_write(writer);return false; }
        return files::commit_write(writer);
    });
    check("mkdir",[] { return files::mkdir("/Исходники/каталог"); });
    check("move/rename",[&] { return files::rename(path.c_str(),"/Исходники/каталог/после.bas"); });
    check("delete",[] { return files::remove("/Исходники/каталог/после.bas"); });
    // A complete maximum editor document, including three-byte M8 codepoints.
    const std::string full(65534,(char)0x0F);
    assert(files::write_text("/full.txt",full.data(),full.size()));
    files::Entry full_info;assert(files::stat("/full.txt",full_info) && full_info.size==196602);
    char raw[8];unsigned n=0;assert(files::read_range("/full.txt",0,(u8*)raw,sizeof(raw),n));
    const std::string too_large(300000,'X');const auto before=disk;changed.clear();
    assert(!files::write("/old.txt",(const u8*)too_large.data(),too_large.size()));mount();same_filesystem(before,journal);
    // Corrupt a committed record's magic/transaction/payload and refuse all
    // writes/export, retaining every byte until the valid record is restored.
    trace.clear();tracing=true;assert(files::write_text("/old.txt","LAST",4));tracing=false;
    const auto complete=trace;disk=before;changed.clear();
    for(unsigned i=0;i+1<complete.size();++i) save_sector(complete[i].sector,complete[i].bytes.data());
    const auto pending=disk;
    std::vector<u32> physical;
    FIL file;assert(f_open(&file,storage_journal::FILE_NAME,FA_READ)==FR_OK);
    for(unsigned i=0;i<4;++i) { assert(f_lseek(&file,i*512+1)==FR_OK);physical.push_back((u32)(file.obj.fs->database+(file.clust-2)*file.obj.fs->csize+i%file.obj.fs->csize)); }
    assert(f_close(&file)==FR_OK);
    for(const auto& at:std::array<std::pair<unsigned,unsigned>,4>{{{0,508},{2,0},{2,8},{3,20}}}) {
        disk=pending;disk[(size_t)physical[at.first]*512+at.second]^=1;const auto corrupt=disk;
        assert(!files::mount() && !files::ready() && !files::begin_usb());assert(disk==corrupt);
    }
    disk=pending;mount();same_filesystem(before,journal);
    std::printf("PASS %s: provisioning, reserved file, maximum source, capacity rollback and damaged-journal preservation\n",name);
    // Running out of space during first-use provisioning must still permit
    // reading the old files and exporting the card to a host to free space.
    format(type);raw_write("/old.txt",original);
    DWORD free=0;FATFS* fs=nullptr;assert(f_getfree("",&free,&fs)==FR_OK);
    FIL filler;assert(f_open(&filler,"/filler.bin",FA_CREATE_NEW|FA_WRITE)==FR_OK);
    assert(f_lseek(&filler,(FSIZE_t)(free-4)*fs->csize*512)==FR_OK);assert(f_close(&filler)==FR_OK);
    assert(!files::write_text("/old.txt","NEW",3));mount();
    char out[1024];unsigned size=0;assert(files::read_text("/old.txt",out,sizeof(out),size) && std::string(out,size)==original);
    assert(files::begin_usb());files::usb_eject();assert(files::end_usb());
    // The host/card-reader's deletion frees room without a firmware transaction.
    assert(f_unlink("/filler.bin")==FR_OK);
    assert(files::write_text("/old.txt","NEW",3));
    std::printf("PASS %s: full-card provisioning keeps reads/USB available; retry after freeing space\n",name);
}
}
namespace picocalc { namespace diagnostics {
Scope::Scope(Point p):point_(p),start_(0),generation_(0) {}
Scope::~Scope() { (void)point_;(void)start_;(void)generation_; } void feed_watchdog() {}
} namespace sd {
bool init() { initialized=true;return true; } bool ready() { return initialized; }
u32 sectors() { return disk.size()/512; }
bool read(u32 sector,u8 out[512]) { if(sector>=sectors()) return false;std::memcpy(out,disk.data()+(size_t)sector*512,512);return true; }
bool read_sectors(u32 sector,u8* out,u32 count) { for(unsigned i=0;i<count;++i) if(!read(sector+i,out+i*512)) return false;return true; }
bool write(u32 sector,const u8 data[512]) {
    if(sector>=sectors()) return false;
    if(fail_after==0) { fail_after=-1;return false; } if(fail_after>0) --fail_after;
    if(tracing) { Write entry;entry.sector=sector;std::memcpy(entry.bytes.data(),data,512);trace.push_back(entry); }
    save_sector(sector,data);return true;
}
bool write_sectors(u32 sector,const u8* data,u32 count) {
    if(!data || !count || sector>=sectors() || count>sectors()-sector) return false;
    for(u32 i=0;i<count;++i) if(!write(sector+i,data+i*512)) return false;
    return true;
}
bool sync() {
    ++sync_calls;
    if(fail_sync_after==0) { fail_sync_after=-1;return false; }
    if(fail_sync_after>0) --fail_sync_after;return true;
}
} }
extern "C" {
DWORD get_fattime() { return ((2026-1980)<<25)|(10<<21)|(20<<16); }
DSTATUS disk_initialize(BYTE drive) { return drive || !sd::init()?STA_NOINIT:0; }
DSTATUS disk_status(BYTE drive) { return drive || !sd::ready()?STA_NOINIT:0; }
DRESULT disk_read(BYTE drive,BYTE* data,LBA_t sector,UINT count) { return !drive && sector+count<=sd::sectors() && sd::read_sectors(sector,data,count)?RES_OK:RES_ERROR; }
DRESULT disk_write(BYTE drive,const BYTE* data,LBA_t sector,UINT count) {
    if(drive || sector+count>sd::sectors()) return RES_PARERR;
    return storage_journal::write_sectors(sector,data,count)?RES_OK:RES_ERROR;
}
DRESULT disk_ioctl(BYTE drive,BYTE op,void* out) {
    if(drive) return RES_PARERR;
    if(op==CTRL_SYNC) return storage_journal::sync()?RES_OK:RES_ERROR;
    if(op==GET_SECTOR_COUNT) *(LBA_t*)out=sd::sectors();
    else if(op==GET_SECTOR_SIZE) *(WORD*)out=512;
    else if(op==GET_BLOCK_SIZE) *(DWORD*)out=1;
    else return RES_PARERR;return RES_OK;
}
}
int main() {
    std::setbuf(stdout,nullptr);
    suite(FM_FAT,"FAT16");suite(FM_FAT32,"FAT32");suite(FM_EXFAT,"exFAT");
    std::printf("PASS recovery: %u power-cut prefixes and %u interrupted-replay prefixes; three real FatFs formats\n",cuts,repair_cuts);
}
