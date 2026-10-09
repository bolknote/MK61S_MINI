#include "../code/fat_cluster_chain.hpp"
#include "experimental/fat12_layout_model.hpp"

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

using namespace fat_cluster_chain;

struct Clusters {
  std::vector<u16> values;
  int fail_at = -1;
};
static bool cluster_source(void* context, u16 index, u16& output) {
  Clusters& source = *(Clusters*) context;
  if(index >= source.values.size() || index == source.fail_at) return false;
  output = source.values[index];
  return true;
}
struct Bytes {
  std::vector<u8> values;
  int fail_at = -1;
};
static bool byte_reader(void* context, u32 offset, u8* output, usize size) {
  Bytes& source = *(Bytes*) context;
  if(offset > source.values.size() || size > source.values.size() - offset ||
     (source.fail_at >= 0 && offset <= (u32) source.fail_at &&
      size > (u32) source.fail_at - offset)) return false;
  if(size != 0) memcpy(output, source.values.data() + offset, size);
  return true;
}

static Bytes encode(const Plan& plan, Clusters& source, usize chunk) {
  Bytes output;
  output.values.resize(encoded_size(plan));
  for(usize offset = 0; offset < output.values.size(); offset += chunk) {
    const usize size = output.values.size() - offset < chunk
        ? output.values.size() - offset : chunk;
    assert(read_encoded(plan, {&source, cluster_source}, (u32) offset,
                        output.values.data() + offset, size));
  }
  return output;
}

static void golden_wire_and_boundaries() {
  // CRC was independently calculated with Python binascii.crc32.
  const u8 golden[] = {0x46,0x39,0x43,0x48,0x01,0x00,0x2a,0x00,
      0x03,0x00,0x00,0x00,0x0e,0x01,0x85,0x7d,0x02,0x00,0xff,0x01,0xda,0x03};
  Clusters source = {{2, 511, 986}, -1};
  Workspace workspace = {};
  Plan plan = {};
  assert(prepare(42, 3, 985, {&source, cluster_source}, workspace, plan));
  for(usize chunk : {1U, 2U, 3U, 7U, 16U, 64U}) {
    Bytes output = encode(plan, source, chunk);
    assert(output.values.size() == sizeof(golden));
    assert(memcmp(output.values.data(), golden, sizeof(golden)) == 0);
    Plan verified = {};
    assert(verify({&output, byte_reader}, sizeof(golden), 42, 985, workspace, verified));
    for(u16 index = 0; index < 3; ++index) {
      u16 cluster = 0;
      assert(read_cluster({&output, byte_reader}, verified, index, cluster));
      assert(cluster == source.values[index]);
    }
    u16 cluster = 1;
    assert(!read_cluster({&output, byte_reader}, verified, 3, cluster) && cluster == 0);
  }
  u8 sentinel = 0xAB;
  assert(read_encoded(plan, {&source, cluster_source}, sizeof(golden), nullptr, 0));
  assert(!read_encoded(plan, {&source, cluster_source}, sizeof(golden), &sentinel, 1));
  assert(!read_encoded(plan, {&source, cluster_source}, 0xFFFFFFFFU, &sentinel, 1));
  assert(sentinel == 0xAB);
}

static void damaged_and_torn_records() {
  Clusters source = {{2, 5, 986}, -1};
  Workspace workspace = {};
  Plan plan = {};
  assert(prepare(777, 3, 985, {&source, cluster_source}, workspace, plan));
  const Bytes original = encode(plan, source, 3);
  for(usize byte = 0; byte < original.values.size(); ++byte) {
    Bytes corrupt = original;
    corrupt.values[byte] ^= 0x80;
    Plan out = {12, 12, 12};
    assert(!verify({&corrupt, byte_reader}, (u16) corrupt.values.size(),
                   777, 985, workspace, out));
    assert(out.owner == 0 && out.count == 0 && out.crc == 0);
  }
  for(usize kept = 0; kept < original.values.size(); ++kept) {
    Bytes torn = original;
    torn.values.resize(kept);
    Plan out = {};
    assert(!verify({&torn, byte_reader}, (u16) original.values.size(),
                   777, 985, workspace, out));
  }
  for(int failed = 0; failed < (int) original.values.size(); ++failed) {
    Bytes failed_read = original;
    failed_read.fail_at = failed;
    Plan out = {};
    assert(!verify({&failed_read, byte_reader}, (u16) original.values.size(),
                   777, 985, workspace, out));
  }
  Bytes wrong = original;
  Plan out = {};
  assert(!verify({&wrong, byte_reader}, (u16) wrong.values.size(),
                 778, 985, workspace, out));
  assert(!verify({&wrong, byte_reader}, (u16) wrong.values.size(),
                 777, 984, workspace, out));
  wrong.values.push_back(0);
  assert(!verify({&wrong, byte_reader}, (u16) wrong.values.size(),
                 777, 985, workspace, out));
}

static void invalid_sources_and_long_chains() {
  Workspace workspace = {};
  Plan plan = {};
  for(Clusters source : {Clusters{{2,2},-1}, Clusters{{1,3},-1},
                          Clusters{{2,987},-1}, Clusters{{2,3},1}}) {
    assert(!prepare(42, 2, 985, {&source, cluster_source}, workspace, plan));
  }
  assert(!prepare(0xFFFFU, 0, 985, {nullptr,nullptr}, workspace, plan));
  assert(!prepare(0, 0, 0, {nullptr,nullptr}, workspace, plan));
  assert(prepare(42, 0, 985, {nullptr,nullptr}, workspace, plan));
  Clusters empty = {};
  Bytes empty_bytes = encode(plan, empty, 1);
  assert(verify({&empty_bytes, byte_reader}, HEADER_BYTES, 42, 985, workspace, plan));

  const u16 lengths[] = {41, 1281, MAX_CHAIN_LENGTH};
  for(u16 count : lengths) {
    Clusters source = {};
    for(u16 index = 0; index < count; ++index) source.values.push_back((u16) (index + 2U));
    assert(prepare(123, count, MAX_CLUSTERS, {&source,cluster_source}, workspace, plan));
    Bytes output = encode(plan, source, 63);
    assert(verify({&output,byte_reader}, (u16) output.values.size(),
                  123, MAX_CLUSTERS, workspace, plan));
    // Data changed after preparation must not pass verification/publication.
    source.values[0] = 4085;
    output = encode(plan, source, 63);
    assert(!verify({&output,byte_reader}, (u16) output.values.size(),
                   123, MAX_CLUSTERS, workspace, plan));
  }
  assert(!prepare(123, MAX_CHAIN_LENGTH + 1U, MAX_CLUSTERS,
                   {nullptr,nullptr}, workspace, plan));
}

static void candidate_layouts() {
  for(u32 capacity = 128U * 1024U; capacity <= 128U * 1024U * 1024U; capacity *= 2U) {
    fat12_layout_model::Layout layout = {};
    assert(fat12_layout_model::compute(capacity, layout));
    const auto& geometry = layout.geometry;
    assert(geometry.logical_sectors <= (capacity >= 512U * 1024U && capacity < 2U * 1024U * 1024U
        ? 4096U : capacity / 512U));
    assert(layout.clusters <= MAX_CLUSTERS);
    assert(geometry.max_nodes <= fat12_layout_model::MAX_NODES);
    assert(geometry.stage_first_sector + geometry.stage_sector_count == geometry.settings_sector);
    assert(geometry.data_sector_count > 4);
    assert(layout.directory_chain_clusters <= MAX_CHAIN_LENGTH);
    assert(geometry.catalog_table_sectors <= fat12_layout_model::CATALOG_PAGES);
    printf("C9 candidate: %u KiB, %u nodes, %u clusters of %u bytes, %u table pages, %u data sectors\n",
           capacity / 1024U, geometry.max_nodes, layout.clusters,
           geometry.sectors_per_cluster * 512U, geometry.catalog_table_sectors,
           geometry.data_sector_count);
  }
  fat12_layout_model::Layout small = {};
  assert(fat12_layout_model::compute(512U * 1024U, small));
  assert(small.geometry.max_nodes == 1024 && small.clusters == 4039);
  assert(small.geometry.sectors_per_cluster == 1);
  assert(small.geometry.catalog_table_sectors == 7);
  assert(small.geometry.data_sector_count == 71);
  assert(!fat12_layout_model::compute(127U * 1024U, small));
  assert(!fat12_layout_model::compute(129U * 1024U * 1024U, small));
}

int main() {
  golden_wire_and_boundaries();
  damaged_and_torn_records();
  invalid_sources_and_long_chains();
  candidate_layouts();
  puts("immutable FAT cluster chain tests: OK");
}
