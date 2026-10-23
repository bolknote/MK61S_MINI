#include "storage.hpp"
#include "shared_memory_buffer.hpp"
#include "mk8_codec.hpp"
#include "diagnostics.hpp"
#include "storage_journal.hpp"
#include <cstdio>
#include <cstring>
#include <new>
extern "C" {
#include "ff.h"
}

namespace picocalc { namespace files {
struct WriteSession {
    FIL file{};
    char path[PATH_SIZE]{},temporary[PATH_SIZE]{};
    u32 revision=0;
    bool open=false,text=false;
};
namespace {
FATFS filesystem;
bool mounted = false, usb = false, ejected = false, recovery_required=false;
u32 generation = 1;
u32 media_epoch = 1;
char problem[64] = "No microSD mounted";
WriteSession* writer=nullptr;
bool finish_transaction(bool success);
void abort_write(WriteSession* value) {
    if(!value || !value->open) return;
    value->open=false;
    if(writer==value) writer=nullptr;
    // Discard the unsynced FatFs window too; closing it would flush an upload
    // which the caller explicitly cancelled.
    if(mounted && !usb) (void)finish_transaction(false);
}
struct TextCache {
    char path[PATH_SIZE]{};
    u32 generation=0,index[128]{};
    u16 length=0,window_start=0,window_size=0;
    bool valid=false;
    u8 window[512]{};
} text_cache;
bool fail(FRESULT result) {
    if(result == FR_OK) { problem[0] = 0; return true; }
    const char* text = result == FR_NO_FILE || result == FR_NO_PATH ? "File or directory not found" :
        result == FR_NOT_READY ? "No microSD / card not ready" : result == FR_NO_FILESYSTEM ? "No FAT/exFAT filesystem" :
        result == FR_DENIED ? "Write denied or directory not empty" : result == FR_EXIST ? "Name already exists" :
        result == FR_INVALID_NAME ? "Invalid or too long filename" : "microSD I/O error";
    std::snprintf(problem, sizeof(problem), "%s (%u)", text, (unsigned)result);
    return false;
}
bool available() {
    if(usb) { std::snprintf(problem, sizeof(problem), "USB owns the microSD"); return false; }
    if(!mounted) return mount();
    return true;
}
bool start_transaction() {
    if(writer) abort_write(writer);
    if(!available()) return false;
    if(storage_journal::begin()) return true;
    std::snprintf(problem,sizeof(problem),"%s",storage_journal::error());
    recovery_required=true;mounted=false;(void)f_mount(nullptr,"",0);return false;
}
bool finish_transaction(bool success) {
    if(success && storage_journal::commit()) return true;
    char saved[sizeof(problem)];std::snprintf(saved,sizeof(saved),"%s",problem);
    if(storage_journal::error()[0]) std::snprintf(saved,sizeof(saved),"%s",storage_journal::error());
    const bool undone=storage_journal::rollback();
    if(!undone) std::snprintf(saved,sizeof(saved),"%s",storage_journal::error());
    recovery_required=true;mounted=false;(void)f_mount(nullptr,"",0);
    // mount() retries a failed replay and also resolves an uncertain commit
    // marker. No user filesystem operation is allowed before it completes.
    if(undone && mount()) std::snprintf(problem,sizeof(problem),"%s",saved);
    else if(!undone) std::snprintf(problem,sizeof(problem),"%s",saved);
    return false;
}
bool private_name(const char* path, const char* suffix, char out[PATH_SIZE]) {
    const char* slash = std::strrchr(path, '/');
    const unsigned prefix = slash ? (unsigned)(slash - path + 1) : 0;
    for(unsigned i = 0; i < 1000; ++i) {
        const int length = std::snprintf(out, PATH_SIZE, "%.*s.MK61-%u.%s", prefix, path, i, suffix);
        if(length < 0 || length >= (int)PATH_SIZE) return fail(FR_INVALID_NAME);
        FILINFO info;
        const FRESULT result = f_stat(out, &info);
        if(result == FR_NO_FILE) return true;
        if(result != FR_OK) return fail(result);
    }
    return fail(FR_EXIST);
}
bool contains(const char* name,const char* filter) {
    if(!filter || !*filter) return true;
    u8 decoded[256],needle[256];usize n=0,m=0;
    if(!mk8::from_utf8((const u8*)name,std::strlen(name),decoded,sizeof(decoded),n) ||
       !mk8::from_utf8((const u8*)filter,std::strlen(filter),needle,sizeof(needle),m)) return false;
    if(m>n) return false;
    for(usize start=0;start<=n-m;++start) {
        usize i=0;
        while(i<m && mk8::fold_case(decoded[start+i])==mk8::fold_case(needle[i])) ++i;
        if(i==m) return true;
    }
    return false;
}
}
bool mount() {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(usb) return available();
    abort_write(writer);
    mounted = fail(f_mount(&filesystem, "", 1));
    if(mounted) {
        recovery_required=true;
        if(!storage_journal::recover()) {
            std::snprintf(problem,sizeof(problem),"%s",storage_journal::error());
            mounted=false;(void)f_mount(nullptr,"",0);
        } else {
            // Replay bypasses FatFs. Throw away its cached metadata before
            // letting readers or the USB host see the recovered filesystem.
            (void)f_mount(nullptr,"",0);
            mounted=fail(f_mount(&filesystem,"",1));
            if(mounted) recovery_required=false;
        }
    }
    ++generation;
    ++media_epoch;
    return mounted;
}
bool ready() { return mounted && !usb; }
const char* error() { return problem; }
bool exists(const char* path) {
    if(!available()) return false;
    FILINFO info;
    return f_stat(path, &info) == FR_OK;
}
u32 revision() { return generation; }
bool content_stamp(const char* path,u32& stamp) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!path || !available()) return false;
    FIL file;
    FRESULT result=f_open(&file,path,FA_READ);
    if(result!=FR_OK) return fail(result);
    const u32 before=media_epoch;
    u32 crc=0xFFFFFFFFU;
    const auto append=[&](u8 byte) {
        crc^=byte;
        for(unsigned bit=0;bit<8;++bit) crc=(crc>>1)^((crc&1)?0xEDB88320U:0);
    };
    for(const char* p=path;*p;++p) append((u8)*p);
    u8 buffer[512];UINT count=0;
    do {
        result=f_read(&file,buffer,sizeof(buffer),&count);
        if(result!=FR_OK) break;
        for(unsigned i=0;i<count;++i) append(buffer[i]);
    } while(count);
    const FRESULT closed=f_close(&file);
    if(result!=FR_OK || closed!=FR_OK || before!=media_epoch) return false;
    stamp=(crc^0xFFFFFFFFU) ^ (before*0x9E3779B9U);
    return true;
}
bool space(u64& total,u64& free) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!available()) return false;
    DWORD clusters;FATFS* fs;
    if(!fail(f_getfree("",&clusters,&fs))) return false;
    total=(u64)(fs->n_fatent-2)*fs->csize*512;free=(u64)clusters*fs->csize*512;return true;
}
bool stat(const char* path, Entry& out) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!available()) return false;
    FILINFO info;
    if(!fail(f_stat(path, &info))) return false;
    out = {};
    std::snprintf(out.name, sizeof(out.name), "%s", info.fname);
    out.directory = (info.fattrib & AM_DIR) != 0;
    out.size = info.fsize > UINT32_MAX ? UINT32_MAX : (u32)info.fsize;
    return true;
}
bool read_range(const char* path, u32 offset, u8* out, unsigned count, unsigned& used) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used = 0;
    if(!available() || (!out && count)) return false;
    FIL file;
    FRESULT result = f_open(&file, path, FA_READ);
    if(result != FR_OK) return fail(result);
    if(offset < f_size(&file)) {
        result = f_lseek(&file, offset);
        UINT got = 0;
        if(result == FR_OK) result = f_read(&file, out, count, &got);
        used = got;
    }
    const FRESULT closed = f_close(&file);
    return fail(result == FR_OK ? closed : result);
}
bool list(const char* path, unsigned skip, Entry* out, unsigned capacity, unsigned& used, bool& more,const char* filter) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used = 0; more = false;
    if(!available()) return false;
    DIR directory;
    FRESULT result = f_opendir(&directory, path);
    if(result != FR_OK) return fail(result);
    FILINFO info;
    while((result = f_readdir(&directory, &info)) == FR_OK && info.fname[0]) {
        if(info.fname[0] == '.' || storage_journal::reserved(info.fname)) continue;
        if(!contains(info.fname,filter)) continue;
        if(skip) { --skip; continue; }
        if(used == capacity) { more = true; break; }
        auto& entry = out[used++];
        std::snprintf(entry.name, sizeof(entry.name), "%s", info.fname);
        entry.directory = (info.fattrib & AM_DIR) != 0;
        entry.size = info.fsize > UINT32_MAX ? UINT32_MAX : (u32)info.fsize;
    }
    const FRESULT closed = f_closedir(&directory);
    return fail(result == FR_OK ? closed : result);
}
bool read(const char* path, u8* out, unsigned capacity, unsigned& used) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used = 0;
    if(!available()) return false;
    FIL file;
    FRESULT result = f_open(&file, path, FA_READ);
    if(result != FR_OK) return fail(result);
    if(f_size(&file) > capacity) {
        f_close(&file); std::snprintf(problem, sizeof(problem), "File exceeds editor capacity"); return false;
    }
    UINT count = 0;
    result = f_read(&file, out, (UINT)f_size(&file), &count);
    used = count;
    const FRESULT closed = f_close(&file);
    return fail(result == FR_OK ? closed : result);
}
bool read_buffer(const char* path, shared_memory::Buffer& out, unsigned& used) {
    if(out.data()) return read(path,out.data(),out.size(),used);
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used=0;
    if(!out.ok() || !available()) return false;
    FIL file;FRESULT result=f_open(&file,path,FA_READ);
    if(result!=FR_OK) return fail(result);
    const auto size=f_size(&file);
    if(size>out.size()) { f_close(&file);std::snprintf(problem,sizeof(problem),"File exceeds buffer capacity");return false; }
    u8 chunk[1024];
    while(used<size) {
        UINT count=0;const unsigned remaining=(unsigned)(size-used);
        result=f_read(&file,chunk,remaining<sizeof(chunk)?remaining:sizeof(chunk),&count);
        if(result!=FR_OK || !count) { if(result==FR_OK) result=FR_INT_ERR;break; }
        if(!out.write(used,chunk,count)) { result=FR_DISK_ERR;break; }
        used+=count;diagnostics::feed_watchdog();
    }
    const auto closed=f_close(&file);return fail(result==FR_OK?closed:result);
}
bool read_text(const char* path, char* out, unsigned capacity, unsigned& used) {
    if(!out || !capacity) { used=0;return false; }
    struct Output { char* bytes;unsigned at=0; } output{out};
    const bool ok=read_text_stream(path,[](void* raw,const u8* bytes,unsigned n) {
        auto& out=*(Output*)raw;std::memcpy(out.bytes+out.at,bytes,n);out.at+=n;return true;
    },&output,capacity,used);
    out[used]=0;return ok;
}
bool read_text_stream(const char* path,bool (*write)(void*,const u8*,unsigned),
                      void* context,unsigned capacity,unsigned& used) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used = 0;
    if(!available() || !write || capacity == 0) return false;
    FIL file;
    FRESULT result = f_open(&file, path, FA_READ);
    if(result != FR_OK) return fail(result);
    u8 chunk[512],decoded[512];unsigned buffered=0;
    UINT count;
    u32 codepoint = 0, minimum = 0;
    unsigned remaining = 0;
    bool cr = false, valid = true;
    do {
        result = f_read(&file, chunk, sizeof(chunk), &count);
        if(result != FR_OK) break;
        for(unsigned i = 0; i < count && valid; ++i) {
            const u8 ch = chunk[i];
            if(remaining) {
                if((ch & 0xC0) != 0x80) { valid = false; break; }
                codepoint = (codepoint << 6) | (ch & 63);
                if(--remaining) continue;
                if(codepoint < minimum || (codepoint >= 0xD800 && codepoint <= 0xDFFF)) { valid = false; break; }
            } else if(ch >= 0xC2 && ch <= 0xDF) { remaining = 1; codepoint = ch & 31; minimum = 0x80; continue; }
            else if(ch >= 0xE0 && ch <= 0xEF) { remaining = 2; codepoint = ch & 15; minimum = 0x800; continue; }
            else if(ch >= 128) { valid = false; break; }
            else codepoint = ch;
            if(codepoint == 0xFEFF && used == 0) continue;
            if(codepoint == '\n' && cr) { cr = false; continue; }
            cr = codepoint == '\r';
            if(cr) codepoint = '\n';
            u8 m8 = 0;
            if(codepoint == 0 || !mk8::from_codepoint(codepoint, m8) || used + 1 >= capacity) { valid = false; break; }
            decoded[buffered++]=m8;++used;
            if(buffered==sizeof(decoded)) {
                const bool accepted=write(context,decoded,buffered);buffered=0;
                if(!accepted) { valid=false;break; }
            }
        }
    } while(count && valid);
    const FRESULT closed = f_close(&file);
    if(buffered && !write(context,decoded,buffered)) valid=false;
    if(result != FR_OK) return fail(result);
    if(!valid || remaining) { std::snprintf(problem, sizeof(problem), "Invalid UTF-8/M8 character or source too large"); return false; }
    return fail(closed);
}
namespace {
struct TextStream {
    FIL& file;
    u8 bytes[512]{};
    unsigned at=0,count=0;
    u32 physical=0,logical=0;
    FRESULT result=FR_OK;
    bool valid=true;
    int byte() {
        if(at==count) {
            UINT n=0;result=f_read(&file,bytes,sizeof(bytes),&n);count=n;at=0;
            if(result!=FR_OK) { valid=false;return -1; }
            if(!count) return -1;
        }
        ++physical;return bytes[at++];
    }
    int next(u8& value) {
        for(;;) {
            const int first=byte();if(first<0) return valid?0:-1;
            u32 cp=(u8)first,minimum=0;unsigned remaining=0;
            if(cp>=0xC2 && cp<=0xDF) { remaining=1;minimum=0x80;cp&=31; }
            else if(cp>=0xE0 && cp<=0xEF) { remaining=2;minimum=0x800;cp&=15; }
            else if(cp>=128) { valid=false;return -1; }
            while(remaining--) {
                const int part=byte();
                if(part<0 || (part&0xC0)!=0x80) { valid=false;return -1; }
                cp=(cp<<6)|(part&63);
            }
            if(cp<minimum || (cp>=0xD800 && cp<=0xDFFF)) { valid=false;return -1; }
            if(cp==0xFEFF && !logical) continue;
            if(!cp || !mk8::from_codepoint(cp,value)) { valid=false;return -1; }
            ++logical;return 1;
        }
    }
};
bool cache_text(const char* path) {
    if(!available()) return false;
    if(text_cache.valid && text_cache.generation==generation && !std::strcmp(text_cache.path,path)) return true;
    text_cache.valid=false;text_cache.window_size=0;
    if(!path || std::strlen(path)>=PATH_SIZE) return fail(FR_INVALID_NAME);
    FIL file;FRESULT result=f_open(&file,path,FA_READ);
    if(result!=FR_OK) return fail(result);
    TextStream reader{file};text_cache.index[0]=0;
    if(f_size(&file)>196608) reader.valid=false;
    u8 value=0;
    while(reader.valid && reader.next(value)>0) {
        if(reader.logical>65534) { reader.valid=false;break; }
        if(!(reader.logical%512)) text_cache.index[reader.logical/512]=reader.physical;
    }
    result=reader.result;const FRESULT closed=f_close(&file);
    if(result!=FR_OK || closed!=FR_OK) return fail(result!=FR_OK?result:closed);
    if(!reader.valid) { std::snprintf(problem,sizeof(problem),"Invalid UTF-8/M8 character or source too large");return false; }
    std::strcpy(text_cache.path,path);text_cache.length=(u16)reader.logical;
    text_cache.generation=generation;text_cache.valid=true;return fail(FR_OK);
}
bool text_window(u16 logical) {
    const unsigned start=logical/512*512;
    const unsigned length=text_cache.length-start<512?text_cache.length-start:512;
    const u32 position=text_cache.index[start/512];
    text_cache.window_size=0;
    FIL file;FRESULT result=f_open(&file,text_cache.path,FA_READ);
    if(result!=FR_OK) return fail(result);
    result=f_lseek(&file,position);
    TextStream reader{file};reader.physical=position;reader.logical=start;
    if(result==FR_OK) for(unsigned i=0;i<length;++i) if(reader.next(text_cache.window[i])!=1) { reader.valid=false;break; }
    const FRESULT closed=f_close(&file);
    if(result==FR_OK) result=reader.result;
    if(result!=FR_OK || closed!=FR_OK || !reader.valid) {
        text_cache.valid=false;return fail(result!=FR_OK?result:closed!=FR_OK?closed:FR_DISK_ERR);
    }
    text_cache.window_start=(u16)start;text_cache.window_size=(u16)length;return true;
}
bool replace_file(const char* path,const char* temporary) {
    char backup[PATH_SIZE];FILINFO info;
    const FRESULT status=f_stat(path,&info);
    if((status==FR_OK && (info.fattrib&AM_DIR)) || (status!=FR_OK && status!=FR_NO_FILE)) {
        f_unlink(temporary);return fail(status==FR_OK?FR_DENIED:status);
    }
    const bool replace=status==FR_OK;
    FRESULT result=FR_OK;
    if(replace) {
        if(!private_name(path,"BAK",backup)) { f_unlink(temporary);return false; }
        result=f_rename(path,backup);
        if(result!=FR_OK) { f_unlink(temporary);return fail(result); }
    }
    result=f_rename(temporary,path);
    if(result!=FR_OK) {
        if(replace) (void)f_rename(backup,path);
        f_unlink(temporary);return fail(result);
    }
    if(replace) (void)f_unlink(backup);
    ++generation;return fail(FR_OK);
}
}
bool text_size(const char* path,unsigned& size) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    size=0;if(!cache_text(path)) return false;size=text_cache.length;return true;
}
bool read_text_range(const char* path,u32 offset,u8* out,unsigned count,unsigned& used) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    used=0;if((count && !out) || !cache_text(path)) return false;
    while(used<count && offset<text_cache.length) {
        if(offset<text_cache.window_start || offset>=text_cache.window_start+text_cache.window_size)
            if(!text_window((u16)offset)) return false;
        unsigned n=text_cache.window_start+text_cache.window_size-offset;
        if(n>count-used) n=count-used;
        std::memcpy(out+used,text_cache.window+offset-text_cache.window_start,n);used+=n;offset+=n;
    }
    return true;
}
static bool write_impl(const char* path, const u8* data, unsigned size, bool text) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!path || (size && !data) || storage_journal::reserved(path)) return fail(FR_INVALID_NAME);
    if(!start_transaction()) return false;
    char temporary[PATH_SIZE];
    if(!private_name(path, "TMP", temporary)) return finish_transaction(false);
    FIL file;
    FRESULT result = f_open(&file, temporary, FA_WRITE | FA_CREATE_NEW);
    if(result != FR_OK) { fail(result);return finish_transaction(false); }
    for(unsigned at = 0; at < size && result == FR_OK;) {
        u8 chunk[768];
        unsigned count = 0;
        const unsigned end = at + 256 < size ? at + 256 : size;
        while(at < end) {
            const u8 byte = data[at++];
            const u32 cp = text ? mk8::codepoint(byte) : byte;
            if(!text || cp < 0x80) chunk[count++] = (u8)cp;
            else if(cp < 0x800) { chunk[count++] = 0xC0 | (cp >> 6); chunk[count++] = 0x80 | (cp & 63); }
            else { chunk[count++] = 0xE0 | (cp >> 12); chunk[count++] = 0x80 | ((cp >> 6) & 63); chunk[count++] = 0x80 | (cp & 63); }
        }
        UINT written = 0;
        result = f_write(&file, chunk, count, &written);
        if(result == FR_OK && written != count) result = FR_DISK_ERR;
    }
    if(result == FR_OK) result = f_sync(&file);
    const FRESULT closed = f_close(&file);
    if(result == FR_OK) result = closed;
    if(result != FR_OK) { fail(result);return finish_transaction(false); }
    return finish_transaction(replace_file(path,temporary));
}
bool write(const char* path, const u8* data, unsigned size) { return write_impl(path, data, size, false); }
bool write_text(const char* path, const char* data, unsigned size) { return write_impl(path, (const u8*)data, size, true); }
WriteSession* begin_write(const char* path,bool m8) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!available() || writer || !path || std::strlen(path)>=PATH_SIZE || storage_journal::reserved(path)) return nullptr;
    auto* value=new(std::nothrow) WriteSession;
    if(!value) { std::snprintf(problem,sizeof(problem),"Not enough transfer memory");return nullptr; }
    if(!start_transaction()) { delete value;return nullptr; }
    if(!private_name(path,"TMP",value->temporary)) { finish_transaction(false);delete value;return nullptr; }
    const FRESULT result=f_open(&value->file,value->temporary,FA_WRITE|FA_CREATE_NEW);
    if(result!=FR_OK) { fail(result);finish_transaction(false);delete value;return nullptr; }
    std::strcpy(value->path,path);value->text=m8;value->open=true;value->revision=generation;writer=value;return value;
}
bool append_write(WriteSession* value,const u8* data,unsigned size) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!value || !value->open || value->revision!=generation || usb || (size && !data)) return false;
    for(unsigned at=0;at<size;) {
        u8 chunk[768];unsigned count=0;
        const unsigned end=at+256<size?at+256:size;
        while(at<end) {
            const u8 byte=data[at++];
            if(value->text && !mk8::valid_byte(byte)) { abort_write(value);return fail(FR_INVALID_PARAMETER); }
            const auto utf8=mk8::utf8(byte);
            if(!value->text) chunk[count++]=byte;
            else for(unsigned i=0;i<utf8.size;++i) chunk[count++]=utf8.data[i];
        }
        UINT written=0;const FRESULT result=f_write(&value->file,chunk,count,&written);
        if(result!=FR_OK || written!=count) { abort_write(value);return fail(result!=FR_OK?result:FR_DISK_ERR); }
    }
    return true;
}
void cancel_write(WriteSession*& value) { abort_write(value);delete value;value=nullptr; }
bool commit_write(WriteSession*& value) {
    diagnostics::Scope measure(diagnostics::Point::STORAGE);
    if(!value || !value->open || value->revision!=generation || usb) { cancel_write(value);return false; }
    FRESULT result=f_sync(&value->file);const FRESULT closed=f_close(&value->file);
    if(result==FR_OK) result=closed;
    value->open=false;writer=nullptr;
    bool ok=false;
    if(result==FR_OK) ok=replace_file(value->path,value->temporary);
    else fail(result);
    ok=finish_transaction(ok);
    delete value;value=nullptr;return ok;
}
bool mkdir(const char* path) {
    if(storage_journal::reserved(path)) return fail(FR_INVALID_NAME);
    if(!start_transaction() || !finish_transaction(fail(f_mkdir(path)))) return false;
    ++generation;return true;
}
bool remove(const char* path) {
    if(storage_journal::reserved(path)) return fail(FR_DENIED);
    if(!start_transaction() || !finish_transaction(fail(f_unlink(path)))) return false;
    ++generation;return true;
}
bool rename(const char* from,const char* to) {
    if(storage_journal::reserved(from) || storage_journal::reserved(to)) return fail(FR_DENIED);
    if(!start_transaction() || !finish_transaction(fail(f_rename(from,to)))) return false;
    ++generation;return true;
}
bool usb_active() { return usb; }
bool usb_ejected() { return ejected; }
void usb_eject() { if(usb) { (void)sd::sync(); ejected = true; } }
bool begin_usb() {
    if(usb) return true;
    if(!sd::ready() && !sd::init()) return fail(FR_NOT_READY);
    abort_write(writer);
    if(recovery_required && !mount()) return false;
    if(!sd::sync()) return fail(FR_DISK_ERR);
    (void)f_mount(nullptr, "", 0);
    mounted = false; ejected = false; usb = true;
    ++generation;++media_epoch;
    return true;
}
bool end_usb() {
    if(!usb) return true;
    if(!ejected) { std::snprintf(problem, sizeof(problem), "Eject the USB disk on the computer"); return false; }
    usb = false;
    return mount();
}
bool format() {
    if(usb || (!sd::ready() && !sd::init())) return fail(FR_NOT_READY);
    abort_write(writer);
    storage_journal::reset();recovery_required=false;
    (void)f_mount(nullptr, "", 0); mounted = false;
    u8 workspace[4096];
    MKFS_PARM options{};
    options.fmt = FM_ANY;
    if(!fail(f_mkfs("", &options, workspace, sizeof(workspace)))) return false;
    return mount();
}
} } // namespace picocalc::files
