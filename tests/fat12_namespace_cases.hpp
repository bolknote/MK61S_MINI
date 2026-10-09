static void stage_name_cycle(void) {
  fresh(512U * 1024U);
  const u8 a = 'A', b = 'B';
  assert(program_store::write_file(program_store::ROOT_ID, 700, program_store::ProgramType::TEXT, "one", &a, 1));
  assert(program_store::write_file(program_store::ROOT_ID, 800, program_store::ProgramType::TEXT, "two", &b, 1));
  assert(virtual_fat::reset_session());
  const Layout fs = layout();
  u8 root[512]; assert(virtual_fat::read_sector(fs.root_start, root));
  const u16 begin = storage_geometry::ROOT_SYSTEM_DIRENTS * 32U;
  memset(root + begin, 0, sizeof(root) - begin);
  static const char one[11] = {'O','N','E',' ',' ',' ',' ',' ','T','X','T'};
  static const char two[11] = {'T','W','O',' ',' ',' ',' ',' ','T','X','T'};
  u8 slot = append_ascii_entry(root, storage_geometry::ROOT_SYSTEM_DIRENTS, "two.txt", two, false, first_cluster_for_id(700), 1);
  slot = append_ascii_entry(root, slot, "one.txt", one, false, first_cluster_for_id(800), 1);
  root[slot * 32U] = 0;
  assert(virtual_fat::write_sector(fs.root_start, root));
  assert(virtual_fat::flush_write_cache());
}
static void expect_name_cycle(void) {
  program_store::Entry one = {}, two = {};
  assert(program_store::entry_by_id(700, one) && strcmp(one.name, "two") == 0);
  assert(program_store::entry_by_id(800, two) && strcmp(two.name, "one") == 0);
  const u8 a = 'A', b = 'B'; expect_file(700, &a, 1); expect_file(800, &b, 1);
  assert(program_store::used_nodes() == 2);
}
static void test_c9_name_cycle_and_collisions(void) {
  stage_name_cycle(); SPIFlash::resetOperationCounts(); expect_flush();
  const u32 operations = SPIFlash::mutationOperations();
  expect_name_cycle();
  for(u32 cut = 0; cut <= operations; ++cut) {
    stage_name_cycle();
    SPIFlash::resetOperationCounts(); SPIFlash::failAfterOperations((i32) cut);
    (void) virtual_fat::flush_pending_result(); SPIFlash::clearFailure();
    virtual_fat::end_session(); program_store::init();
    assert(program_store::ready() && virtual_fat::reset_session());
    expect_name_cycle(); assert(program_store::vfat_stage_count() == 0);
  }
  for(bool cross_kind : {false, true}) {
    fresh(512U * 1024U);
    const Layout fs = layout();
    u8 root[512]; assert(virtual_fat::read_sector(fs.root_start, root));
    static const char one[11] = {'S','A','M','E',' ',' ',' ',' ','T','X','T'};
    static const char two[11] = {'S','A','M','E','~','1',' ',' ','T','X','T'};
    u8 slot = append_ascii_entry(root, storage_geometry::ROOT_SYSTEM_DIRENTS, "same.txt", one, false, 0, 0);
    slot = append_ascii_entry(root, slot, "SAME.txt", two, cross_kind, cross_kind ? 200 : 0, 0);
    root[slot * 32U] = 0;
    if(cross_kind) {
      u8 fat[512]; assert(virtual_fat::read_sector(1, fat)); set_fat12_value(fat, 200, 0xFFF);
      u8 directory[512]; dot_entries(directory, 200, 0);
      assert(virtual_fat::write_sector(cluster_lba(fs, 200), directory));
      assert(virtual_fat::write_sector(1, fat));
    }
    assert(virtual_fat::write_sector(fs.root_start, root));
    assert(virtual_fat::finalize_pending_result() == virtual_fat::CommitResult::REJECTED);
    assert(virtual_fat::diagnostic().code == virtual_fat::ErrorCode::NAME_COLLISION);
    assert(program_store::total_count() == 0 && program_store::vfat_stage_count() == 0);
  }
  printf("C9 namespace: case-fold and cross-kind collisions rejected; rename-cycle cuts=%u PASS\n", operations + 1U);
}
