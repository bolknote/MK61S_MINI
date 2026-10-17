#include "storage.hpp"
#include "mk8_codec.hpp"
#include <cstdio>
#include <cstring>
extern "C" {
#include "ff.h"
}

namespace picocalc { namespace files {
namespace {
FATFS filesystem;
bool mounted = false, usb = false, ejected = false;
u32 generation = 1;
char problem[64] = "No microSD mounted";
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
}
bool mount() {
    if(usb) return available();
    mounted = fail(f_mount(&filesystem, "", 1));
    ++generation;
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
bool space(u64& total,u64& free) {
    if(!available()) return false;
    DWORD clusters;FATFS* fs;
    if(!fail(f_getfree("",&clusters,&fs))) return false;
    total=(u64)(fs->n_fatent-2)*fs->csize*512;free=(u64)clusters*fs->csize*512;return true;
}
bool stat(const char* path, Entry& out) {
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
bool list(const char* path, unsigned skip, Entry* out, unsigned capacity, unsigned& used, bool& more) {
    used = 0; more = false;
    if(!available()) return false;
    DIR directory;
    FRESULT result = f_opendir(&directory, path);
    if(result != FR_OK) return fail(result);
    FILINFO info;
    while((result = f_readdir(&directory, &info)) == FR_OK && info.fname[0]) {
        if(info.fname[0] == '.') continue;
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
bool read_text(const char* path, char* out, unsigned capacity, unsigned& used) {
    used = 0;
    if(!available() || capacity == 0) return false;
    FIL file;
    FRESULT result = f_open(&file, path, FA_READ);
    if(result != FR_OK) return fail(result);
    u8 chunk[512];
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
            out[used++] = (char)m8;
        }
    } while(count && valid);
    const FRESULT closed = f_close(&file);
    out[used] = 0;
    if(result != FR_OK) return fail(result);
    if(!valid || remaining) { std::snprintf(problem, sizeof(problem), "Invalid UTF-8/M8 character or source too large"); return false; }
    return fail(closed);
}
static bool write_impl(const char* path, const u8* data, unsigned size, bool text) {
    if(!available()) return false;
    char temporary[PATH_SIZE], backup[PATH_SIZE];
    if(!private_name(path, "TMP", temporary)) return false;
    FIL file;
    FRESULT result = f_open(&file, temporary, FA_WRITE | FA_CREATE_NEW);
    if(result != FR_OK) return fail(result);
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
    if(result != FR_OK) { f_unlink(temporary); return fail(result); }
    const bool replace = exists(path);
    if(replace) {
        if(!private_name(path, "BAK", backup)) { f_unlink(temporary); return false; }
        result = f_rename(path, backup);
        if(result != FR_OK) { f_unlink(temporary); return fail(result); }
    }
    result = f_rename(temporary, path);
    if(result != FR_OK) {
        if(replace) (void)f_rename(backup, path);
        f_unlink(temporary);
        return fail(result);
    }
    if(replace) (void)f_unlink(backup);
    ++generation;
    return fail(FR_OK);
}
bool write(const char* path, const u8* data, unsigned size) { return write_impl(path, data, size, false); }
bool write_text(const char* path, const char* data, unsigned size) { return write_impl(path, (const u8*)data, size, true); }
bool mkdir(const char* path) { if(!available() || !fail(f_mkdir(path))) return false; ++generation; return true; }
bool remove(const char* path) { if(!available() || !fail(f_unlink(path))) return false; ++generation; return true; }
bool rename(const char* from, const char* to) { if(!available() || !fail(f_rename(from, to))) return false; ++generation; return true; }
bool usb_active() { return usb; }
bool usb_ejected() { return ejected; }
void usb_eject() { if(usb) { (void)sd::sync(); ejected = true; } }
bool begin_usb() {
    if(usb) return true;
    if(!sd::ready() && !sd::init()) return fail(FR_NOT_READY);
    if(!sd::sync()) return fail(FR_DISK_ERR);
    (void)f_mount(nullptr, "", 0);
    mounted = false; ejected = false; usb = true;
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
    (void)f_mount(nullptr, "", 0); mounted = false;
    u8 workspace[4096];
    MKFS_PARM options{};
    options.fmt = FM_ANY;
    if(!fail(f_mkfs("", &options, workspace, sizeof(workspace)))) return false;
    return mount();
}
} } // namespace picocalc::files
