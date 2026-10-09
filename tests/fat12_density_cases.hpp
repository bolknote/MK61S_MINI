// Normal FAT12 host-sector workflows, independent of preferred inode IDs.
static u16 density_fat(const std::vector<u8>& bytes, u16 cluster) {
  const u32 offset = cluster + cluster / 2U;
  const u16 value = (u16) (bytes[offset] | (bytes[offset + 1U] << 8));
  return cluster & 1U ? (u16) (value >> 4) : (u16) (value & 0xFFFU);
}
static void density_set_fat(std::vector<u8>& fat, u16 cluster, u16 value) {
  const usize offset = cluster + cluster / 2U;
  assert(offset + 1U < fat.size());
  value &= 0xFFFU;
  if(cluster & 1U) {
    fat[offset] = (u8) ((fat[offset] & 0x0FU) | (value << 4U));
    fat[offset + 1U] = (u8) (value >> 4U);
  } else {
    fat[offset] = (u8) value;
    fat[offset + 1U] = (u8) ((fat[offset + 1U] & 0xF0U) | (value >> 8U));
  }
}
static std::vector<u16> density_directory(u16 id, std::vector<u8>& bytes) {
  const Layout fs = layout();
  u16 count = 0;
  assert(program_store::fat_chain_count(id, count));
  std::vector<u16> clusters(count);
  bytes.resize((usize) count * fs.sectors_per_cluster * 512U);
  for(u16 i = 0; i < count; ++i) {
    clusters[i] = chain_cluster_for_id(id, i);
    assert(virtual_fat::read_sectors(cluster_lba(fs, clusters[i]),
        bytes.data() + (usize) i * fs.sectors_per_cluster * 512U,
        fs.sectors_per_cluster));
  }
  return clusters;
}
static void density_write_directory(const Layout& fs, const std::vector<u16>& chain,
                                      const std::vector<u8>& bytes) {
  for(usize i = 0; i < chain.size(); ++i) {
    assert(virtual_fat::write_cached_sectors(cluster_lba(fs, chain[i]),
        bytes.data() + i * fs.sectors_per_cluster * 512U, fs.sectors_per_cluster));
  }
}
static virtual_fat::CommitResult density_add(u16 directory, char prefix,
                                             u16 start, u16 count, bool payload) {
  const Layout fs = layout();
  std::vector<u8> bytes;
  auto chain = density_directory(directory, bytes);
  std::vector<u8> fat((usize) fs.fat_sectors * 512U);
  assert(virtual_fat::read_sectors(1, fat.data(), fs.fat_sectors));
  usize slot = 2;
  while(slot * 32U < bytes.size() && bytes[slot * 32U] != 0) ++slot;
  const usize slots_per_cluster = (usize) fs.sectors_per_cluster * 16U;
  const usize needed = (slot + count + 1U + slots_per_cluster - 1U) / slots_per_cluster;
  while(chain.size() < needed) {
    u16 free = 2;
    while(free < program_store::max_fat_clusters() + 2U && density_fat(fat, free) != 0) ++free;
    assert(free < program_store::max_fat_clusters() + 2U);
    density_set_fat(fat, chain.back(), free);
    density_set_fat(fat, free, 0xFFF);
    chain.push_back(free);
  }
  bytes.resize(chain.size() * slots_per_cluster * 32U, 0);
  for(u16 i = 0; i < count; ++i) {
    char name[8]; snprintf(name, sizeof(name), "%c%04u", prefix, (unsigned) (start + i));
    char alias[11]; memset(alias, ' ', sizeof(alias));
    memcpy(alias, name, strlen(name)); memcpy(alias + 8, "TXT", 3);
    u16 cluster = 0;
    if(payload) {
      cluster = 2;
      while(cluster < program_store::max_fat_clusters() + 2U && density_fat(fat, cluster) != 0) ++cluster;
      assert(cluster < program_store::max_fat_clusters() + 2U);
      density_set_fat(fat, cluster, 0xFFF);
      u8 data[512] = {}; data[0] = (u8) ('A' + (start + i) % 26U);
      assert(virtual_fat::write_cached_sectors(cluster_lba(fs, cluster), data, 1));
    }
    append_short_entry(bytes.data(), (u16) slot++, alias, false, cluster, payload ? 1 : 0);
  }
  bytes[slot * 32U] = 0;
  density_write_directory(fs, chain, bytes);
  assert(virtual_fat::write_cached_sectors(1, fat.data(), fs.fat_sectors));
  const auto result = virtual_fat::finalize_pending_result();
  if(result == virtual_fat::CommitResult::IO_FAILED) {
    char report[virtual_fat::DIAGNOSTIC_LINE_SIZE];
    assert(virtual_fat::format_diagnostic(virtual_fat::diagnostic(), report, sizeof(report)));
    fprintf(stderr, "C9 density import failed: %s\n", report);
  }
  return result;
}
static void test_c9_density_and_refill(void) {
  fresh(512U * 1024U);
  constexpr u16 DIR_ID = 900;
  assert(program_store::create_directory(program_store::ROOT_ID, "Dense", DIR_ID));
  assert(virtual_fat::reset_session());
  const u16 files = (u16) (program_store::max_nodes() - 1U);
  SPIFlash::resetOperationCounts();
  for(u16 first = 0; first < files;) {
    const u16 count = files - first < 128U ? (u16) (files - first) : 128;
    assert(density_add(DIR_ID, 'E', first, count, false) == virtual_fat::CommitResult::OK);
    first = (u16) (first + count);
  }
  assert(program_store::used_nodes() == 1024 && program_store::total_count() == 1024);
  u16 count = 0;
  assert(program_store::fat_chain_count(DIR_ID, count) && count < 140);
  for(int i = 0; i < program_store::child_count(DIR_ID); ++i) {
    program_store::Entry entry = {};
    assert(program_store::child(DIR_ID, i, entry));
    assert(entry.data_len == 0 && first_cluster_for_id(entry.id) == 0);
  }
  printf("C9 USB density: 512 KiB, %u empty files + directory, %u directory clusters, reads=%u mutations=%u\n",
      files, count, SPIFlash::readOperations(), SPIFlash::mutationOperations());
  fflush(stdout);
  assert(density_add(DIR_ID, 'Z', 0, 1, false) == virtual_fat::CommitResult::REJECTED);
  assert(program_store::used_nodes() == 1024 && program_store::vfat_stage_count() == 0);
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  std::vector<u8> bytes;
  const auto chain = density_directory(DIR_ID, bytes);
  u16 seen = 0, removed = 0;
  for(usize slot = 2; slot * 32U < bytes.size() && bytes[slot * 32U] != 0; ++slot) {
    u8* item = bytes.data() + slot * 32U;
    if(item[0] == 0xE5 || item[11] != 0x20) continue;
    if(seen++ % 3U != 0) continue;
    ++removed; item[0] = 0xE5;
    for(usize previous = slot; previous > 2;) {
      --previous;
      if(bytes[previous * 32U + 11U] != 0x0F) break;
      bytes[previous * 32U] = 0xE5;
    }
  }
  density_write_directory(fs, chain, bytes);
  expect_flush();
  assert(program_store::used_nodes() == files + 1U - removed);
  for(u16 first = 0; first < removed;) {
    const u16 batch = removed - first < 128U ? (u16) (removed - first) : 128;
    assert(density_add(DIR_ID, 'R', first, batch, false) == virtual_fat::CommitResult::OK);
    first = (u16) (first + batch);
  }
  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready() && program_store::used_nodes() == 1024);
  assert(virtual_fat::reset_session());
  printf("C9 USB refill: deleted=%u, restored=1023 empty files, reboot PASS\n", removed);

  fresh(512U * 1024U);
  assert(program_store::create_directory(program_store::ROOT_ID, "Small", DIR_ID));
  assert(virtual_fat::reset_session());
  constexpr u16 SMALL_FILES = 320;
  for(u16 first = 0; first < SMALL_FILES; first += 64U) {
    assert(density_add(DIR_ID, 'S', first, 64, true) == virtual_fat::CommitResult::OK);
  }
  virtual_fat::end_session();
  program_store::init();
  assert(program_store::ready() && program_store::used_nodes() == SMALL_FILES + 1U);
  assert(virtual_fat::reset_session());
  for(int i = 0; i < SMALL_FILES; ++i) {
    program_store::Entry entry = {};
    assert(program_store::child(DIR_ID, i, entry));
    const unsigned index = (unsigned) strtoul(entry.name + 1, nullptr, 10);
    const u8 expected = (u8) ('A' + index % 26U);
    expect_file(entry.id, &expected, 1);
    assert(first_cluster_for_id(entry.id) != entry.id + 2U);
  }
  printf("C9 USB density: 320 one-byte files, independent chains, reboot/content PASS\n");
}
