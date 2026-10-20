#include "storage_journal.hpp"
#include "storage.hpp"
#include "diagnostics.hpp"
#include <cstring>
#include <memory>
#include <new>
extern "C" {
#include "ff.h"
}

namespace picocalc { namespace storage_journal {
namespace {
enum : u32 { INITIALIZING=1,EMPTY=2,RECORDING=3 };
struct Header { u64 sequence=0;u32 state=0,binding=0;unsigned slot=0;u64 transaction=0;u32 count=0; };
struct State {
    u32 map[FILE_SECTORS]{},logged[CAPACITY]{};
    unsigned count=0;
    Header header{};
    u32 binding=0;
    bool recording=false,failed=false;
};
std::unique_ptr<State> state;
const char* problem="";
bool reject(const char* message) { problem=message;return false; }
u32 get32(const u8* p) { return (u32)p[0]|(u32)p[1]<<8|(u32)p[2]<<16|(u32)p[3]<<24; }
void put32(u8* p,u32 n) { for(unsigned i=0;i<4;++i) p[i]=(u8)(n>>(i*8)); }
u64 get64(const u8* p) { return get32(p)|(u64)get32(p+4)<<32; }
void put64(u8* p,u64 n) { put32(p,(u32)n);put32(p+4,(u32)(n>>32)); }
u32 crc(const u8* bytes,unsigned size) {
    u32 value=0xFFFFFFFF;
    for(unsigned i=0;i<size;++i) {
        value^=bytes[i];
        for(unsigned bit=0;bit<8;++bit) value=(value>>1)^((value&1)?0xEDB88320U:0);
    }
    return value^0xFFFFFFFF;
}
void encode(const Header& h,u8 out[512]) {
    std::memset(out,0,512);std::memcpy(out,"MK61JNL1",8);
    put64(out+8,h.sequence);put32(out+16,h.state);put32(out+20,h.binding);
    put32(out+24,FILE_SECTORS);
    put64(out+28,h.transaction);put32(out+36,h.count);put32(out+508,crc(out,508));
}
bool decode(const u8 in[512],Header& h,unsigned slot) {
    if(std::memcmp(in,"MK61JNL1",8) || get32(in+24)!=FILE_SECTORS || get32(in+508)!=crc(in,508)) return false;
    h={get64(in+8),get32(in+16),get32(in+20),slot,get64(in+28),get32(in+36)};
    return h.sequence && h.state>=INITIALIZING && h.state<=RECORDING && h.count<=CAPACITY &&
        (h.state!=RECORDING || (h.transaction && h.transaction<=h.sequence));
}
bool store_header(Header h) {
    u8 bytes[512];encode(h,bytes);
    if(!sd::write(state->map[h.slot],bytes) || !sd::sync()) return reject("Recovery journal header I/O error");
    state->header=h;return true;
}
bool header(Header& h) {
    bool found=false;u8 bytes[512];
    for(unsigned slot=0;slot<2;++slot) {
        if(!sd::read(state->map[slot],bytes)) return reject("Recovery journal read error");
        Header candidate;
        if(decode(bytes,candidate,slot)) {
            if(!found || candidate.sequence>h.sequence) { h=candidate;found=true; }
        } else {
            bool nonzero=false;for(u8 value:bytes) if(value) nonzero=true;
            if(nonzero) return reject("Recovery journal header is damaged");
        }
    }
    return found || reject("Recovery journal headers are damaged");
}
bool journal_sector(u32 sector) {
    for(u32 lba:state->map) if(lba==sector) return true;
    return false;
}
bool initialize() {
    FIL file;FRESULT r=f_open(&file,FILE_NAME,FA_WRITE|FA_CREATE_ALWAYS);
    if(r!=FR_OK) return reject("Cannot create recovery journal");
    // A recognizable initialization marker is durable before expansion. A cut
    // during this phase has not touched any user-file transaction yet.
    u8 bytes[512];encode({1,INITIALIZING,0,0},bytes);UINT written=0;
    r=f_write(&file,bytes,sizeof(bytes),&written);
    if(r==FR_OK && written==sizeof(bytes)) r=f_sync(&file);else r=FR_DISK_ERR;
    std::memset(bytes,0,sizeof(bytes));
    for(unsigned sector=1;sector<FILE_SECTORS && r==FR_OK;++sector) {
        r=f_write(&file,bytes,sizeof(bytes),&written);
        if(written!=sizeof(bytes)) r=FR_DISK_ERR;
        diagnostics::feed_watchdog();
    }
    if(r==FR_OK) r=f_sync(&file);
    const FRESULT closed=f_close(&file);
    return (r==FR_OK && closed==FR_OK) || reject("Cannot initialize recovery journal");
}
// Returns true with no state if the card has never used the journal.
bool attach(bool create) {
    state.reset();problem="";
    FILINFO info{};FRESULT r=f_stat(FILE_NAME,&info);
    if(r==FR_NO_FILE) { if(!create) return true;if(!initialize()) return false; }
    else if(r!=FR_OK || (info.fattrib&AM_DIR)) return reject("Recovery journal name is occupied");
    else if(info.fsize!=FILE_BYTES) {
        bool ours=info.fsize==0;
        if(info.fsize>=512) {
            FIL file;u8 bytes[512];UINT got=0;
            if(f_open(&file,FILE_NAME,FA_READ)==FR_OK) {
                r=f_read(&file,bytes,sizeof(bytes),&got);const FRESULT closed=f_close(&file);Header h;
                ours=r==FR_OK && closed==FR_OK && got==512 && decode(bytes,h,0) && h.state==INITIALIZING;
            }
        }
        if(!ours) return reject("Recovery journal has an invalid size");
        // Provisioning precedes every user-file transaction. A read-only
        // mount can leave an incomplete initialization for the next write,
        // including on a full card which must first be cleaned via USB.
        if(!create) return true;
        if(!initialize()) return false;
    }
    state.reset(new(std::nothrow) State);
    if(!state) return reject("Not enough recovery memory");
    FIL file;if(f_open(&file,FILE_NAME,FA_READ)!=FR_OK) return reject("Cannot open recovery journal");
    const auto* fs=file.obj.fs;
    bool valid=f_size(&file)==FILE_BYTES;
    for(unsigned i=0;i<FILE_SECTORS && valid;++i) {
        // Seeking one byte into the sector selects its cluster even at a
        // cluster boundary. No FatFs call is made from the disk_write hook.
        r=f_lseek(&file,(FSIZE_t)i*512+1);
        const u64 lba=(u64)fs->database+(u64)(file.clust-2)*fs->csize+(i%fs->csize);
        valid=r==FR_OK && file.clust>=2 && lba<sd::sectors();
        if(valid) state->map[i]=(u32)lba;
        for(unsigned n=0;n<i && valid;++n) if(state->map[n]==state->map[i]) valid=false;
        diagnostics::feed_watchdog();
    }
    const FRESULT closed=f_close(&file);
    if(!valid || closed!=FR_OK) return reject("Invalid recovery journal allocation");
    state->binding=crc((const u8*)state->map,sizeof(state->map));
    if(!header(state->header)) return false;
    if(state->header.state==INITIALIZING) {
        if(!store_header({state->header.sequence+1,EMPTY,state->binding,1-state->header.slot})) return false;
    }
    if(state->header.state==RECORDING && state->header.binding!=state->binding)
        return reject("Pending recovery journal was moved");
    return true;
}
bool records() {
    state->count=0;u8 meta[512],old[512];
    for(unsigned i=0;i<state->header.count;++i) {
        if(!sd::read(state->map[2+i*2],meta)) return reject("Recovery record read error");
        if(std::memcmp(meta,"MK61UNDO",8) || get64(meta+8)!=state->header.transaction)
            return reject("Recovery record identity is damaged");
        const u32 lba=get32(meta+20);
        if(get32(meta+16)!=i || get32(meta+508)!=crc(meta,508) || lba>=sd::sectors() || journal_sector(lba))
            return reject("Recovery record is damaged");
        for(unsigned n=0;n<i;++n) if(state->logged[n]==lba) return reject("Duplicate recovery record");
        if(!sd::read(state->map[3+i*2],old) || get32(meta+24)!=crc(old,512)) return reject("Recovery data is damaged");
        state->logged[state->count++]=lba;diagnostics::feed_watchdog();
    }
    return true;
}
bool undo() {
    // Validate every record before the first repair write. A second cut during
    // repair replays the same before-images; the active header remains durable.
    if(!records()) return false;
    u8 bytes[512];
    for(unsigned n=0;n<state->count;++n) {
        if(!sd::read(state->map[3+n*2],bytes) || !sd::write(state->logged[n],bytes)) return reject("Recovery replay I/O error");
        diagnostics::feed_watchdog();
    }
    if(!sd::sync()) return reject("Recovery replay sync error");
    return store_header({state->header.sequence+1,EMPTY,state->binding,1-state->header.slot});
}
}
bool reserved(const char* path) {
    if(!path) return false;
    if(path[0]=='0' && path[1]==':') path+=2;
    while(*path=='/' || *path=='\\') ++path;
    const char* end=path+std::strlen(path);
    // FatFs accepts DOS-style trailing dots/spaces and separators too.
    while(end>path && (end[-1]=='/' || end[-1]=='\\' || end[-1]==' ' || end[-1]=='.')) --end;
    const char* name=FILE_NAME+1;
    while(path<end && *name) { const unsigned c=(u8)*path++;if((c>='a' && c<='z'?c-32:c)!=(unsigned)*name++) return false; }
    return path==end && !*name;
}
const char* error() { return problem; }
bool active() { return state && state->recording; }
void reset() { state.reset(); }
bool recover() {
    if(!attach(false)) { state.reset();return false; }
    bool ok=true;
    if(state && state->header.state==RECORDING) ok=undo();
    state.reset();return ok;
}
bool begin() {
    if(active()) return reject("Another file transaction is active");
    if(!attach(true)) { state.reset();return false; }
    if(state->header.state==RECORDING) { state.reset();return reject("File recovery must finish before writing"); }
    if(state->header.sequence>=UINT64_MAX-CAPACITY-3) { state.reset();return reject("Recovery journal sequence exhausted"); }
    const auto next=state->header.sequence+1;
    if(!store_header({next,RECORDING,state->binding,1-state->header.slot,next,0})) { state.reset();return false; }
    state->recording=true;return true;
}
bool write(u32 sector,const u8 data[512]) {
    if(!active()) return sd::write(sector,data);
    if(state->failed || journal_sector(sector)) { state->failed=true;return reject("Recovery journal write rejected"); }
    bool known=false;for(unsigned i=0;i<state->count;++i) if(state->logged[i]==sector) known=true;
    if(!known) {
        if(state->count==CAPACITY) { state->failed=true;return reject("File transaction exceeds recovery capacity"); }
        const unsigned i=state->count;u8 old[512],meta[512]{};
        if(!sd::read(sector,old)) { state->failed=true;return reject("Cannot save recovery sector"); }
        std::memcpy(meta,"MK61UNDO",8);put64(meta+8,state->header.transaction);put32(meta+16,i);put32(meta+20,sector);
        put32(meta+24,crc(old,512));put32(meta+508,crc(meta,508));
        // The old sector and its checksummed descriptor are durable before
        // FatFs can modify the corresponding sector of the filesystem.
        if(!sd::write(state->map[3+i*2],old) || !sd::sync() || !sd::write(state->map[2+i*2],meta) || !sd::sync()) {
            state->failed=true;return reject("Cannot sync recovery record");
        }
        Header next=state->header;++next.sequence;next.slot=1-next.slot;next.count=i+1;
        if(!store_header(next)) { state->failed=true;return false; }
        state->logged[state->count++]=sector;
    }
    diagnostics::feed_watchdog();
    if(sd::write(sector,data)) return true;
    state->failed=true;return reject("microSD transaction I/O error");
}
bool sync() {
    if(active() && state->failed) return false;
    if(sd::sync()) return true;
    if(active()) state->failed=true;
    return reject("microSD transaction sync error");
}
bool commit() {
    if(!active() || state->failed) return false;
    if(!sd::sync()) return reject("File transaction sync error");
    // After attempting the commit marker we must not undo: the marker may
    // already be on the medium even if the SD driver reports an I/O failure.
    const bool ok=store_header({state->header.sequence+1,EMPTY,state->binding,1-state->header.slot});
    state.reset();return ok;
}
bool rollback() {
    if(!active()) { state.reset();return true; }
    Header latest;const bool ok=header(latest) && (state->header=latest,true) &&
        (latest.state==EMPTY || (latest.state==RECORDING && undo()));
    state.reset();return ok;
}
} }
