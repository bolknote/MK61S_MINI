#include "fat_cluster_chain.hpp"

#include "crc32.hpp"

#include <string.h>


namespace fat_cluster_chain {
namespace {

static u16 get16(const u8* bytes) {
  return (u16) ((u16) bytes[0] | ((u16) bytes[1] << 8));
}
static u32 get32(const u8* bytes) {
  return (u32) bytes[0] | ((u32) bytes[1] << 8) |
         ((u32) bytes[2] << 16) | ((u32) bytes[3] << 24);
}
static void put16(u8* bytes, u16 value) {
  bytes[0] = (u8) value;
  bytes[1] = (u8) (value >> 8);
}
static void put32(u8* bytes, u32 value) {
  for(u8 index = 0; index < 4; ++index) bytes[index] = (u8) (value >> (index * 8));
}
static bool valid_shape(u16 owner, u16 count, u16 capacity) {
  return owner != 0xFFFFU && capacity != 0 && capacity <= MAX_CLUSTERS &&
         count <= capacity && count <= MAX_CHAIN_LENGTH;
}
static void header(const Plan& plan, u8* bytes) {
  memset(bytes, 0, HEADER_BYTES);
  memcpy(bytes, "F9CH", 4);
  bytes[4] = 1;
  put16(bytes + 6, plan.owner);
  put16(bytes + 8, plan.count);
  put32(bytes + 12, plan.crc);
}
static bool mark(Workspace& workspace, u16 capacity, u16 cluster) {
  if(cluster < FIRST_CLUSTER || cluster - FIRST_CLUSTER >= capacity) return false;
  const u16 index = (u16) (cluster - FIRST_CLUSTER);
  const u8 bit = (u8) (1U << (index & 7U));
  if((workspace.seen[index >> 3] & bit) != 0) return false;
  workspace.seen[index >> 3] |= bit;
  return true;
}

} // namespace

u16 encoded_size(const Plan& plan) {
  if(plan.count > MAX_CHAIN_LENGTH) return 0;
  return (u16) (HEADER_BYTES + plan.count * sizeof(u16));
}

bool prepare(u16 owner, u16 count, u16 cluster_capacity,
             const Source& source, Workspace& workspace, Plan& output) {
  output = {};
  if(!valid_shape(owner, count, cluster_capacity) ||
     (count != 0 && source.cluster == nullptr)) return false;
  memset(workspace.seen, 0, sizeof(workspace.seen));
  Plan pending = {owner, count, 0};
  u8 bytes[HEADER_BYTES];
  header(pending, bytes);
  mk61_crc32::Context crc;
  if(!crc.update(bytes, 12)) return false;
  for(u16 index = 0; index < count; ++index) {
    u16 cluster = 0;
    if(!source.cluster(source.context, index, cluster) ||
       !mark(workspace, cluster_capacity, cluster)) return false;
    put16(bytes, cluster);
    if(!crc.update(bytes, sizeof(u16))) return false;
  }
  pending.crc = crc.finish();
  output = pending;
  return true;
}

bool read_encoded(const Plan& plan, const Source& source, u32 offset,
                  u8* output, usize size) {
  const u16 total = encoded_size(plan);
  if(total == 0 || offset > total || size > total - offset ||
     (size != 0 && output == nullptr) ||
     (plan.count != 0 && source.cluster == nullptr)) return false;
  u8 bytes[HEADER_BYTES];
  header(plan, bytes);
  usize copied = 0;
  while(copied < size && offset < HEADER_BYTES) {
    output[copied++] = bytes[offset++];
  }
  while(copied < size) {
    const u32 payload = offset - HEADER_BYTES;
    const u16 index = (u16) (payload / sizeof(u16));
    u16 cluster = 0;
    if(index >= plan.count ||
       !source.cluster(source.context, index, cluster)) return false;
    put16(bytes, cluster);
    const u8 first = (u8) (payload & 1U);
    for(u8 byte = first; byte < sizeof(u16) && copied < size; ++byte) {
      output[copied++] = bytes[byte];
      ++offset;
    }
  }
  return true;
}

bool verify(const Reader& reader, u16 record_bytes, u16 owner,
            u16 cluster_capacity, Workspace& workspace, Plan& output) {
  output = {};
  if(reader.read == nullptr || record_bytes < HEADER_BYTES ||
     record_bytes > MAX_RECORD_BYTES) return false;
  u8 bytes[HEADER_BYTES];
  if(!reader.read(reader.context, 0, bytes, sizeof(bytes)) ||
     memcmp(bytes, "F9CH", 4) != 0 || bytes[4] != 1 || bytes[5] != 0 ||
     get16(bytes + 10) != 0) return false;
  Plan pending = {get16(bytes + 6), get16(bytes + 8), get32(bytes + 12)};
  if(pending.owner != owner || !valid_shape(owner, pending.count, cluster_capacity) ||
     encoded_size(pending) != record_bytes) return false;
  memset(workspace.seen, 0, sizeof(workspace.seen));
  mk61_crc32::Context crc;
  if(!crc.update(bytes, 12)) return false;
  for(u16 index = 0; index < pending.count; ++index) {
    if(!reader.read(reader.context, HEADER_BYTES + (u32) index * sizeof(u16),
                    bytes, sizeof(u16)) ||
       !mark(workspace, cluster_capacity, get16(bytes)) ||
       !crc.update(bytes, sizeof(u16))) return false;
  }
  if(crc.finish() != pending.crc) return false;
  output = pending;
  return true;
}

bool read_cluster(const Reader& reader, const Plan& plan,
                  u16 index, u16& output) {
  output = 0;
  if(reader.read == nullptr || index >= plan.count ||
     plan.count > MAX_CHAIN_LENGTH) return false;
  u8 bytes[sizeof(u16)];
  if(!reader.read(reader.context, HEADER_BYTES + (u32) index * sizeof(u16),
                  bytes, sizeof(bytes))) return false;
  output = get16(bytes);
  return true;
}

} // namespace fat_cluster_chain
