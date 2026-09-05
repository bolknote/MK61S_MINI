// Included by the existing production-backed VFAT/C5 harness. Test-only: uses
// its block device adapter and real transaction/rollback code, not a FAT model.
#include <cstdio>
#include <cstring>

static void test_bounded_vfat_mutations(void) {
  static const u8 keep[] = "unchanged C5 payload";
  static const char short_name[11] = {'M','U','T','A','T','E','~','1','T','X','T'};
  // 64-byte LFN+dirent: every truncation and single-bit mutation, then FAT
  // reserved/free/self/out-of-range links. Fixed order is the reproducible seed.
  static const u16 links[] = {0,1,2,202,203,0xFF0,0xFF6,0xFF7,0xFF8,0xFFF};
  constexpr usize TRUNCATIONS = 65;
  constexpr usize BITS = 64 * 8;
  const usize cases = TRUNCATIONS + BITS + sizeof(links) / sizeof(links[0]);
  usize rejected = 0;
  for(usize trial = 0; trial < cases; ++trial) {
    fresh();
    assert(program_store::write_file(program_store::ROOT_ID, 60,
        program_store::ProgramType::TEXT, "KEEP", keep, sizeof(keep)-1));
    assert(virtual_fat::reset_session());
    const Layout fs = layout();
    u8 root[512], fat[512], payload[512] = {0x41};
    assert(virtual_fat::read_sector(fs.root_start, root));
    assert(virtual_fat::read_sector(1, fat));
    const int free_slot = first_free_slot(root);
    assert(free_slot >= 0 && free_slot + 2 < 16);
    const u8 end = append_ascii_entry(root, (u8) free_slot, "mutate.txt", short_name, false, 202, 1);
    root[(usize) end * 32] = 0;
    u8* entry = root + (usize) free_slot * 32;
    u16 link = 0xFFF;
    if(trial < TRUNCATIONS) {
      std::memset(entry + trial, 0, 64 - trial);
    } else if(trial < TRUNCATIONS + BITS) {
      const usize bit = trial - TRUNCATIONS;
      entry[bit / 8] ^= (u8) (1U << (bit % 8));
    } else {
      link = links[trial - TRUNCATIONS - BITS];
    }
    set_fat12_value(fat, 202, link);
    assert(virtual_fat::write_sector(cluster_lba(fs, 202), payload));
    assert(virtual_fat::write_sector(1, fat));
    assert(virtual_fat::write_sector(fs.root_start, root));
    const bool ok = virtual_fat::finalize_pending();
    if(!ok) {
      ++rejected;
      assert(virtual_fat::diagnostic().code != virtual_fat::ErrorCode::NONE);
      assert(program_store::total_count() == 1);
    }
    expect_file(60, keep, sizeof(keep)-1);
    // Verify persistent C5 as well, not merely a cached logical read.
    virtual_fat::end_session();
    program_store::init();
    assert(virtual_fat::reset_session());
    expect_file(60, keep, sizeof(keep)-1);
  }
  std::printf("VFAT mutation corpus: cases=%u rejected=%u C5 preserved PASS\n",
               (unsigned) cases, (unsigned) rejected);
}
