#include <algorithm>
#include <cassert>
#include <cstdio>
#include <vector>

#include "experimental/catalog_wear_model.hpp"
#include "../code/storage_geometry.hpp"

using namespace catalog_wear_model;

// The entire device is a byte vector. No hardware/filesystem I/O is present.
class RamNor {
 public:
  enum class Cut { before, prefix, scattered, complete };
  explicit RamNor(uint32_t bytes) : data(bytes, 0xff), erases(bytes / sector_bytes),
      pinned(bytes / sector_bytes, false) {}
  uint32_t sectors() const { return uint32_t(erases.size()); }
  bool available(uint32_t sector) const { return !pinned.at(sector); }
  bool read(uint32_t address, uint8_t* out, uint32_t size) {
    if(!powered || address > data.size() || size > data.size() - address) return false;
    ++reads; read_bytes += size;
    std::memcpy(out, data.data() + address, size);
    return true;
  }
  bool program(uint32_t address, const uint8_t* input, uint32_t size) {
    if(!powered || address > data.size() || size > data.size() - address) return false;
    assert(size != 0);
    for(uint32_t i = 0; i < size; ++i) {
      assert(!pinned.at((address + i) / sector_bytes));
      assert((data[address + i] & input[i]) == input[i]);
    }
    const bool fail = should_cut();
    for(uint32_t i = 0; i < size; ++i) {
      uint8_t mask = 0xff;
      if(fail) {
        if(mode == Cut::before) mask = 0;
        else if(mode == Cut::prefix) mask = i < size / 2 ? 0xff : 0;
        else if(mode == Cut::scattered) mask = uint8_t(0x55U << (i % 2));
      }
      data[address + i] &= uint8_t(input[i] | ~mask);
    }
    programmed += size;
    ++mutations;
    if(fail) powered = false;
    return powered;
  }
  bool erase(uint32_t sector) {
    if(!powered || sector >= sectors()) return false;
    assert(!pinned.at(sector));
    const bool fail = should_cut();
    for(uint32_t i = 0; i < sector_bytes; ++i) {
      uint8_t mask = 0xff;
      if(fail) {
        if(mode == Cut::before) mask = 0;
        else if(mode == Cut::prefix) mask = i < sector_bytes / 2 ? 0xff : 0;
        else if(mode == Cut::scattered) mask = uint8_t(0x55U << (i % 2));
      }
      data[sector * sector_bytes + i] |= mask;
    }
    ++erases[sector]; ++mutations;
    if(fail) powered = false;
    return powered;
  }
  void arm(uint32_t operation, Cut cut) { remaining = operation; mode = cut; powered = true; }
  void restart() { remaining = -1; powered = true; }
  uint64_t total_erases() const {
    uint64_t total = 0;
    for(uint32_t n : erases) total += n;
    return total;
  }
  std::vector<uint8_t> data;
  std::vector<uint32_t> erases;
  std::vector<bool> pinned;
  uint64_t reads = 0, read_bytes = 0, mutations = 0, programmed = 0;
 private:
  bool should_cut() {
    if(remaining < 0) return false;
    if(remaining == 0) return true;
    --remaining;
    return false;
  }
  int64_t remaining = -1;
  Cut mode = Cut::before;
  bool powered = true;
};

using TestCatalog = Catalog<RamNor>;
static constexpr uint32_t test_epoch = 0x71ce1234;
static_assert(sizeof(TestCatalog) <= 3072, "catalog working state must stay bounded");

struct Fixture {
  explicit Fixture(uint32_t capacity) : flash(capacity) {
    assert(storage_geometry::compute(capacity, geometry));
    for(uint32_t s = 0; s < flash.sectors(); ++s)
      if(s < 2 || s >= geometry.stage_first_sector) flash.pinned[s] = true;
  }
  TestCatalog catalog() {
    return TestCatalog(flash, geometry.max_nodes, 2, geometry.stage_first_sector, test_epoch);
  }
  RamNor flash;
  storage_geometry::Geometry geometry{};
};

static Update value(uint16_t id, uint32_t seed) {
  Update update{id, {}};
  for(unsigned i = 0; i < inode_bytes; ++i) {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    update.value[i] = uint8_t(seed);
  }
  return update;
}
static Meta metadata(uint32_t revision) {
  Meta result{};
  put32(result.data(), revision);
  put32(result.data() + 28, ~revision);
  return result;
}
static void expect(TestCatalog& catalog, const Update& update) {
  Inode actual{};
  assert(catalog.read(update.id, actual));
  assert(actual == update.value);
}
static void expect_empty(TestCatalog& catalog, uint16_t id) {
  Inode actual{};
  assert(catalog.read(id, actual));
  for(uint8_t byte : actual) assert(byte == 0xff);
}

static void test_pages_and_overlay() {
  Fixture f(16U * 1024U * 1024U);
  auto catalog = f.catalog();
  assert(catalog.create());
  // inode 204 straddles two erase pages, inode 25 two 512-byte buffers.
  const Update updates[] = {value(0, 1), value(25, 2), value(204, 3), value(4083, 4)};
  assert(catalog.commit(updates, 4, metadata(1)));
  assert(catalog.flush());
  uint32_t old_pages[max_pages];
  for(uint8_t p = 0; p < max_pages; ++p) old_pages[p] = catalog.page_sector(p);
  auto remount = f.catalog();
  assert(remount.mount());
  for(const auto& update : updates) expect(remount, update);
  expect_empty(remount, 1000);

  const auto changed = value(0, 5);
  const uint64_t erases_before = f.flash.total_erases();
  assert(remount.commit(&changed, 1, metadata(2)));
  assert(remount.flush());
  assert(f.flash.total_erases() - erases_before == 3); // one page + root + WAL
  assert(remount.page_sector(0) != old_pages[0]);
  for(uint8_t p = 1; p < max_pages; ++p) assert(remount.page_sector(p) == old_pages[p]);
  expect(remount, changed);

  // More than 96 distinct IDs must checkpoint without growing the overlay.
  for(uint16_t base = 500; base < 660; base += 16) {
    Update batch[16];
    for(uint8_t i = 0; i < 16; ++i) batch[i] = value(uint16_t(base + i), base + i);
    assert(remount.commit(batch, 16, metadata(base)));
  }
  auto again = f.catalog();
  assert(again.mount());
  for(uint16_t id = 500; id < 660; ++id) expect(again, value(id, id));
  std::puts("catalog model: dirty pages, split inodes, bounded overlay OK");
}

static void test_power_cuts(bool force_checkpoint, bool near_full) {
  Fixture original(512U * 1024U);
  auto catalog = original.catalog();
  assert(catalog.create());
  const Update stable = value(2, 19), before = value(0, 20), after = value(0, 21);
  assert(catalog.commit(&stable, 1, metadata(19)));
  assert(catalog.commit(&before, 1, metadata(20)));
  assert(catalog.flush());
  // Repeated relocations leave reclaimable old roots in the allocator's path.
  for(unsigned round = 0; round < 45; ++round) {
    assert(catalog.commit(&before, 1, metadata(20)));
    assert(catalog.flush());
  }
  if(force_checkpoint)
    for(unsigned i = 0; i < wal_slots; ++i) assert(catalog.commit(&before, 1, metadata(20)));
  if(near_full) {
    unsigned free = 0;
    for(uint32_t s = 2; s < original.geometry.stage_first_sector; ++s) {
      if(catalog.protects(s)) continue;
      if(free++ < 4) continue;
      original.flash.pinned[s] = true;
    }
  }
  RamNor working = original.flash;
  TestCatalog reference(working, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
  assert(reference.mount());
  const uint64_t starting = working.mutations;
  assert(reference.commit(&after, 1, metadata(21)));
  const uint32_t operations = uint32_t(working.mutations - starting);
  assert(operations >= 2);
  if(force_checkpoint) assert(operations >= 15);
  unsigned trials = 0;
  for(RamNor::Cut mode : {RamNor::Cut::before, RamNor::Cut::prefix,
                         RamNor::Cut::scattered, RamNor::Cut::complete}) {
    for(uint32_t cut = 0; cut <= operations; ++cut) {
      RamNor flash = original.flash;
      TestCatalog c(flash, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
      assert(c.mount());
      flash.arm(cut, mode);
      const bool success = c.commit(&after, 1, metadata(21));
      flash.restart();
      TestCatalog recovered(flash, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
      const uint64_t mount_mutations = flash.mutations;
      assert(recovered.mount());
      assert(flash.mutations == mount_mutations); // recovery never writes/formats
      expect(recovered, stable);
      Inode actual{};
      assert(recovered.read(0, actual));
      const bool is_new = actual == after.value;
      assert(is_new || actual == before.value);
      if(success) assert(is_new);
      assert(recovered.meta() == metadata(is_new ? 21 : 20));
      assert(recovered.commit(&after, 1, metadata(21)));
      assert(recovered.flush());
      TestCatalog retry(flash, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
      assert(retry.mount()); expect(retry, after); expect(retry, stable);
      ++trials;
    }
  }
  std::printf("catalog model: %u power cuts, checkpoint=%d near_full=%d OK\n", trials, force_checkpoint, near_full);
}

static void test_nearly_full_and_no_space() {
  Fixture f(512U * 1024U);
  auto catalog = f.catalog();
  assert(catalog.create());
  auto old = value(0, 42), next = value(0, 43);
  assert(catalog.commit(&old, 1, metadata(42)));
  assert(catalog.flush());
  // Leave exactly enough for one new page, root and WAL, then recycle the
  // old snapshot. All pinned sectors represent unrelated, immutable files.
  unsigned free = 0;
  for(uint32_t s = 2; s < f.geometry.stage_first_sector; ++s)
    if(!catalog.protects(s) && free++ >= 3) f.flash.pinned[s] = true;
  for(unsigned round = 0; round < 80; ++round) {
    auto update = value(0, 100 + round);
    assert(catalog.commit(&update, 1, metadata(round)));
    assert(catalog.flush());
    auto remount = f.catalog(); assert(remount.mount()); expect(remount, update);
  }
  for(uint32_t s = 2; s < f.geometry.stage_first_sector; ++s)
    if(!catalog.protects(s)) f.flash.pinned[s] = true;
  assert(catalog.commit(&next, 1, metadata(43)));
  const uint64_t erases = f.flash.total_erases();
  assert(!catalog.flush());
  assert(f.flash.total_erases() == erases);
  auto recovered = f.catalog(); assert(recovered.mount()); expect(recovered, next);
  std::puts("catalog model: nearly-full relocation, pinned files, no-space recovery OK");
}

static void test_max_transaction_power_cuts() {
  Fixture original(2U * 1024U * 1024U);
  auto catalog = original.catalog(); assert(catalog.create());
  std::vector<Inode> before(original.geometry.max_nodes);
  for(auto& inode : before) inode.fill(0xff);
  // Exhaust the overlay across every catalog page, before the WAL is full.
  for(uint8_t group = 0; group < 6; ++group) {
    Update batch[16];
    for(uint8_t i = 0; i < 16; ++i) {
      const uint16_t id = uint16_t(uint32_t(group * 16 + i) * (original.geometry.max_nodes - 1) / 95);
      batch[i] = value(id, 2000 + id);
      before[id] = batch[i].value;
    }
    assert(catalog.commit(batch, 16, metadata(100)));
  }
  Update batch[16];
  std::vector<Inode> after = before;
  for(uint8_t i = 0; i < 16; ++i) { batch[i] = value(i, 3000 + i); after[i] = batch[i].value; }
  RamNor successful = original.flash;
  TestCatalog reference(successful, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
  assert(reference.mount());
  const uint32_t generation = reference.generation();
  const uint64_t mutations = successful.mutations;
  assert(reference.commit(batch, 16, metadata(101)));
  assert(reference.generation() != generation);
  const uint32_t operations = uint32_t(successful.mutations - mutations);
  unsigned trials = 0;
  for(RamNor::Cut mode : {RamNor::Cut::before, RamNor::Cut::prefix, RamNor::Cut::scattered, RamNor::Cut::complete}) {
    for(uint32_t cut = 0; cut <= operations; ++cut) {
      RamNor flash = original.flash;
      TestCatalog c(flash, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
      assert(c.mount());
      flash.arm(cut, mode);
      const bool success = c.commit(batch, 16, metadata(101));
      flash.restart();
      TestCatalog recovered(flash, original.geometry.max_nodes, 2, original.geometry.stage_first_sector, test_epoch);
      assert(recovered.mount());
      const bool new_state = recovered.meta() == metadata(101);
      assert(new_state || recovered.meta() == metadata(100));
      if(success) assert(new_state);
      for(uint16_t id = 0; id < original.geometry.max_nodes; ++id) {
        Inode actual{}; assert(recovered.read(id, actual));
        assert(actual == (new_state ? after[id] : before[id]));
      }
      assert(recovered.commit(batch, 16, metadata(101)));
      assert(recovered.flush());
      ++trials;
    }
  }
  std::printf("catalog model: %u multi-page/16-inode/overlay-full power cuts OK\n", trials);
}

static void test_sequence_wrap_and_epoch() {
  Fixture f(512U * 1024U);
  auto catalog = f.catalog(); assert(catalog.create());
  uint8_t* root = f.flash.data.data() + catalog.root() * sector_bytes;
  put32(root + 8, 0xfffffffeU);
  put32(root + 20, 0xfffffffeU);
  put32(root + crc_offset, record_crc(root));
  assert(catalog.mount());
  for(uint32_t i = 0; i < 3; ++i) {
    auto update = value(0, 4000 + i);
    assert(catalog.commit(&update, 1, metadata(i))); assert(catalog.flush());
    assert(catalog.mount()); expect(catalog, update);
  }
  assert(catalog.generation() == 2);
  const uint64_t mutations = f.flash.mutations;
  TestCatalog wrong_epoch(f.flash, f.geometry.max_nodes, 2, f.geometry.stage_first_sector, test_epoch + 1);
  assert(!wrong_epoch.mount());
  assert(f.flash.mutations == mutations);
  std::puts("catalog model: generation/sequence wrap and epoch isolation OK");
}

static void test_corruption_and_legacy_refusal() {
  Fixture f(512U * 1024U);
  auto catalog = f.catalog(); assert(catalog.create());
  auto a = value(0, 70), b = value(0, 71);
  assert(catalog.commit(&a, 1, metadata(70))); assert(catalog.flush());
  assert(catalog.commit(&b, 1, metadata(71))); assert(catalog.flush());
  f.flash.data[catalog.page_sector(0) * sector_bytes + 15] ^= 1;
  const uint64_t mutations = f.flash.mutations;
  auto damaged = f.catalog(); assert(!damaged.mount());
  assert(f.flash.mutations == mutations);

  Fixture legacy(512U * 1024U);
  std::memcpy(legacy.flash.data.data(), "C6FS", 4);
  legacy.flash.data[4] = 6;
  const auto image = legacy.flash.data;
  auto refuse = legacy.catalog(); assert(!refuse.mount());
  assert(legacy.flash.data == image && legacy.flash.mutations == 0);
  std::puts("catalog model: corrupt committed page and legacy media never autoformat OK");
}

static void test_catalog_wear(uint32_t capacity, bool reboot_every_transaction) {
  Fixture f(capacity);
  auto catalog = f.catalog(); assert(catalog.create());
  const auto before = f.flash.erases;
  const uint64_t bytes_before = f.flash.programmed;
  constexpr uint32_t transactions = 2048;
  for(uint32_t i = 0; i < transactions; ++i) {
    Update update = value(0, i + 1);
    if(i & 1) update.value.fill(0xff); // delete after create
    assert(catalog.commit(&update, 1, metadata(i)));
    if(reboot_every_transaction) assert(catalog.mount());
  }
  assert(catalog.mount());
  expect_empty(catalog, 0);
  uint32_t maximum = 0, touched = 0;
  uint64_t total = 0;
  for(uint32_t s = 0; s < f.flash.sectors(); ++s) {
    const uint32_t n = f.flash.erases[s] - before[s];
    if(n) ++touched;
    maximum = std::max(maximum, n); total += n;
  }
  assert(f.flash.erases[0] == 0 && f.flash.erases[1] == 0);
  assert(touched >= std::min(uint32_t(300), f.geometry.stage_first_sector - 2));
  assert(maximum <= (capacity <= 512U * 1024U ? 5U : 1U));
  std::printf("catalog model: capacity=%u KiB transactions=%u reboot=%d erases=%llu peak=%u touched=%u programmed=%llu\n",
      capacity / 1024, transactions, reboot_every_transaction,
      static_cast<unsigned long long>(total), maximum, touched,
      static_cast<unsigned long long>(f.flash.programmed - bytes_before));
}

static void test_random_churn_and_cuts() {
  Fixture f(512U * 1024U);
  auto initial = f.catalog(); assert(initial.create());
  for(uint32_t s = 2; s < f.geometry.stage_first_sector; ++s) {
    if(s % 3 != 0 || initial.protects(s)) continue;
    f.flash.pinned[s] = true;
    std::fill(f.flash.data.begin() + s * sector_bytes,
              f.flash.data.begin() + (s + 1) * sector_bytes, 0xa5);
  }
  const auto protected_image = f.flash.data;
  assert(initial.commit(nullptr, 0, metadata(0)));
  std::vector<Inode> expected(f.geometry.max_nodes);
  for(auto& inode : expected) inode.fill(0xff);
  uint32_t random = 0x71a5e42U, revision = 0;
  auto next_random = [&]() {
    random ^= random << 13; random ^= random >> 17; random ^= random << 5;
    return random;
  };
  for(uint32_t step = 1; step <= 600; ++step) {
    auto catalog = f.catalog(); assert(catalog.mount());
    const uint8_t count = uint8_t(next_random() % 16 + 1);
    const uint16_t first = uint16_t(next_random() % f.geometry.max_nodes);
    Update batch[16];
    auto candidate = expected;
    for(uint8_t i = 0; i < count; ++i) {
      const uint16_t id = uint16_t((first + i * 37) % f.geometry.max_nodes);
      batch[i] = value(id, next_random());
      if(next_random() % 4 == 0) batch[i].value.fill(0xff);
      candidate[id] = batch[i].value;
    }
    if(step % 3 == 0)
      f.flash.arm(next_random() % 30, static_cast<RamNor::Cut>(next_random() % 4));
    const bool success = catalog.commit(batch, count, metadata(step));
    f.flash.restart();
    auto recovered = f.catalog(); assert(recovered.mount());
    if(recovered.meta() == metadata(step)) { expected = candidate; revision = step; }
    else { assert(!success); assert(recovered.meta() == metadata(revision)); }
    for(uint16_t id = 0; id < f.geometry.max_nodes; ++id) {
      Inode actual{}; assert(recovered.read(id, actual)); assert(actual == expected[id]);
    }
  }
  for(uint32_t s = 0; s < f.flash.sectors(); ++s) {
    if(!f.flash.pinned[s]) continue;
    assert(std::equal(protected_image.begin() + s * sector_bytes,
                      protected_image.begin() + (s + 1) * sector_bytes,
                      f.flash.data.begin() + s * sector_bytes));
    assert(f.flash.erases[s] == 0);
  }
  std::puts("catalog model: 600 seeded mixed transactions/reboots/cuts with pinned data OK");
}

int main() {
  test_pages_and_overlay();
  test_power_cuts(false, false);
  test_power_cuts(true, false);
  test_power_cuts(true, true);
  test_max_transaction_power_cuts();
  test_nearly_full_and_no_space();
  test_sequence_wrap_and_epoch();
  test_corruption_and_legacy_refusal();
  test_random_churn_and_cuts();
  test_catalog_wear(512U * 1024U, false);
  test_catalog_wear(512U * 1024U, true);
  test_catalog_wear(16U * 1024U * 1024U, false);
  test_catalog_wear(16U * 1024U * 1024U, true);
  std::printf("catalog model: bounded object=%zu bytes; all tests passed\n", sizeof(TestCatalog));
}
