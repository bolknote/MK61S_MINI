#include <assert.h>
#include <stdio.h>

#include "../code/storage_geometry.hpp"

using storage_geometry::Geometry;

static void check(u32 capacity, u8 expected_cluster_sectors,
                  u8 module_mask = 0) {
  Geometry geometry;
  assert(storage_geometry::compute(capacity, geometry, module_mask));
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
  assert(geometry.stage_data_sector_count <= geometry.stage_sector_count);
  if(geometry.module_first_sector != 0) {
    assert(geometry.module_mask == module_mask);
    assert(geometry.stage_data_sector_count +
           storage_geometry::MODULE_SECTORS ==
           geometry.stage_sector_count);
    assert(geometry.module_first_sector == geometry.stage_first_sector +
           geometry.stage_data_sector_count);
    assert(geometry.module_first_sector + storage_geometry::MODULE_SECTORS ==
           geometry.settings_sector);
  } else {
    assert(geometry.module_mask == 0);
    assert(geometry.stage_data_sector_count == geometry.stage_sector_count);
  }
  assert(geometry.root_entries % 16 == 0);
  assert(geometry.root_entries <= storage_geometry::ROOT_ENTRY_CAPACITY);
}

int main(void) {
  Geometry geometry;
  assert(!storage_geometry::compute(31U * 4096U, geometry));
  assert(!storage_geometry::compute(1024U * 1024U + 1U, geometry));
  assert(!storage_geometry::compute(2U * 1024U * 1024U, geometry, 0x80));

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
  assert(small.stage_sector_count == storage_geometry::STAGE_SMALL_SECTORS);
  assert(small.module_first_sector == 0);
  assert(storage_geometry::compute(16U * 1024U * 1024U, geometry,
                                   storage_geometry::MODULE_ALL));
  assert(geometry.stage_sector_count == storage_geometry::STAGE_TARGET_SECTORS);
  assert(geometry.stage_data_sector_count ==
         storage_geometry::STAGE_TARGET_SECTORS -
         storage_geometry::MODULE_SECTORS);
  assert(geometry.module_first_sector != 0);
  assert(geometry.module_mask == storage_geometry::MODULE_ALL);
  assert(geometry.root_entries == storage_geometry::ROOT_ENTRY_CAPACITY);
  assert(geometry.max_nodes == storage_geometry::FAT12_MAX_DATA_CLUSTERS);

  Geometry focal_only;
  assert(storage_geometry::compute(2U * 1024U * 1024U, focal_only,
                                   storage_geometry::MODULE_FOCAL));
  assert(focal_only.module_mask == storage_geometry::MODULE_FOCAL);
  assert(focal_only.stage_data_sector_count ==
         storage_geometry::STAGE_TARGET_SECTORS -
         storage_geometry::MODULE_SECTORS);
  printf("storage geometry tests: OK (%u nodes on 512 KiB, %u on 16 MiB)\n",
         (unsigned) small.max_nodes, (unsigned) geometry.max_nodes);
  return 0;
}
