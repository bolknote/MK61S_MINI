// Production storage + real FatFs on a RAM card. Counters wrap the public
// FatFs calls, so performance assertions count filesystem operations rather
// than host wall time. No device, image file or user media is accessed.
#include "storage.hpp"
#include "storage_journal.hpp"
#include "diagnostics.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
extern "C" {
#define f_open cursor_test_open
#define f_close cursor_test_close
#define f_lseek cursor_test_seek
#define f_read cursor_test_read
#include "ff.h"
#undef f_open
#undef f_close
#undef f_lseek
#undef f_read
#include "diskio.h"
FRESULT f_open(FIL*,const TCHAR*,BYTE);
FRESULT f_close(FIL*);
FRESULT f_lseek(FIL*,FSIZE_t);
FRESULT f_read(FIL*,void*,UINT,UINT*);
}
using namespace picocalc;
namespace {
std::vector<u8> card(64*1024*1024);
bool initialized=false,read_failure=false,seek_failure=false;
struct Counts { unsigned opens=0,closes=0,seeks=0,reads=0,sectors=0; } counts;
u8 pattern(u32 offset) { return (u8)((offset*17U)^(offset>>8)^(offset>>17)); }
void raw_file(const char* path,unsigned size) {
    FIL f;assert(f_open(&f,path,FA_CREATE_ALWAYS|FA_WRITE)==FR_OK);
    u8 bytes[4096];
    for(unsigned at=0;at<size;at+=sizeof(bytes)) {
        const unsigned n=std::min<unsigned>(sizeof(bytes),size-at);
        for(unsigned i=0;i<n;++i) bytes[i]=pattern(at+i);
        UINT used=0;assert(f_write(&f,bytes,n,&used)==FR_OK && used==n);
    }
    assert(f_close(&f)==FR_OK);
}
void check_read(const char* path,u32 offset,unsigned count=512) {
    u8 bytes[512];unsigned used=0;
    assert(count<=sizeof(bytes) && files::read_range(path,offset,bytes,count,used) && used==count);
    for(unsigned i=0;i<used;++i) assert(bytes[i]==pattern(offset+i));
}
void two_passes(const char* path,bool cached) {
    for(unsigned pass=0;pass<2;++pass) for(unsigned at=0;at<87796;at+=96) {
        const unsigned n=std::min(96U,87796-at);u8 bytes[96];
        if(cached) {
            unsigned used=0;assert(files::read_range(path,at,bytes,n,used) && used==n);
        } else {
            FIL f;UINT used=0;assert(f_open(&f,path,FA_READ)==FR_OK);
            assert(f_lseek(&f,at)==FR_OK && f_read(&f,bytes,n,&used)==FR_OK && used==n);
            assert(f_close(&f)==FR_OK);
        }
        for(unsigned i=0;i<n;++i) assert(bytes[i]==pattern(at+i));
    }
}
void suite(BYTE format,const char* name) {
    files::release_read_cursor();storage_journal::reset();
    assert(f_mount(nullptr,"",0)==FR_OK);std::fill(card.begin(),card.end(),0);
    MKFS_PARM options{};options.fmt=format;u8 work[4096];
    assert(f_mkfs("",&options,work,sizeof(work))==FR_OK && files::mount());
    assert(files::mkdir("/Spectrum") && files::mkdir("/Spectrum/Original games"));
    const std::string path="/Spectrum/Original games/"+std::string(100,'x')+".img";
    raw_file(path.c_str(),16*1024*1024);
    counts={};two_passes(path.c_str(),false);const auto old=counts;
    counts={};two_passes(path.c_str(),true);const auto now=counts;
    assert(now.opens==1 && now.closes==0 && now.seeks==1 && now.reads==old.reads);
    assert(old.opens==1830 && old.closes==1830 && old.seeks==1830);
    assert(now.sectors<old.sectors);
    std::printf("PASS %s 2x87796B/96B: opens %u->%u, seeks %u->%u, card-sector reads %u->%u\n",
        name,old.opens,now.opens,old.seeks,now.seeks,old.sectors,now.sectors);
    // Deterministic nonsequential, repeated and backward sector reads through
    // the full 16 MiB image, with the real FatFs cluster traversal.
    u32 random=0x10293847;
    for(unsigned i=0;i<2048;++i) {
        random=random*1664525+1013904223;
        check_read(path.c_str(),(random%32768)*512);
    }
    unsigned used=123;u8 bytes[512];
    assert(files::read_range(path.c_str(),16*1024*1024,bytes,512,used) && used==0);
    assert(files::read_range(path.c_str(),UINT32_MAX,bytes,512,used) && used==0);
    assert(!files::read_range(nullptr,0,bytes,1,used) && used==0);
    assert(!files::read_range(std::string(files::PATH_SIZE,'x').c_str(),0,bytes,1,used));
    assert(!files::read_range(path.c_str(),0,nullptr,1,used));
    // Both seek and read errors discard the cursor; the next successful
    // request must reopen rather than reusing a poisoned FatFs FIL.
    check_read(path.c_str(),0);counts={};seek_failure=true;
    assert(!files::read_range(path.c_str(),8192,bytes,512,used));seek_failure=false;
    check_read(path.c_str(),0);assert(counts.opens==1 && counts.closes==1);
    counts={};read_failure=true;
    assert(!files::read_range(path.c_str(),512,bytes,512,used));read_failure=false;
    check_read(path.c_str(),0);assert(counts.opens==1 && counts.closes==1);
    // A path change closes the old lock. Missing-file attempts never leave
    // a previous cursor attached to an unrelated filename.
    assert(!files::read_range("/absent.img",0,bytes,1,used));
    check_read(path.c_str(),0);
    const u8 changed[]={4,3,2,1};
    assert(files::write_range(path.c_str(),2,changed,sizeof(changed)));
    assert(files::read_range(path.c_str(),0,bytes,8,used) && used==8);
    assert(!std::memcmp(bytes+2,changed,sizeof(changed)));
    assert(files::rename(path.c_str(),"/renamed.img"));
    assert(!files::read_range(path.c_str(),0,bytes,1,used));
    check_read("/renamed.img",512);
    assert(files::write("/renamed.img",changed,sizeof(changed)));
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==4 && !std::memcmp(bytes,changed,4));
    auto* upload=files::begin_write("/renamed.img");assert(upload);
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==4);
    assert(files::append_write(upload,changed,2));
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==4);
    assert(files::commit_write(upload));
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==2);
    upload=files::begin_write("/renamed.img");assert(upload);
    assert(files::append_write(upload,changed,4));
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==2);
    files::cancel_write(upload);assert(!upload);
    assert(files::read_range("/renamed.img",0,bytes,8,used) && used==2);
    assert(files::remove("/renamed.img"));
    assert(!files::read_range("/renamed.img",0,bytes,8,used));
    // A host replaces a file while native FatFs is unmounted. The old FIL
    // and old size may not survive the USB ownership/media epoch change.
    raw_file("/media.bin",1024);check_read("/media.bin",0);
    assert(files::begin_usb());
    assert(!files::read_range("/media.bin",0,bytes,8,used));
    FATFS host{};assert(f_mount(&host,"",1)==FR_OK);raw_file("/media.bin",200);
    assert(f_mount(nullptr,"",0)==FR_OK);files::usb_eject();assert(files::end_usb());
    assert(files::read_range("/media.bin",0,bytes,512,used) && used==200);
    check_read("/media.bin",0,100);assert(files::mount());
    check_read("/media.bin",0,100);
    FIL f;assert(f_open(&f,"/media.bin",FA_WRITE)==FR_LOCKED);
    files::release_read_cursor();
    assert(f_open(&f,"/media.bin",FA_WRITE)==FR_OK && f_close(&f)==FR_OK);
    check_read("/media.bin",0,100);assert(files::format() && !files::exists("/media.bin"));
    std::printf("PASS %s: random sectors, EOF, errors, replacement, streamed commit/cancel, rename/remove, remount, USB replacement, release and format\n",name);
}
}
extern "C" {
FRESULT f_open(FIL* f,const TCHAR* path,BYTE flags) { ++counts.opens;return cursor_test_open(f,path,flags); }
FRESULT f_close(FIL* f) { ++counts.closes;return cursor_test_close(f); }
FRESULT f_lseek(FIL* f,FSIZE_t at) { ++counts.seeks;return seek_failure?FR_DISK_ERR:cursor_test_seek(f,at); }
FRESULT f_read(FIL* f,void* out,UINT n,UINT* used) {
    ++counts.reads;if(read_failure) { *used=0;return FR_DISK_ERR; } return cursor_test_read(f,out,n,used);
}
DWORD get_fattime() { return ((2026-1980)<<25)|(11<<21)|(6<<16); }
DSTATUS disk_initialize(BYTE drive) { return drive || !sd::init()?STA_NOINIT:0; }
DSTATUS disk_status(BYTE drive) { return drive || !sd::ready()?STA_NOINIT:0; }
DRESULT disk_read(BYTE drive,BYTE* data,LBA_t sector,UINT count) {
    return !drive && sector+count<=sd::sectors() && sd::read_sectors(sector,data,count)?RES_OK:RES_ERROR;
}
DRESULT disk_write(BYTE drive,const BYTE* data,LBA_t sector,UINT count) {
    return !drive && sector+count<=sd::sectors() && storage_journal::write_sectors(sector,data,count)?RES_OK:RES_ERROR;
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
namespace picocalc::diagnostics {
Scope::Scope(Point p):point_(p),start_(0),generation_(0) {}
Scope::~Scope() { (void)point_;(void)start_;(void)generation_; } void feed_watchdog() {}
}
namespace picocalc::sd {
bool init() { initialized=true;return true; } bool ready() { return initialized; }
u32 sectors() { return card.size()/512; }
bool read(u32 sector,u8 out[512]) { return read_sectors(sector,out,1); }
bool read_sectors(u32 sector,u8* out,u32 count) {
    if(sector>=sectors() || count>sectors()-sector) return false;
    counts.sectors+=count;std::memcpy(out,card.data()+(size_t)sector*512,(size_t)count*512);return true;
}
bool write(u32 sector,const u8 data[512]) { return write_sectors(sector,data,1); }
bool write_sectors(u32 sector,const u8* data,u32 count) {
    if(sector>=sectors() || count>sectors()-sector) return false;
    std::memcpy(card.data()+(size_t)sector*512,data,(size_t)count*512);return true;
}
bool sync() { return true; }
}
int main() { suite(FM_FAT,"FAT16");suite(FM_FAT32,"FAT32");suite(FM_EXFAT,"exFAT"); }
