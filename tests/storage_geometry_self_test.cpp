#include <assert.h>
#include <stdio.h>

#include "../code/storage_geometry.hpp"

using storage_geometry::Geometry;

static void check(u32 capacity, u8 expected_cluster_sectors) {
  Geometry geometry;
  assert(storage_geometry::compute(capacity, geometry));
  assert(geometry.capacity_bytes == capacity);
  assert(geometry.physical_sectors == capacity / 4096);
  assert(geometry.sectors_per_cluster == expected_cluster_sectors);
  assert(geometry.max_nodes > 0);
  assert(geometry.max_nodes <= storage_geometry::FAT12_MAX_DATA_CLUSTERS);
  assert(geometry.logical_sectors <= capacity / 512);
  assert(geometry.catalog_a_sector >= 2);
  assert(geometry.catalog_b_sector > geometry.catalog_a_sector);
  assert(geometry.data_first_sector > geometry.catalog_b_sector);
  assert(geometry.stage_first_sector > geometry.data_first_sector);
  assert(geometry.settings_sector + 1 == geometry.physical_sectors);
  assert(geometry.stage_first_sector + geometry.stage_sector_count ==
         geometry.settings_sector);
  assert(geometry.root_entries % 16 == 0);
}

int main(void) {
  Geometry geometry;
  assert(!storage_geometry::compute(31U * 4096U, geometry));
  assert(!storage_geometry::compute(1024U * 1024U + 1U, geometry));

  check(128U * 1024U, 4);
  check(256U * 1024U, 4);
  check(512U * 1024U, 4);
  check(1U * 1024U * 1024U, 4);
  check(2U * 1024U * 1024U, 4);
  check(4U * 1024U * 1024U, 4);
  check(8U * 1024U * 1024U, 4);
  check(16U * 1024U * 1024U, 8);
  check(32U * 1024U * 1024U, 16);
  check(64U * 1024U * 1024U, 32);
  check(128U * 1024U * 1024U, 64);

  Geometry small;
  assert(storage_geometry::compute(512U * 1024U, small));
  assert(storage_geometry::compute(16U * 1024U * 1024U, geometry));
  assert(geometry.max_nodes >= 3800);
  assert(geometry.max_nodes < 4085);
  printf("storage geometry tests: OK (%u nodes on 512 KiB, %u on 16 MiB)\n",
         (unsigned) small.max_nodes, (unsigned) geometry.max_nodes);
  return 0;
}
