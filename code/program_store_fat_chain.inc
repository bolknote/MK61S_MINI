// C9 immutable mappings and bounded FAT projection scratch.
namespace {
static constexpr u8 INODE_FLAG_FAT_RELEASED = 0x04;
static constexpr u16 FAT_WINDOW = 32;
static constexpr u16 REVERSE_SLOT_BYTES = 8 + FAT_WINDOW * 6;
static constexpr u16 REVERSE_SLOTS_PER_SECTOR = 4096 / REVERSE_SLOT_BYTES;
struct C9MapReader { u32 address; };
static bool c9_read_map(void* context, u32 offset, u8* bytes, usize size) {
  const u32 address = ((C9MapReader*) context)->address;
  return address <= g_geometry.capacity_bytes &&
      offset <= g_geometry.capacity_bytes - address &&
      size <= g_geometry.capacity_bytes - address - offset &&
      read_bytes(address + offset, bytes, size);
}
static bool c9_chain_open(u16 id, const Inode& inode, fat_cluster_chain::Plan& plan) {
  plan = {id, 0, 0};
  if(inode.fat_address == EMPTY_ADDRESS) return true;
  if(!data_sector_in_range(inode.fat_address / 4096U)) return false;
  if(g_chain_verified_address == inode.fat_address && g_chain_verified_id == id) {
    plan = g_chain_verified_plan;
    return true;
  }
  u8 header[fat_cluster_chain::HEADER_BYTES];
  if(!read_bytes(inode.fat_address, header, sizeof(header))) return false;
  const u16 count = get_le16(header, 8);
  const u32 bytes = fat_cluster_chain::HEADER_BYTES + (u32) count * 2U;
  if(bytes > fat_cluster_chain::MAX_RECORD_BYTES ||
     inode.fat_address % 4096U + bytes > 4096U) return false;
  C9MapReader input = {inode.fat_address};
  fat_cluster_chain::Workspace workspace;
  if(!fat_cluster_chain::verify({&input, c9_read_map}, (u16) bytes, id,
      storage_geometry::fat_cluster_capacity(g_geometry), workspace, plan)) return false;
  g_chain_verified_address = inode.fat_address;
  g_chain_verified_id = id;
  g_chain_verified_plan = plan;
  return true;
}
static bool c9_map_size(u16 id, const Inode& inode, u16& size) {
  size = 0;
  if(inode.fat_address == EMPTY_ADDRESS) return true;
  fat_cluster_chain::Plan plan;
  if(!c9_chain_open(id, inode, plan)) return false;
  size = fat_cluster_chain::encoded_size(plan);
  return true;
}
static bool c9_chain_cluster(u16 id, const Inode& inode, u16 index, u16& value) {
  fat_cluster_chain::Plan plan;
  if(!c9_chain_open(id, inode, plan)) return false;
  C9MapReader input = {inode.fat_address};
  return fat_cluster_chain::read_cluster({&input, c9_read_map}, plan, index, value);
}
struct C9Pins {
  u8 previous;
  C9Pins() : previous(g_c9_pin_count) {}
  ~C9Pins() { g_c9_pin_count = previous; }
};
static bool c9_pin(u32 address, u16 owner, bool mapping) {
  if(address == EMPTY_ADDRESS) return true;
  for(u8 i = 0; i < g_c9_pin_count; ++i) {
    if(g_c9_pins[i].address == address) return true;
  }
  if(g_c9_pin_count >= C9_PIN_CAPACITY) return false;
  g_c9_pins[g_c9_pin_count++] = {address, owner, mapping};
  return true;
}
static bool c9_mark_cluster(u8* bits, u16 cluster) {
  const u16 count = storage_geometry::fat_cluster_capacity(g_geometry);
  if(cluster < 2 || cluster - 2U >= count) return false;
  const u16 bit = (u16) (cluster - 2U);
  bits[bit >> 3] |= (u8) (1U << (bit & 7U));
  return true;
}
static bool c9_mark_map(u16 owner, const Inode& inode, u8* bits) {
  fat_cluster_chain::Plan plan;
  if(!c9_chain_open(owner, inode, plan)) return false;
  C9MapReader input = {inode.fat_address};
  for(u16 index = 0; index < plan.count; ++index) {
    u16 cluster = 0;
    if(!fat_cluster_chain::read_cluster({&input, c9_read_map}, plan, index, cluster) ||
       !c9_mark_cluster(bits, cluster)) return false;
  }
  return true;
}
static bool c9_occupied_clusters(u16 except, u8* bits) {
  memset(bits, 0, fat_cluster_chain::BITMAP_BYTES);
  u16 remaining = g_meta.total_count;
  for(u16 id = 0; id < g_geometry.max_nodes && remaining != 0; ++id) {
    Inode inode;
    if(!get_inode(id, inode)) return false;
    if(!visible_inode(inode)) continue;
    --remaining;
    if(id == except ||
       (inode.flags & INODE_FLAG_FAT_RELEASED) != 0) continue;
    if(!c9_mark_map(id, inode, bits)) return false;
  }
  for(u8 index = 0; index < g_c9_pin_count; ++index) {
    const auto& pin = g_c9_pins[index];
    if(!pin.mapping || pin.owner == except) continue;
    Inode pending = empty_inode();
    pending.fat_address = pin.address;
    if(!c9_mark_map(pin.owner, pending, bits)) return false;
  }
  return true;
}
static bool c9_choose_file_chain(u16 owner, const Inode& old, u8 wanted,
                                const u16* requested, u8 count, u16* output) {
  if(wanted > MAX_FAT_EXTENTS_PER_FILE + 1U ||
     (requested != nullptr && count != wanted) ||
     (requested == nullptr && count != 0)) return false;
  if(wanted == 0) return true;
  u8 occupied[fat_cluster_chain::BITMAP_BYTES];
  if(!c9_occupied_clusters(owner, occupied)) return false;
  fat_cluster_chain::Plan old_plan;
  if(!c9_chain_open(owner, old, old_plan)) return false;
  C9MapReader old_reader = {old.fat_address};
  u16 cursor = 2;
  const u16 limit = (u16) (storage_geometry::fat_cluster_capacity(g_geometry) + 2U);
  for(u8 index = 0; index < wanted; ++index) {
    u16 cluster = 0;
    if(requested != nullptr) cluster = requested[index];
    else if(index < old_plan.count) {
      if(!fat_cluster_chain::read_cluster({&old_reader, c9_read_map},
                                         old_plan, index, cluster)) return false;
    } else {
      while(cursor < limit &&
          (occupied[(cursor - 2U) >> 3] & (1U << ((cursor - 2U) & 7U))) != 0) ++cursor;
      if(cursor == limit) return false;
      cluster = cursor++;
    }
    if(cluster < 2 || cluster >= limit) return false;
    const u16 bit = (u16) (cluster - 2U);
    if((occupied[bit >> 3] & (1U << (bit & 7U))) != 0) return false;
    occupied[bit >> 3] |= (u8) (1U << (bit & 7U));
    output[index] = cluster;
  }
  return true;
}
struct C9RawSource { u32 address; u16 size; };
static bool c9_read_raw(void* context, u32 offset, u8* data, usize size) {
  const auto& source = *(C9RawSource*) context;
  return offset <= source.size && size <= source.size - offset &&
      read_bytes(source.address + offset, data, size);
}
struct C9ArraySource { const u16* values; u16 count; };
static bool c9_array_cluster(void* context, u16 index, u16& value) {
  const auto& source = *(C9ArraySource*) context;
  if(index >= source.count) return false;
  value = source.values[index];
  return true;
}
static bool c9_append_chain(u16 owner, u16 count,
                            const fat_cluster_chain::Source& source,
                            u32& address) {
  address = EMPTY_ADDRESS;
  if(count == 0) return true;
  fat_cluster_chain::Workspace workspace;
  fat_cluster_chain::Plan plan;
  if(!fat_cluster_chain::prepare(owner, count,
        storage_geometry::fat_cluster_capacity(g_geometry), source, workspace, plan)) return false;
  const u16 bytes = fat_cluster_chain::encoded_size(plan);
  if(!ensure_record_space(bytes, address)) return false;
  u8 buffer[64];
  for(u16 offset = 0; offset < bytes; ) {
    const u16 size = (usize) (bytes - offset) < sizeof(buffer) ? (u16) (bytes - offset) : sizeof(buffer);
    if(!fat_cluster_chain::read_encoded(plan, source, offset, buffer, size) ||
       !write_bytes(address + offset, buffer, size)) return false;
    offset = (u16) (offset + size);
  }
  C9MapReader input = {address};
  fat_cluster_chain::Plan verified;
  if(!fat_cluster_chain::verify({&input, c9_read_map}, bytes, owner,
      storage_geometry::fat_cluster_capacity(g_geometry), workspace, verified)) return false;
  g_meta.current_offset = (u16) (g_meta.current_offset + bytes);
  return c9_pin(address, owner, true);
}
static bool c9_chain_equals(u16 owner, const Inode& inode,
                            const u16* values, u16 count) {
  fat_cluster_chain::Plan plan;
  if(!c9_chain_open(owner, inode, plan) || plan.count != count) return false;
  for(u16 index = 0; index < count; ++index) {
    u16 cluster = 0;
    if(!c9_chain_cluster(owner, inode, index, cluster) || cluster != values[index]) return false;
  }
  return true;
}
static u32 c9_reverse_slot(u16 window) {
  const u32 first = storage_geometry::import_scratch_first_sector(g_geometry);
  return sector_address(first + window / REVERSE_SLOTS_PER_SECTOR) +
      (u32) (window % REVERSE_SLOTS_PER_SECTOR) * REVERSE_SLOT_BYTES;
}
static u16 c9_name_bucket(u16 hash, u16 parent, u8 kind_type) {
  return (u16) ((hash ^ ((u32) parent * 257U) ^ ((u32) kind_type << 8U)) %
                  ((u32) g_geometry.max_nodes * 2U));
}
static u32 c9_name_slot_address(u16 slot) {
  const u16 window = slot / 64U;
  const u32 first = storage_geometry::import_scratch_first_sector(g_geometry) +
                    storage_geometry::fat_reverse_sector_count(g_geometry);
  return sector_address(first + window / 30U) + (u32) (window % 30U) * 136U;
}
static bool c9_build_name_index(void) {
  const u32 first = c9_name_slot_address(0) / 4096U;
  const u16 sectors = storage_geometry::fat_name_index_sector_count(g_geometry);
  for(u16 i = 0; i < sectors; ++i) if(!erase_sector(first + i)) return false;
  const u16 slots = (u16) (g_geometry.max_nodes * 2U);
  u16 remaining = g_meta.total_count;
  for(u16 id = 0; id < g_geometry.max_nodes && remaining != 0; ++id) {
    Inode inode;
    if(!get_inode(id, inode)) return false;
    if(!visible_inode(inode)) continue;
    --remaining;
    u16 slot = c9_name_bucket(inode.name_hash, inode.parent_id, inode.kind_type);
    for(u16 step = 0; step < slots; ++step) {
      u8 bytes[2];
      const u32 address = c9_name_slot_address(slot) + 8U + (u32) (slot % 64U) * 2U;
      if(!read_bytes(address, bytes, sizeof(bytes))) return false;
      if(get_le16(bytes, 0) == NONE) {
        put_le16(bytes, 0, id);
        if(!write_bytes(address, bytes, sizeof(bytes))) return false;
        break;
      }
      slot = (u16) ((slot + 1U) % slots);
      if(step + 1U == slots) return false;
    }
  }
  for(u16 slot = 0; slot < slots; slot = (u16) (slot + 64U)) {
    u8 header[8];
    put_le16(header, 0, slot);
    put_le16(header, 2, (u16) ((u16) (slots - slot) < 64U ? slots - slot : 64U));
    if(!read_bytes(c9_name_slot_address(slot) + 8U, (u8*) g_reverse_entries, 128)) return false;
    mk61_crc32::Context crc;
    if(!crc.update(header, 4) || !crc.update((u8*) g_reverse_entries, 128)) return false;
    put_le32(header, 4, crc.finish());
    if(!write_bytes(c9_name_slot_address(slot), header, sizeof(header))) return false;
  }
  g_reverse_window = NONE;
  return true;
}
static bool c9_read_name_slot(u16 slot, u16& id) {
  const u16 window = (u16) (slot / 64U);
  const u16 cache_tag = (u16) (0x8000U | window);
  if(g_reverse_window != cache_tag) {
    u8 header[8];
    if(!read_bytes(c9_name_slot_address(slot), header, sizeof(header)) ||
       !read_bytes(c9_name_slot_address(slot) + 8U, (u8*) g_reverse_entries, 128) ||
       get_le16(header, 0) != window * 64U) return false;
    mk61_crc32::Context crc;
    if(!crc.update(header, 4) || !crc.update((u8*) g_reverse_entries, 128) ||
       crc.finish() != get_le32(header, 4)) return false;
    g_reverse_window = cache_tag;
  }
  id = get_le16((u8*) g_reverse_entries, (u16) ((slot % 64U) * 2U));
  return id == NONE || id < g_geometry.max_nodes;
}
static bool c9_build_reverse(void) {
  g_reverse_ready = false;
  g_reverse_window = NONE;
  const u16 clusters = storage_geometry::fat_cluster_capacity(g_geometry);
  const u16 windows = (u16) ((clusters + FAT_WINDOW - 1U) / FAT_WINDOW);
  const u16 sectors = (u16) ((windows + REVERSE_SLOTS_PER_SECTOR - 1U) / REVERSE_SLOTS_PER_SECTOR);
  const u32 first = storage_geometry::import_scratch_first_sector(g_geometry);
  for(u16 sector = 0; sector < sectors; ++sector) {
    if(!erase_sector(first + sector)) return false;
  }
  u8 occupied[fat_cluster_chain::BITMAP_BYTES] = {};
  // A resumed import may have released old reservations. Prefer published
  // owners; released mappings remain available only for old source data.
  for(u8 pass = 0; pass < 2; ++pass) {
    u16 remaining = g_meta.total_count;
    for(u16 id = 0; id < g_geometry.max_nodes && remaining != 0; ++id) {
      Inode inode;
      if(!get_inode(id, inode)) return false;
      if(!visible_inode(inode)) continue;
      --remaining;
      if((((inode.flags & INODE_FLAG_FAT_RELEASED) != 0) != (pass != 0))) continue;
      fat_cluster_chain::Plan plan;
      if(!c9_chain_open(id, inode, plan)) return false;
      for(u16 index = 0; index < plan.count; ++index) {
        u16 cluster = 0;
        if(!c9_chain_cluster(id, inode, index, cluster)) return false;
        const u16 bit = (u16) (cluster - 2U);
        if((occupied[bit >> 3] & (1U << (bit & 7U))) != 0) {
          if(pass == 0) return false;
          continue;
        }
        c9_mark_cluster(occupied, cluster);
        u8 bytes[6];
        u16 next = NONE;
        if(index + 1U < plan.count && !c9_chain_cluster(id, inode, (u16) (index + 1U), next)) return false;
        put_le16(bytes, 0, id);
        put_le16(bytes, 2, index);
        put_le16(bytes, 4, next);
        if(!write_bytes(c9_reverse_slot((u16) (bit / FAT_WINDOW)) + 8U +
                         (u32) (bit % FAT_WINDOW) * 6U, bytes, sizeof(bytes))) return false;
      }
    }
  }
  for(u16 window = 0; window < windows; ++window) {
    u8 header[8] = {};
    put_le16(header, 0, (u16) (2U + window * FAT_WINDOW));
    put_le16(header, 2, (u16) ((u32) (window + 1U) * FAT_WINDOW <= clusters
        ? FAT_WINDOW : clusters - window * FAT_WINDOW));
    if(!read_bytes(c9_reverse_slot(window) + 8U, (u8*) g_reverse_entries,
                    sizeof(g_reverse_entries))) return false;
    mk61_crc32::Context crc;
    if(!crc.update(header, 4) ||
       !crc.update((u8*) g_reverse_entries, sizeof(g_reverse_entries))) return false;
    put_le32(header, 4, crc.finish());
    if(!write_bytes(c9_reverse_slot(window), header, sizeof(header))) return false;
  }
  if(!c9_build_name_index()) return false;
  g_reverse_window = NONE;
  g_reverse_ready = true;
  return true;
}
static bool c9_read_reverse(u16 cluster, u16& owner, u16& index, u16& next) {
  if(!g_reverse_ready && !c9_build_reverse()) return false;
  const u16 capacity = storage_geometry::fat_cluster_capacity(g_geometry);
  if(cluster < 2 || cluster - 2U >= capacity) return false;
  const u16 window = (u16) ((cluster - 2U) / FAT_WINDOW);
  if(g_reverse_window != window) {
    u8 header[8];
    if(!read_bytes(c9_reverse_slot(window), header, sizeof(header)) ||
       !read_bytes(c9_reverse_slot(window) + 8U, (u8*) g_reverse_entries,
                    sizeof(g_reverse_entries)) ||
       get_le16(header, 0) != 2U + window * FAT_WINDOW) return false;
    mk61_crc32::Context crc;
    if(!crc.update(header, 4) ||
       !crc.update((u8*) g_reverse_entries, sizeof(g_reverse_entries)) ||
       crc.finish() != get_le32(header, 4)) return false;
    g_reverse_window = window;
  }
  const u16 slot = (u16) ((cluster - 2U) % FAT_WINDOW);
  owner = get_le16((u8*) g_reverse_entries, (u16) (slot * 6U));
  index = get_le16((u8*) g_reverse_entries, (u16) (slot * 6U + 2U));
  next = get_le16((u8*) g_reverse_entries, (u16) (slot * 6U + 4U));
  return owner == NONE || (owner < g_geometry.max_nodes &&
      (next == NONE || (next >= 2 && next - 2U < capacity)));
}
static u32 c9_plan_address(void) {
  return sector_address(storage_geometry::import_scratch_first_sector(g_geometry) +
                         storage_geometry::fat_reverse_sector_count(g_geometry) +
                         storage_geometry::fat_name_index_sector_count(g_geometry));
}

static_assert((u32) storage_geometry::FAT12_MAX_DATA_CLUSTERS * 4U +
    (u32) storage_geometry::MAX_NODES * 14U <= 32U * 4096U,
    "C9 import scratch must fit the initialized-sector bitmap");

#if defined(ARDUINO_BLACKPILL_F401CC)
__attribute__((always_inline)) inline
#else
__attribute__((noinline))
#endif
static bool c9_plan_transfer(u32 address, u8* bytes, u16 size, bool writing) {
#if defined(ARDUINO_BLACKPILL_F401CC)
  // The constrained F401 resident keeps the eager scratch erase policy;
  // avoiding the lazy mapper's code leaves the published 4 KiB ROM reserve.
  return writing ? write_bytes(address, bytes, size) : read_bytes(address, bytes, size);
#else
  const u32 base = c9_plan_address();
  const u32 end = sector_address(storage_geometry::import_scratch_first_sector(g_geometry) +
                                storage_geometry::import_scratch_sector_count(g_geometry));
  if(address < base || address > end || size > end - address) return false;
  while(size != 0) {
    const u16 page = (u16) ((address - base) / 4096U);
    if(page >= 32U) return false;
    const u32 bit = 1UL << page;
    const u16 room = (u16) (4096U - address % 4096U);
    const u16 count = size < room ? size : room;
    if(writing) {
      if((g_import_plan_erased & bit) == 0) {
        if(!erase_sector(address / 4096U)) return false;
        g_import_plan_erased |= bit;
      }
      if(!write_bytes(address, bytes, count)) return false;
    } else if((g_import_plan_erased & bit) != 0) {
      if(!read_bytes(address, bytes, count)) return false;
    } else {
      // Old scratch is never authoritative for a new import. Its logical
      // initial value is erased, without paying 32 NOR erases up front.
      memset(bytes, 0xFF, count);
    }
    address += count; bytes += count; size = (u16) (size - count);
  }
  return true;
#endif
}
} // namespace

namespace {
struct C9DirectorySource {
  u32 old_address;
  u16 old_count;
  u16 reused;
  u16 count;
  u8 added[fat_cluster_chain::BITMAP_BYTES];
};
static bool c9_directory_source(void* context, u16 index, u16& value) {
  auto& source = *(C9DirectorySource*) context;
  if(index >= source.count) return false;
  if(index < source.reused) {
    u8 bytes[2];
    if(!read_bytes(source.old_address + fat_cluster_chain::HEADER_BYTES +
                    (u32) index * 2U, bytes, sizeof(bytes))) return false;
    value = get_le16(bytes, 0);
    return true;
  }
  u16 wanted = (u16) (index - source.reused);
  for(u16 bit = 0; bit < storage_geometry::fat_cluster_capacity(g_geometry); ++bit) {
    if((source.added[bit >> 3] & (1U << (bit & 7U))) == 0) continue;
    if(wanted == 0) { value = (u16) (bit + 2U); return true; }
    --wanted;
  }
  return false;
}
static bool c9_grow_directory(Transaction& transaction, u16 parent_id, bool trim = false) {
  if(parent_id == ROOT_ID || g_import_applying) return true;
  Inode parent;
  if(!txn_get(transaction, parent_id, parent) ||
     inode_kind(parent) != NodeKind::DIRECTORY) return false;
  u32 slots = 2;
  u16 current = parent.first_child;
  for(u16 guard = 0; current != NONE && guard < g_geometry.max_nodes; ++guard) {
    Inode child;
    char name[NAME_SIZE];
    char visible[NAME_SIZE + 16];
    if(!txn_get(transaction, current, child) || !visible_inode(child) ||
       !read_inode_name(current, child, name) ||
       !fat_visible_name(inode_kind(child), inode_type(child), name, visible)) return false;
    slots += fat_name::dirent_count(visible);
    current = child.next_sibling;
  }
  if(current != NONE) return false;
  const u16 wanted = (u16) ((slots + g_geometry.sectors_per_cluster * 16U - 1U) /
                            (g_geometry.sectors_per_cluster * 16U));
  fat_cluster_chain::Plan old;
  if(!c9_chain_open(parent_id, parent, old)) return false;
  if(old.count == wanted || (!trim && old.count > wanted)) return true;
  C9DirectorySource source = {};
  source.old_address = parent.fat_address;
  source.old_count = old.count;
  source.reused = old.count < wanted ? old.count : wanted;
  source.count = wanted;
  if(!c9_pin(parent.fat_address, parent_id, true)) return false;
  {
    u8 occupied[fat_cluster_chain::BITMAP_BYTES];
    if(!c9_occupied_clusters(parent_id, occupied)) return false;
    for(u16 index = 0; index < old.count; ++index) {
      u16 cluster = 0;
      if(!c9_chain_cluster(parent_id, parent, index, cluster) ||
         !c9_mark_cluster(occupied, cluster)) return false;
    }
    u16 remaining = (u16) (wanted - source.reused);
    for(u16 bit = 0; bit < storage_geometry::fat_cluster_capacity(g_geometry) && remaining != 0; ++bit) {
      if((occupied[bit >> 3] & (1U << (bit & 7U))) != 0) continue;
      source.added[bit >> 3] |= (u8) (1U << (bit & 7U));
      --remaining;
    }
    if(remaining != 0) return false;
  }
  u32 address = EMPTY_ADDRESS;
  if(!c9_append_chain(parent_id, wanted, {&source, c9_directory_source}, address)) return false;
  parent.fat_address = address;
  parent.flags &= (u8) ~INODE_FLAG_FAT_RELEASED;
  return txn_set(transaction, parent_id, parent);
}
static bool c9_reserve_mapping(u16 id) {
  Inode inode;
  if(!get_inode(id, inode) || !visible_inode(inode)) return false;
  if((inode.flags & INODE_FLAG_FAT_RELEASED) == 0) return true;
  inode.flags &= (u8) ~INODE_FLAG_FAT_RELEASED;
  Transaction transaction;
  txn_begin(transaction);
  return txn_set(transaction, id, inode) && append_transaction(transaction);
}
static u16 g_directory_requested_cluster = NONE;
}

bool fat_find_child(u16 parent, bool directory, ProgramType type,
                     const char* name, u16& output) {
  output = NONE;
  if(!g_ready || !valid_name(name) || !parent_valid(parent) ||
     (!g_reverse_ready && !c9_build_reverse())) return false;
  const u8 kind_type = make_kind_type(directory ? NodeKind::DIRECTORY : NodeKind::FILE,
                                     directory ? ProgramType::MK61 : type);
  const u16 hash = hash_name(name);
  const u16 slots = (u16) (g_geometry.max_nodes * 2U);
  u16 slot = c9_name_bucket(hash, parent, kind_type);
  for(u16 step = 0; step < slots; ++step) {
    u16 id = NONE;
    if(!c9_read_name_slot(slot, id)) return false;
    if(id == NONE) return true;
    Inode inode;
    if(!get_inode(id, inode)) return false;
    if(inode.parent_id == parent && inode.kind_type == kind_type && inode.name_hash == hash) {
      char stored[NAME_SIZE];
      if(!read_inode_name(id, inode, stored)) return false;
      if(fat_name::equal(name, stored)) { output = id; return true; }
    }
    slot = (u16) ((slot + 1U) % slots);
  }
  return false;
}

bool node_id_available(u16 id) {
  Inode inode;
  return g_ready && get_inode(id, inode) && !inode_used(inode);
}

u8 format_version(void) { return 9; }

u16 max_fat_clusters(void) {
  return g_ready ? storage_geometry::fat_cluster_capacity(g_geometry) : 0;
}
bool fat_first_cluster(u16 id, u16& cluster) {
  cluster = 0;
  Inode inode;
  fat_cluster_chain::Plan plan;
  if(!g_ready || !get_inode(id, inode) || !visible_inode(inode) ||
     !c9_chain_open(id, inode, plan)) return false;
  if(plan.count == 0) return inode_kind(inode) == NodeKind::FILE && inode.exported_size == 0;
  return c9_chain_cluster(id, inode, 0, cluster);
}
bool fat_chain_count(u16 id, u16& count) {
  count = 0;
  Inode inode;
  fat_cluster_chain::Plan plan;
  if(!g_ready || !get_inode(id, inode) || !visible_inode(inode) ||
     !c9_chain_open(id, inode, plan)) return false;
  count = plan.count;
  return true;
}
bool fat_chain_cluster(u16 id, u16 index, u16& cluster) {
  Inode inode;
  return g_ready && get_inode(id, inode) && visible_inode(inode) &&
      c9_chain_cluster(id, inode, index, cluster);
}
FatClusterStatus fat_cluster_info(u16 cluster, FatClusterInfo& output) {
  output = {INVALID_ID, 0, INVALID_ID};
  u16 owner = NONE, index = 0, next = NONE;
  if(!g_ready || !c9_read_reverse(cluster, owner, index, next)) return FatClusterStatus::ERROR;
  if(owner == NONE) return FatClusterStatus::FREE;
  output = {owner, index, next};

  return FatClusterStatus::USED;
}
bool fat_projection_begin(void) {
  if(g_import_applying) g_reverse_ready = false;
  g_import_applying = false;
  g_import_plan_ready = false;
  return g_ready && (g_reverse_ready || c9_build_reverse());
}
bool import_plan_begin(void) {
  if(!g_ready) return false;
  g_import_applying = false;
  g_import_plan_ready = false;
  if(!g_reverse_ready && !c9_build_reverse()) return false;
#if defined(ARDUINO_BLACKPILL_F401CC)
  const u32 first = c9_plan_address() / 4096U;
  const u16 sectors = (u16) (storage_geometry::import_scratch_sector_count(g_geometry) -
      storage_geometry::fat_reverse_sector_count(g_geometry) -
      storage_geometry::fat_name_index_sector_count(g_geometry));
  for(u16 page = 0; page < sectors; ++page) if(!erase_sector(first + page)) return false;
#else
  g_import_plan_erased = 0;
#endif
  g_import_plan_ready = true;
  g_import_applying = true;
  return true;
}
bool import_plan_put(u16 cluster, u16 empty_index, u16 target, u16 source) {
  if(!g_import_plan_ready || target >= g_geometry.max_nodes ||
     (source != NONE && source >= g_geometry.max_nodes)) return false;
  u32 offset = 0;
  u8 bytes[4];
  u16 size = 4;
  if(cluster == 0) {
    if(empty_index >= g_geometry.max_nodes) return false;
    offset = (u32) max_fat_clusters() * 4U + (u32) empty_index * 2U;
    size = 2;
  } else {
    if(cluster < 2 || cluster - 2U >= max_fat_clusters()) return false;
    offset = (u32) (cluster - 2U) * 4U;
  }
  put_le16(bytes, 0, target);
  put_le16(bytes, 2, source);
  return c9_plan_transfer(c9_plan_address() + offset, bytes, size, true);
}
bool import_plan_get(u16 cluster, u16 empty_index, u16& target, u16& source) {
  target = source = NONE;
  if(!g_import_plan_ready) return false;
  u32 offset = 0;
  u8 bytes[4];
  u16 size = 4;
  if(cluster == 0) {
    if(empty_index >= g_geometry.max_nodes) return false;
    offset = (u32) max_fat_clusters() * 4U + (u32) empty_index * 2U;
    size = 2;
  } else {
    if(cluster < 2 || cluster - 2U >= max_fat_clusters()) return false;
    offset = (u32) (cluster - 2U) * 4U;
  }
  if(!c9_plan_transfer(c9_plan_address() + offset, bytes, size, false)) return false;
  target = get_le16(bytes, 0);
  if(size == 4) source = get_le16(bytes, 2);
  return target == NONE || target < g_geometry.max_nodes;
}
static u32 c9_claim_address(u16 slot) {
  return c9_plan_address() + (u32) max_fat_clusters() * 4U +
         (u32) g_geometry.max_nodes * 2U + (u32) slot * 6U;
}
bool import_name_get(u16 slot, u16& hash, u32& location) {
  if(!g_import_plan_ready || slot >= (u32) g_geometry.max_nodes * 2U) return false;
  u8 bytes[6];
  if(!c9_plan_transfer(c9_claim_address(slot), bytes, sizeof(bytes), false)) return false;
  hash = get_le16(bytes, 0); location = get_le32(bytes, 2);
  return true;
}
bool import_name_put(u16 slot, u16 hash, u32 location) {
  if(!g_import_plan_ready || slot >= (u32) g_geometry.max_nodes * 2U || location > 0x007FFFFFU) return false;
  u8 bytes[6]; put_le16(bytes, 0, hash); put_le32(bytes, 2, location);
  return c9_plan_transfer(c9_claim_address(slot), bytes, sizeof(bytes), true);
}

bool prepare_import_mapping(u16 id) {
  if(!g_import_plan_ready) return false;
  Inode inode;
  fat_cluster_chain::Plan plan;
  if(!get_inode(id, inode) || !visible_inode(inode) ||
     !c9_chain_open(id, inode, plan)) return false;
  bool release = false;
  for(u16 index = 0; index < plan.count; ++index) {
    u16 cluster = 0, target = NONE, source = NONE;
    if(!c9_chain_cluster(id, inode, index, cluster) ||
       !import_plan_get(cluster, 0, target, source)) return false;
    if(target != id) release = true;
  }
  g_import_applying = true;
  if(!release || (inode.flags & INODE_FLAG_FAT_RELEASED) != 0) return true;
  inode.flags |= INODE_FLAG_FAT_RELEASED;
  Transaction transaction;
  txn_begin(transaction);
  return txn_set(transaction, id, inode) && append_transaction(transaction);
}
void import_plan_end(void) {
  g_import_applying = false;
  g_import_plan_ready = false;
  g_reverse_ready = false;
  g_reverse_window = NONE;
}

bool create_directory_from_fat(u16 parent, const char* name, u16 preferred,
                                u16 first, u16* output) {
  if(first < 2 || first - 2U >= max_fat_clusters()) return false;
  const u16 previous = g_directory_requested_cluster;
  g_directory_requested_cluster = first;
  const bool result = create_directory(parent, name, preferred, output);
  g_directory_requested_cluster = previous;
  return result;
}
struct C9FileChainSource { const FileSource* source; };
static bool c9_chain_from_bytes(void* context, u16 index, u16& value) {
  const auto& input = *(C9FileChainSource*) context;
  u8 bytes[2];
  if(!input.source->read(input.source->context, (u32) index * 2U, bytes, sizeof(bytes))) return false;
  value = get_le16(bytes, 0);
  return true;
}
bool set_directory_chain(u16 id, u16 count, const FileSource& source) {
  if(count == 0 || count > fat_cluster_chain::MAX_CHAIN_LENGTH || source.read == nullptr) return false;
  C9Pins pins;
  Inode inode;
  if(!g_ready || !get_inode(id, inode) || inode_kind(inode) != NodeKind::DIRECTORY ||
     !c9_pin(inode.fat_address, id, true)) return false;
  {
    u8 occupied[fat_cluster_chain::BITMAP_BYTES];
    if(!c9_occupied_clusters(id, occupied)) return false;
    C9FileChainSource input = {&source};
    for(u16 index = 0; index < count; ++index) {
      u16 cluster = 0;
      if(!c9_chain_from_bytes(&input, index, cluster) || cluster < 2 ||
         cluster - 2U >= max_fat_clusters()) return false;
      const u16 bit = (u16) (cluster - 2U);
      if((occupied[bit >> 3] & (1U << (bit & 7U))) != 0) return false;
      occupied[bit >> 3] |= (u8) (1U << (bit & 7U));
    }
  }
  fat_cluster_chain::Plan old;
  if(!c9_chain_open(id, inode, old)) return false;
  bool same = old.count == count;
  C9FileChainSource input = {&source};
  for(u16 index = 0; same && index < count; ++index) {
    u16 wanted = 0, current = 0;
    if(!c9_chain_from_bytes(&input, index, wanted) ||
       !c9_chain_cluster(id, inode, index, current)) return false;
    same = wanted == current;
  }
  if(same) return c9_reserve_mapping(id);
  u32 address = EMPTY_ADDRESS;
  if(!c9_append_chain(id, count, {&input, c9_chain_from_bytes}, address)) return false;
  if(!get_inode(id, inode)) return false;
  inode.fat_address = address;
  inode.flags &= (u8) ~INODE_FLAG_FAT_RELEASED;
  Transaction transaction;
  txn_begin(transaction);
  return txn_set(transaction, id, inode) && append_transaction(transaction);
}
bool ensure_directory_chain(u16 id) {
  C9Pins pins;
  Transaction transaction;
  txn_begin(transaction);
  if(!c9_grow_directory(transaction, id, true)) return false;
  return transaction.count == 0 || append_transaction(transaction);
}
