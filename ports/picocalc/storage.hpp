#ifndef MK61_PICOCALC_STORAGE_HPP
#define MK61_PICOCALC_STORAGE_HPP
#include "rust_types.h"
namespace shared_memory { class Buffer; }

namespace picocalc {
namespace sd {
struct Statistics { bool dma;u32 reads,writes,dma_transfers,hardware_crc,crc_errors; };
Statistics statistics();
bool init();
bool ready();
u32 sectors();
bool read(u32 sector, u8 out[512]);
bool read_sectors(u32 sector, u8* out, u32 count);
bool write(u32 sector, const u8 data[512]);
bool read_bytes(u32 sector, u32 offset, u8* out, u32 count);
bool write_bytes(u32 sector, u32 offset, const u8* data, u32 count);
bool sync();
}
namespace files {
constexpr unsigned PATH_SIZE = 384;
struct Entry { char name[256]; bool directory; u32 size; };
bool mount();
bool ready();
const char* error();
bool list(const char* path, unsigned skip, Entry* out, unsigned capacity, unsigned& used, bool& more,
          const char* filter=nullptr);
bool read(const char* path, u8* out, unsigned capacity, unsigned& used);
bool read_buffer(const char* path, shared_memory::Buffer& out, unsigned& used);
bool read_text(const char* path, char* out, unsigned capacity, unsigned& used);
bool text_size(const char* path,unsigned& size);
bool read_text_range(const char* path,u32 offset,u8* out,unsigned count,unsigned& used);
struct WriteSession;
WriteSession* begin_write(const char* path,bool m8=false);
bool append_write(WriteSession* session,const u8* data,unsigned size);
bool commit_write(WriteSession*& session);
void cancel_write(WriteSession*& session);
bool write(const char* path, const u8* data, unsigned size);
bool write_text(const char* path, const char* data, unsigned size);
bool mkdir(const char* path);
bool remove(const char* path);
bool rename(const char* from, const char* to);
bool exists(const char* path);
bool stat(const char* path, Entry& out);
u32 revision();
bool content_stamp(const char* path,u32& stamp);
bool space(u64& total,u64& free);
bool read_range(const char* path, u32 offset, u8* out, unsigned count, unsigned& used);
bool begin_usb();
bool end_usb();
bool usb_active();
bool usb_ejected();
void usb_eject();
bool format();
}
} // namespace picocalc
#endif
