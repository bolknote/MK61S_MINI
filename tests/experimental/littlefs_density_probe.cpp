// Host-only littlefs comparison. The NOR exists only in this process's RAM.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <algorithm>
extern "C" {
#include "lfs.h"
}
#include "../../code/storage_geometry.hpp"
struct Nor {
  std::vector<uint8_t> bytes;
  std::vector<uint32_t> wear;
  uint64_t reads = 0, read_bytes = 0, programs = 0, program_bytes = 0, erases = 0;
};
static int rd(const lfs_config* cfg, lfs_block_t block, lfs_off_t off, void* data, lfs_size_t size) {
  auto& n = *(Nor*) cfg->context;
  assert(block < cfg->block_count && off + size <= cfg->block_size);
  memcpy(data, n.bytes.data() + block * 4096U + off, size);
  ++n.reads; n.read_bytes += size; return 0;
}
static int pg(const lfs_config* cfg, lfs_block_t block, lfs_off_t off, const void* data, lfs_size_t size) {
  auto& n = *(Nor*) cfg->context;
  assert(block < cfg->block_count && off + size <= cfg->block_size);
  const auto* src = (const uint8_t*) data;
  for(unsigned i = 0; i < size; ++i) {
    auto& value = n.bytes[block * 4096U + off + i];
    assert((value & src[i]) == src[i]); value &= src[i];
  }
  ++n.programs; n.program_bytes += size; return 0;
}
static int er(const lfs_config* cfg, lfs_block_t block) {
  auto& n = *(Nor*) cfg->context; assert(block < cfg->block_count);
  memset(n.bytes.data() + block * 4096U, 0xFF, 4096);
  ++n.wear[block]; ++n.erases; return 0;
}
static int sy(const lfs_config*) { return 0; }
static void put16(uint8_t* dst, unsigned value) { dst[0] = value; dst[1] = value >> 8U; }
static void run(unsigned capacity, unsigned payload) {
  storage_geometry::Geometry geometry;
  assert(storage_geometry::compute(capacity, geometry));
  // Both candidates retain identical locator/settings/staging/projection
  // reserves. C9's own catalog reserve is available to littlefs metadata.
  const unsigned blocks = geometry.catalog_bank_sectors * 2U + geometry.data_sector_count;
  Nor nor; nor.bytes.assign(blocks * 4096U, 0xFF); nor.wear.assign(blocks, 0);
  uint8_t read_cache[512], prog_cache[512], lookahead[32], file_cache[512];
  lfs_config cfg = {};
  cfg.context = &nor; cfg.read = rd; cfg.prog = pg; cfg.erase = er; cfg.sync = sy;
  cfg.read_size = 16; cfg.prog_size = 256; cfg.block_size = 4096; cfg.block_count = blocks;
  cfg.block_cycles = 128; cfg.cache_size = 512; cfg.lookahead_size = sizeof(lookahead);
  cfg.read_buffer = read_cache; cfg.prog_buffer = prog_cache; cfg.lookahead_buffer = lookahead;
  cfg.name_max = 31; cfg.file_max = 20544; cfg.attr_max = 1022;
  cfg.inline_max = 512;
  lfs_t fs = {}; assert(lfs_format(&fs, &cfg) == 0); assert(lfs_mount(&fs, &cfg) == 0);
  assert(lfs_mkdir(&fs, "Dense") == 0);
  const unsigned cluster_bytes = (unsigned) geometry.sectors_per_cluster * 512U;
  const unsigned chain = (payload + cluster_bytes - 1U) / cluster_bytes;
  std::vector<uint8_t> bytes(payload);
  std::vector<uint8_t> mapping(16U + 2U * chain, 0);
  memcpy(mapping.data(), "F9CH", 4); mapping[4] = 1; put16(mapping.data() + 8, chain);
  std::vector<uint8_t> directory_mapping(1022, 0);
  unsigned files = 0;
  int result = 0;
  for(; files + 1U < geometry.max_nodes; ++files) {
    const unsigned directory_clusters = (2U + (files + 1U) * 2U +
        16U * geometry.sectors_per_cluster - 1U) / (16U * geometry.sectors_per_cluster);
    if((files + 1U) * chain + directory_clusters > storage_geometry::fat_cluster_capacity(geometry)) break;
    char path[32]; snprintf(path, sizeof(path), "Dense/F%04u", files);
    for(unsigned i = 0; i < payload; ++i) bytes[i] = (uint8_t) (files + i * 37U + (i >> 8U));
    put16(mapping.data() + 6, files + 1U);
    for(unsigned i = 0; i < chain; ++i) put16(mapping.data() + 16U + i * 2U, 2U + files * chain + i);
    lfs_attr attrs[] = {{0x90, mapping.data(), (lfs_size_t) mapping.size()}};
    lfs_file_config fc = {}; fc.buffer = file_cache; fc.attrs = attrs; fc.attr_count = 1;
    lfs_file_t file = {};
    result = lfs_file_opencfg(&fs, &file, path, LFS_O_WRONLY | LFS_O_CREAT | LFS_O_EXCL, &fc);
    if(result != 0) break;
    const lfs_ssize_t written = lfs_file_write(&fs, &file, bytes.data(), payload);
    result = lfs_file_close(&fs, &file);
    if(written != (lfs_ssize_t) payload || result != 0) break;
    // Include persistent directory mapping storage, with the same 16-byte
    // header and uint16 cluster-list budget as C9. This probe compares space
    // and I/O only; it does not implement the FAT frontend or atomic ID reuse.
    result = lfs_setattr(&fs, "Dense", 0x90, directory_mapping.data(), 16U + directory_clusters * 2U);
    if(result != 0) break;
  }
  assert(result == 0 || result == LFS_ERR_NOSPC);
  assert(lfs_unmount(&fs) == 0 && lfs_mount(&fs, &cfg) == 0);
  // Verify the committed prefix after a fresh mount, independent of counters.
  for(unsigned i = 0; i < files; ++i) {
    char path[32]; snprintf(path, sizeof(path), "Dense/F%04u", i);
    lfs_file_config fc = {}; fc.buffer = file_cache;
    lfs_file_t file = {}; assert(lfs_file_opencfg(&fs, &file, path, LFS_O_RDONLY, &fc) == 0);
    std::vector<uint8_t> readback(payload);
    assert(lfs_file_read(&fs, &file, readback.data(), payload) == (lfs_ssize_t) payload);
    for(unsigned j = 0; j < payload; ++j) assert(readback[j] == (uint8_t) (i + j * 37U + (j >> 8U)));
    assert(lfs_file_close(&fs, &file) == 0);
  }
  const uint32_t peak = *std::max_element(nor.wear.begin(), nor.wear.end());
  printf("littlefs,%u,%u,%u,%llu,%llu,%llu,%u,%zu\n", capacity, payload, files,
      (unsigned long long) nor.read_bytes, (unsigned long long) nor.program_bytes,
      (unsigned long long) nor.erases, peak,
      sizeof(fs) + sizeof(read_cache) + sizeof(prog_cache) + sizeof(lookahead) + sizeof(file_cache));
  fflush(stdout); assert(lfs_unmount(&fs) == 0);
}
int main() {
  puts("backend,capacity,payload,files,read_bytes,program_bytes,erases,peak_erase,working_bytes");
  for(unsigned cap : {512U * 1024U, 16U * 1024U * 1024U})
    for(unsigned size : {0U, 1U, 100U, 500U, 512U, 513U, 1536U, 4096U, 20544U}) run(cap, size);
}
