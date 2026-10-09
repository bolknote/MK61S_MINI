// C9 import assignments remain in flash while the namespace is applied.
static constexpr u16 UNRESOLVED_PARENT = 0xFFFEU;
static u16 g_empty_import_index;
static u16 g_import_id_hint;
static bool g_root_changed;
static void c9_mark_parent_changed(u16 parent) {
  if(parent == program_store::ROOT_ID) g_root_changed = true;
  else mark_existing_node(parent);
}

static bool c9_strong_source(u16 id, bool directory) {
  u16 cluster = 0;
  if(!program_store::fat_first_cluster(id, cluster) || cluster == 0) return false;
  // fat_find_child below already checked the kind and type of this inode.
  return desired_kind(cluster) == (directory ? DESIRED_DIRECTORY : DESIRED_FILE);
}
static bool c9_named_source(u16 parent, const ParsedNode& parsed, u16& id) {
  id = program_store::INVALID_ID;
  if(parent != program_store::ROOT_ID &&
     (parent >= geometry().max_nodes || desired_node(parent) == DESIRED_EXTENT)) return true;
  if(!program_store::fat_find_child(parent, parsed.directory, parsed.type, parsed.name, id)) {
    return g_error.fail(ErrorCode::FILE_READ, Phase::VALIDATE, parent, 0, parsed.name, true);
  }
  if(id != program_store::INVALID_ID && c9_strong_source(id, parsed.directory)) id = program_store::INVALID_ID;
  return true;
}

static bool c9_source_node(u16 parent, ParsedNode& parsed, bool names) {
  parsed.source_id = program_store::INVALID_ID;
  if(parsed.cluster != 0) {
    program_store::FatClusterInfo info = {};
    const auto status = program_store::fat_cluster_info(parsed.cluster, info);
    if(status == program_store::FatClusterStatus::ERROR) {
      return g_error.fail(ErrorCode::FILE_READ, Phase::VALIDATE,
                           parsed.cluster, 0, parsed.name, true);
    }
    if(status == program_store::FatClusterStatus::USED && info.index == 0) {
      program_store::Entry current;
      if(!program_store::entry_by_id(info.owner, current)) {
        return g_error.fail(ErrorCode::FILE_READ, Phase::VALIDATE,
                             info.owner, 0, parsed.name, true);
      }
      if(parsed.directory == (current.kind == program_store::NodeKind::DIRECTORY)) {
        parsed.source_id = info.owner;
      }
    }
  }
  if(names && parsed.source_id == program_store::INVALID_ID) {
    if(!c9_named_source(parent, parsed, parsed.source_id)) return false;
  }
  return true;
}
static bool c9_reserve_source(u16 id) {
  for(u8 depth = 0; depth <= MAX_DEPTH && id != program_store::ROOT_ID; ++depth) {
    if(existing_node(id)) return true;
    mark_existing_node(id);
    program_store::Entry entry;
    if(!program_store::entry_by_id(id, entry)) return false;
    id = entry.parent_id;
  }
  return id == program_store::ROOT_ID;
}
static bool c9_resolve_node(u16 parent, ParsedNode& parsed, WalkPass pass) {
  if(pass == WalkPass::RESERVE) { parsed.id = program_store::INVALID_ID; return true; }
  if(pass == WalkPass::RESERVE_NAMES) {
    if(!c9_source_node(parent, parsed, pass == WalkPass::RESERVE_NAMES)) return false;
    parsed.id = parsed.source_id;
    if(parsed.source_id != program_store::INVALID_ID && !c9_reserve_source(parsed.source_id)) return false;
    return true;
  }
  if(pass == WalkPass::SNAPSHOT) {
    if(!parsed.directory) return true;
    return program_store::import_plan_get(parsed.cluster, 0, parsed.id, parsed.source_id);
  }
  parsed.empty_index = parsed.cluster == 0 ? g_empty_import_index++ : 0;
  if(pass == WalkPass::APPLY || pass == WalkPass::CHANGES || pass == WalkPass::DISPLACE) {
    if(!program_store::import_plan_get(parsed.cluster, parsed.empty_index,
                                        parsed.id, parsed.source_id) ||
       parsed.id >= geometry().max_nodes) {
      return g_error.fail(ErrorCode::APPLY, Phase::APPLY,
                           parsed.cluster, parsed.empty_index, parsed.name, true);
    }
    if(parsed.cluster == 0 && desired_node(parsed.id) == DESIRED_FILE) parsed.source_id = parsed.id;
    return true;
  }
  if(!c9_source_node(parent, parsed, true)) return false;
  parsed.id = parsed.source_id;
  if(parsed.id == program_store::INVALID_ID) {
    const u16 capacity = geometry().max_nodes;
    for(u16 step = 0; step < capacity; ++step) {
      const u16 candidate = (u16) ((g_import_id_hint + step) % capacity);
      if(existing_node(candidate) || desired_node(candidate) != DESIRED_NONE) continue;
      program_store::Entry old;
      if(program_store::node_id_available(candidate) ||
         program_store::entry_by_id(candidate, old)) {
        parsed.id = candidate;
        g_import_id_hint = (u16) ((candidate + 1U) % capacity);
        break;
      }
    }
  }
  if(parsed.id >= geometry().max_nodes || desired_node(parsed.id) != DESIRED_NONE) {
    return g_error.fail(parsed.id >= geometry().max_nodes ? ErrorCode::NODE_LIMIT : ErrorCode::NAME_COLLISION,
                         Phase::VALIDATE, (u32) geometry().max_nodes + 1U, geometry().max_nodes, parsed.name);
  }
  const DesiredKind wanted = parsed.source_id == program_store::INVALID_ID
      ? DESIRED_EXTENT : parsed.directory ? DESIRED_DIRECTORY : DESIRED_FILE;
  if(!set_desired_node(parsed.id, wanted) ||
     !program_store::import_plan_put(parsed.cluster, parsed.empty_index,
                                      parsed.id, parsed.source_id)) {
    return g_error.fail(ErrorCode::CACHE_WRITE, Phase::VALIDATE,
                         parsed.cluster, parsed.id, parsed.name, true);
  }
  if(!parsed.directory) {
    FileChain chain = {};
    if(!collect_file_chain(parsed, false, chain)) return false;
    for(u8 index = 1; index < chain.cluster_count; ++index) {
      if(!program_store::import_plan_put(chain.clusters[index], 0,
                                         parsed.id, parsed.source_id)) return false;
    }
  }
  return true;
}

struct C9DirectoryChain {
  u16 first;
  u16 count;
};
static bool c9_directory_clusters(const ParsedNode& parsed, C9DirectoryChain& result) {
  result = {parsed.cluster, 0};
  u16 cluster = parsed.cluster;
  for(u16 guard = 0; guard < program_store::max_fat_clusters(); ++guard) {
    if(!valid_cluster(cluster)) return false;
    ++result.count;
    bool ended = false;
    for(u8 sector = 0; sector < geometry().sectors_per_cluster; ++sector) {
      const u8* block = nullptr;
      if(!cached_effective_sector(cluster_lba(cluster, sector), block)) return false;
      for(u8 slot = 0; slot < 16; ++slot) if(block[slot * 32U] == 0) { ended = true; break; }
      if(ended) break;
    }
    if(ended) return true;
    u16 next = 0;
    if(!effective_fat_value(cluster, next)) return false;
    if(fat_eof(next)) return true;
    cluster = next;
  }
  return false;
}
static bool c9_directory_chain_source(void* context, u32 offset, u8* output, usize size) {
  const auto& source = *(C9DirectoryChain*) context;
  const u32 total = (u32) source.count * 2U;
  if(offset > total || size > total - offset) return false;
  while(size != 0) {
    u16 cluster = source.first;
    const u16 index = (u16) (offset / 2U);
    for(u16 step = 0; step < index; ++step) {
      if(!effective_fat_value(cluster, cluster) || !valid_cluster(cluster)) return false;
    }
    u8 bytes[2] = {(u8) cluster, (u8) (cluster >> 8)};
    const u8 begin = (u8) (offset & 1U);
    for(u8 byte = begin; byte < 2 && size != 0; ++byte) {
      *output++ = bytes[byte];
      ++offset; --size;
    }
  }
  return true;
}
static bool c9_snapshot_sector(u32 lba) {
  if(program_store::vfat_stage_exists(lba)) return true;
  u8 bytes[SECTOR_SIZE];
  return read_effective_sector(lba, bytes) &&
      program_store::vfat_stage_write(lba, bytes);
}

static bool c9_keep_stage(void*, u32 lba) {
  if(lba >= fat_start() && lba < data_start()) return true;
  if(lba < data_start() || lba >= geometry().logical_sectors) return false;
  const u16 cluster = (u16) (2U + (lba - data_start()) / geometry().sectors_per_cluster);
  return desired_kind(cluster) != DESIRED_NONE;
}

static bool c9_keep_host_metadata(void*, u32 lba) {
  if(lba >= fat_start() && lba < data_start()) return true;
  if(lba < data_start() || lba >= geometry().logical_sectors) return false;
  const u16 cluster = (u16) (2U + (lba - data_start()) / geometry().sectors_per_cluster);
  return desired_kind(cluster) == DESIRED_DIRECTORY;
}

static bool c9_visible_name(const ParsedNode& parsed, char* output, usize capacity) {
  const usize length = strlen(parsed.name);
  const char* extension = parsed.directory ? "" : program_store::file_extension(parsed.type);
  const usize extra = parsed.directory ? 0 : strlen(extension) + 1U;
  if(length + extra >= capacity) return false;
  memcpy(output, parsed.name, length + 1U);
  if(!parsed.directory) { output[length] = '.'; memcpy(output + length + 1U, extension, extra); }
  return true;
}
static u16 c9_host_name_hash(u16 parent, const char* name) {
  u32 hash = 2166136261U ^ parent;
  for(; *name; ++name) { hash ^= mk8::fold_case((u8) *name); hash *= 16777619U; }
  return (u16) (hash ^ (hash >> 16U));
}
static bool c9_claimed_name(u32 location, u16& parent, ParsedNode& output) {
  const u32 wanted_lba = location >> 4U;
  const u8 wanted_slot = (u8) (location & 15U);
  const bool root = wanted_lba >= root_start() && wanted_lba < data_start();
  u16 first = 0;
  parent = program_store::ROOT_ID;
  if(!root) {
    if(wanted_lba < data_start() || wanted_lba >= geometry().logical_sectors) return false;
    const u16 wanted_cluster = (u16) (2U + (wanted_lba - data_start()) / geometry().sectors_per_cluster);
    u16 source = program_store::INVALID_ID;
    if(!program_store::import_plan_get(wanted_cluster, 0, parent, source)) return false;
    for(u16 cluster = 2; cluster < cluster_limit(); ++cluster) {
      if(desired_kind(cluster) != DESIRED_DIRECTORY) continue;
      u16 owner = program_store::INVALID_ID;
      if(!program_store::import_plan_get(cluster, 0, owner, source)) return false;
      if(owner == parent) { first = cluster; break; }
    }
    if(first == 0) return false;
  }
  LfnState lfn; reset_lfn(lfn);
  u16 cluster = first;
  for(u16 guard = 0; guard < (root ? 1U : program_store::max_fat_clusters()); ++guard) {
    const u16 sectors = root ? geometry().root_sectors : geometry().sectors_per_cluster;
    for(u16 sector = 0; sector < sectors; ++sector) {
      const u32 lba = root ? root_start() + sector : cluster_lba(cluster, (u8) sector);
      for(u8 slot = 0; slot < 16; ++slot) {
        const u8* block = nullptr;
        if(!cached_effective_sector(lba, block)) return false;
        u8 item[32]; memcpy(item, block + slot * 32U, sizeof(item));
        if(item[11] == ATTR_LFN) { parse_lfn(item, lfn); continue; }
        if(lba == wanted_lba && slot == wanted_slot) return parse_short_item(item, lfn, output) == ParseStatus::VALID;
        reset_lfn(lfn);
      }
    }
    if(root || !effective_fat_value(cluster, cluster) || !valid_cluster(cluster)) break;
  }
  return false;
}
static bool c9_host_name_exists(u16 parent, const ParsedNode& parsed, bool& exists,
                                u32 insertion = 0xFFFFFFFFU) {
  exists = false;
  char wanted[program_store::NAME_SIZE + 16];
  if(!c9_visible_name(parsed, wanted, sizeof(wanted))) return false;
  const u16 hash = c9_host_name_hash(parent, wanted);
  const u16 slots = (u16) (geometry().max_nodes * 2U);
  u16 slot = (u16) (hash % slots);
  for(u16 step = 0; step < slots; ++step) {
    u16 current_hash = 0; u32 location = 0;
    if(!program_store::import_name_get(slot, current_hash, location)) return false;
    if(location == 0xFFFFFFFFU) return insertion == 0xFFFFFFFFU ||
        program_store::import_name_put(slot, hash, insertion);
    if(current_hash == hash) {
      u16 candidate_parent = program_store::ROOT_ID;
      ParsedNode candidate = {};
      char candidate_name[program_store::NAME_SIZE + 16];
      if(!c9_claimed_name(location, candidate_parent, candidate) ||
         !c9_visible_name(candidate, candidate_name, sizeof(candidate_name))) return false;
      if(candidate_parent == parent && fat_name::equal(wanted, candidate_name)) { exists = true; return true; }
    }
    slot = (u16) ((slot + 1U) % slots);
  }
  return false;
}
static bool c9_claim_name(u16 parent, const ParsedNode& parsed, u32 lba, u8 slot) {
  bool exists = false;
  if(!c9_host_name_exists(parent, parsed, exists, (lba << 4U) | slot)) {
    return g_error.fail(ErrorCode::CACHE_WRITE, Phase::VALIDATE, lba, slot, parsed.name, true);
  }
  return !exists || g_error.fail(ErrorCode::NAME_COLLISION, Phase::VALIDATE, parent, 0, parsed.name);
}
static void format_displaced_name(u16 id, u16 sequence, char* output) {
  static const char hex[] = "0123456789ABCDEF";
  for(u8 i = 0; i < 4; ++i) {
    output[i] = hex[(id >> ((3U - i) * 4U)) & 15U];
    output[i + 4U] = hex[(sequence >> ((3U - i) * 4U)) & 15U];
  }
  output[8] = 0;
}
