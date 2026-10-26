#ifndef MK61_FAT_CLUSTER_CHAIN_HPP
#define MK61_FAT_CLUSTER_CHAIN_HPP

#include "rust_types.h"

namespace fat_cluster_chain {

// C9 mapping is an immutable sequence, published by a single catalog pointer.
// It is independent of file IDs and uses no inode for continuation clusters.
static constexpr u16 FIRST_CLUSTER = 2;
static constexpr u16 MAX_CLUSTERS = 4084;
static constexpr u16 HEADER_BYTES = 16;
static constexpr u16 MAX_RECORD_BYTES = 4080;
static constexpr u16 MAX_CHAIN_LENGTH =
    (MAX_RECORD_BYTES - HEADER_BYTES) / sizeof(u16);
static constexpr usize BITMAP_BYTES = (MAX_CLUSTERS + 7U) / 8U;

struct Source {
  void* context;
  bool (*cluster)(void* context, u16 index, u16& value);
};

struct Reader {
  void* context;
  bool (*read)(void* context, u32 offset, u8* output, usize size);
};

struct Plan {
  u16 owner;
  u16 count;
  u32 crc;
};

struct Workspace {
  u8 seen[BITMAP_BYTES];
};

// Source must remain stable until the immutable record is written and verified.
// On failure output is cleared and no allocation/publication is performed.
bool prepare(u16 owner, u16 count, u16 cluster_capacity,
             const Source& source, Workspace& workspace, Plan& output);
u16 encoded_size(const Plan& plan);
bool read_encoded(const Plan& plan, const Source& source, u32 offset,
                  u8* output, usize size);
// record_bytes is the actual bounded record length, not a header-declared size.
bool verify(const Reader& reader, u16 record_bytes, u16 owner,
            u16 cluster_capacity, Workspace& workspace, Plan& output);
bool read_cluster(const Reader& reader, const Plan& plan,
                  u16 index, u16& output);

} // namespace fat_cluster_chain
#endif
