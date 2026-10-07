#ifndef MK61_CATALOG_WEAR_MODEL_HPP
#define MK61_CATALOG_WEAR_MODEL_HPP

// HOST-ONLY EXPERIMENT. This is not an on-device format implementation and
// must never be included in a firmware build. Flash is an in-memory test NOR;
// no filesystem, serial port, USB device or production disk is opened here.
//
// Experiment boundary:
// - Independent reference model for the C7 port in program_store.cpp.
//   This model never touches a real device; integration has separate tests.
// - X7CT/X7WL are deliberately NOT production C7 signatures.
// - Only inode-sized records and opaque transaction metadata are modeled.
//   available() represents file/staging ownership; payload GC is not modeled.
// - Two moving sectors hold a root/page map and 15 journal records. Only
//   changed 4-KiB pages are copied; a root is committed after all its pages.
// - Current/pending roots, journals and pages must be protected by EVERY
//   production allocator; the model only sees opaque occupied-sector pins.
// - Fixed geometry/identity locators are not rewritten on a checkpoint.
// - Dynamic leveling uses available sectors, not sectors pinned by cold data.
// - This cannot validate firmware metadata reserves, format transitions,
//   USB/GC interaction, ARM size/stack budgets or on-device timing.
// - The 15-slot journal and full-size pages can program more bytes on small
//   media than C6; distributed wear is not a promise of faster operations.
#ifndef PROGRAM_STORE_HOST_TEST
#error "The catalog wear model is restricted to host tests"
#endif

#include <array>
#include <cstdint>
#include <cstring>

namespace catalog_wear_model {

constexpr uint32_t sector_bytes = 4096;
constexpr uint32_t none = UINT32_MAX;
constexpr uint16_t inode_bytes = 20;
constexpr uint8_t max_pages = 20;
constexpr uint8_t overlay_limit = 96;
constexpr uint8_t transaction_limit = 16;
constexpr uint8_t wal_slots = 15;
constexpr uint16_t record_bytes = 512;
constexpr uint16_t crc_offset = 508;
constexpr uint16_t map_offset = 64;
constexpr uint16_t wal_offset = map_offset + max_pages * 8;
constexpr uint16_t cursor_offset = wal_offset + 4;
constexpr uint8_t active = 0x7f;

using Inode = std::array<uint8_t, inode_bytes>;
using Meta = std::array<uint8_t, 32>;
struct Update { uint16_t id; Inode value; };
struct Page { uint32_t sector = none; uint32_t crc = none; };

inline uint32_t get32(const uint8_t* p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 |
         uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline void put32(uint8_t* p, uint32_t v) {
  for(unsigned i = 0; i < 4; ++i) p[i] = uint8_t(v >> (i * 8));
}
inline uint16_t get16(const uint8_t* p) {
  return uint16_t(p[0] | uint16_t(p[1]) << 8);
}
inline void put16(uint8_t* p, uint16_t v) {
  p[0] = uint8_t(v); p[1] = uint8_t(v >> 8);
}
inline uint32_t extend_crc(uint32_t crc, const uint8_t* data, uint32_t size) {
  for(uint32_t i = 0; i < size; ++i) {
    crc ^= data[i];
    for(unsigned bit = 0; bit < 8; ++bit)
      crc = crc & 1 ? (crc >> 1) ^ 0xedb88320U : crc >> 1;
  }
  return crc;
}
inline uint32_t record_crc(uint8_t* data) {
  const uint8_t state = data[5];
  const uint32_t saved_crc = get32(data + crc_offset);
  data[5] = 0xff;
  put32(data + crc_offset, 0);
  const uint32_t crc = ~extend_crc(none, data, record_bytes);
  data[5] = state;
  put32(data + crc_offset, saved_crc);
  return crc;
}
inline bool newer(uint32_t a, uint32_t b) { return int32_t(a - b) > 0; }

// Fixed-size working state, independent of the NOR capacity. The test's
// available() callback represents sectors owned by files/USB staging, which
// are not implemented by this catalog-only experiment.
template<class Flash> class Catalog {
 public:
  Catalog(Flash& flash, uint16_t nodes, uint32_t first, uint32_t end, uint32_t epoch)
      : flash_(flash), nodes_(nodes), first_(first), end_(end), epoch_(epoch) {
    page_count_ = uint8_t((uint32_t(nodes) * inode_bytes + sector_bytes - 1) / sector_bytes);
    cursor_ = first;
  }

  bool create() {
    // Explicit test-volume creation only; mount() never formats on failure.
    if(!geometry_valid()) return false;
    pages_.fill(Page{}); pending_.fill(Page{});
    root_ = wal_ = pending_root_ = pending_wal_ = none;
    generation_ = sequence_ = 0; used_ = overlay_count_ = 0;
    cursor_ = first_; meta_.fill(0xff); sealed_ = false;
    mounted_ = checkpoint();
    return mounted_;
  }

  bool mount() {
    mounted_ = false;
    if(!geometry_valid()) return false;
    pages_.fill(Page{}); pending_.fill(Page{});
    root_ = wal_ = pending_root_ = pending_wal_ = none;
    generation_ = sequence_ = 0; used_ = overlay_count_ = 0;
    uint8_t record[record_bytes];
    for(uint32_t sector = first_; sector < end_; ++sector) {
      if(!flash_.read(sector * sector_bytes, record, 20)) return false;
      if(std::memcmp(record, "X7CT", 4) || record[5] != active ||
         get32(record + 12) != epoch_) continue;
      if(!flash_.read(sector * sector_bytes, record, sizeof(record))) return false;
      if(valid_root(record) && (root_ == none || newer(get32(record + 8), generation_))) {
        root_ = sector; generation_ = get32(record + 8);
      }
    }
    if(root_ == none || !flash_.read(root_ * sector_bytes, record, sizeof(record))) return false;
    wal_ = get32(record + wal_offset);
    cursor_ = get32(record + cursor_offset);
    if(!in_range(wal_) || !in_range(cursor_) || wal_ == root_) return false;
    for(uint8_t p = 0; p < page_count_; ++p) {
      pages_[p] = {get32(record + map_offset + p * 8), get32(record + map_offset + p * 8 + 4)};
      const Page& page = pages_[p];
      if(page.sector == none) { if(page.crc != none) return false; continue; }
      if(!in_range(page.sector) || page.sector == root_ || page.sector == wal_) return false;
      for(uint8_t previous = 0; previous < p; ++previous)
        if(pages_[previous].sector == page.sector) return false;
    }
    sequence_ = get32(record + 20);
    std::memcpy(meta_.data(), record + 24, meta_.size());
    // A committed newest root with damaged pages is an error, not an excuse
    // to resurrect an obsolete catalog whose file data may have been reused.
    for(uint8_t p = 0; p < page_count_; ++p) {
      if(pages_[p].sector == none) continue;
      uint32_t crc = none;
      for(uint16_t offset = 0; offset < sector_bytes; offset += sizeof(record)) {
        if(!flash_.read(pages_[p].sector * sector_bytes + offset, record, sizeof(record))) return false;
        crc = extend_crc(crc, record, sizeof(record));
      }
      if(~crc != pages_[p].crc) return false;
    }
    mounted_ = replay();
    return mounted_;
  }

  bool read(uint16_t id, Inode& value) {
    if(!mounted_ || id >= nodes_) return false;
    for(uint8_t i = 0; i < overlay_count_; ++i)
      if(overlay_[i].id == id) { value = overlay_[i].value; return true; }
    return read_table(uint32_t(id) * inode_bytes, value.data(), value.size());
  }

  bool commit(const Update* updates, uint8_t count, const Meta& meta) {
    if(!mounted_ || count > transaction_limit || (count && !updates)) return false;
    uint8_t extra = 0;
    for(uint8_t i = 0; i < count; ++i) {
      if(updates[i].id >= nodes_) return false;
      for(uint8_t prior = 0; prior < i; ++prior)
        if(updates[prior].id == updates[i].id) return false;
      if(find_overlay(updates[i].id) == overlay_count_) ++extra;
    }
    if(sealed_ || used_ == wal_slots || overlay_count_ + extra > overlay_limit) {
      if(!checkpoint()) { mounted_ = false; return false; }
    }
    uint8_t record[record_bytes];
    std::memset(record, 0xff, sizeof(record));
    std::memcpy(record, "X7WL", 4); record[4] = 7;
    put32(record + 8, sequence_ + 1); record[12] = count;
    std::memcpy(record + 16, meta.data(), meta.size());
    for(uint8_t i = 0; i < count; ++i) {
      put16(record + 48 + i * 22, updates[i].id);
      std::memcpy(record + 50 + i * 22, updates[i].value.data(), inode_bytes);
    }
    put32(record + crc_offset, record_crc(record));
    const uint32_t address = record_address(used_);
    if(!flash_.program(address, record, sizeof(record)) || !flash_.program(address + 5, &active, 1)) {
      mounted_ = false; return false;
    }
    for(uint8_t i = 0; i < count; ++i) if(!set_overlay(updates[i])) return false;
    ++sequence_; ++used_; meta_ = meta;
    return true;
  }

  bool flush() {
    if(!mounted_) return false;
    if(overlay_count_ == 0 && used_ == 0 && !sealed_) return true;
    if(!checkpoint()) { mounted_ = false; return false; }
    return true;
  }
  const Meta& meta() const { return meta_; }
  uint32_t root() const { return root_; }
  uint32_t page_sector(uint8_t p) const { return p < page_count_ ? pages_[p].sector : none; }
  uint32_t wal_address(uint8_t i) const { return record_address(i); }
  uint32_t generation() const { return generation_; }
  uint8_t records() const { return used_; }
  bool protects(uint32_t sector) const {
    if(sector == root_ || sector == wal_ || sector == pending_root_ || sector == pending_wal_) return true;
    for(uint8_t p = 0; p < page_count_; ++p)
      if(pages_[p].sector == sector || pending_[p].sector == sector) return true;
    return false;
  }

 private:
  bool geometry_valid() const {
    return nodes_ && nodes_ <= 4084 && page_count_ && page_count_ <= max_pages && first_ >= 2 &&
        end_ <= flash_.sectors() && end_ > first_ &&
        end_ - first_ >= 2U * page_count_ + 4;
  }
  bool in_range(uint32_t sector) const { return sector >= first_ && sector < end_; }
  bool valid_root(uint8_t* record) const {
    return !std::memcmp(record, "X7CT", 4) && record[4] == 7 && record[5] == active &&
        get32(record + 8) && get32(record + 12) == epoch_ &&
        get16(record + 16) == nodes_ && record[18] == page_count_ &&
        record_crc(record) == get32(record + crc_offset);
  }
  uint32_t record_address(uint8_t i) const {
    return i < 7 ? root_ * sector_bytes + record_bytes * (uint32_t(i) + 1)
                 : wal_ * sector_bytes + record_bytes * uint32_t(i - 7);
  }
  uint8_t find_overlay(uint16_t id) const {
    uint8_t i = 0;
    while(i < overlay_count_ && overlay_[i].id != id) ++i;
    return i;
  }
  bool set_overlay(const Update& update) {
    uint8_t i = find_overlay(update.id);
    if(i == overlay_count_) {
      if(overlay_count_ == overlay_limit) return false;
      ++overlay_count_;
    }
    overlay_[i] = update;
    return true;
  }
  bool read_table(uint32_t offset, uint8_t* data, uint32_t size) {
    while(size) {
      const uint32_t page = offset / sector_bytes, within = offset % sector_bytes;
      if(page >= page_count_) return false;
      const uint32_t count = size < sector_bytes - within ? size : sector_bytes - within;
      if(pages_[page].sector == none) std::memset(data, 0xff, count);
      else if(!flash_.read(pages_[page].sector * sector_bytes + within, data, count)) return false;
      data += count; offset += count; size -= count;
    }
    return true;
  }
  bool allocate(uint32_t& output) {
    for(uint32_t n = 0; n < end_ - first_; ++n) {
      const uint32_t candidate = first_ + (cursor_ - first_ + n) % (end_ - first_);
      if(protects(candidate) || !flash_.available(candidate)) continue;
      if(!flash_.erase(candidate)) return false;
      output = candidate;
      cursor_ = first_ + (candidate - first_ + 1) % (end_ - first_);
      return true;
    }
    return false;
  }
  bool dirty(uint8_t page) const {
    const uint32_t low = uint32_t(page) * sector_bytes, high = low + sector_bytes;
    for(uint8_t i = 0; i < overlay_count_; ++i) {
      const uint32_t offset = uint32_t(overlay_[i].id) * inode_bytes;
      if(offset < high && offset + inode_bytes > low) return true;
    }
    return false;
  }
  bool write_page(uint8_t page) {
    if(!allocate(pending_[page].sector)) return false;
    uint8_t buffer[record_bytes];
    uint32_t crc = none;
    for(uint16_t offset = 0; offset < sector_bytes; offset += sizeof(buffer)) {
      const uint32_t low = uint32_t(page) * sector_bytes + offset, high = low + sizeof(buffer);
      if(!read_table(low, buffer, sizeof(buffer))) return false;
      for(uint8_t i = 0; i < overlay_count_; ++i) {
        const uint32_t inode_low = uint32_t(overlay_[i].id) * inode_bytes, inode_high = inode_low + inode_bytes;
        if(inode_low >= high || inode_high <= low) continue;
        const uint32_t a = low > inode_low ? low : inode_low, b = high < inode_high ? high : inode_high;
        std::memcpy(buffer + (a - low), overlay_[i].value.data() + (a - inode_low), b - a);
      }
      if(!flash_.program(pending_[page].sector * sector_bytes + offset, buffer, sizeof(buffer))) return false;
      crc = extend_crc(crc, buffer, sizeof(buffer));
    }
    pending_[page].crc = ~crc;
    return true;
  }
  bool publish(uint32_t generation) {
    uint8_t record[record_bytes];
    std::memset(record, 0xff, sizeof(record));
    std::memcpy(record, "X7CT", 4); record[4] = 7;
    put32(record + 8, generation); put32(record + 12, epoch_);
    put16(record + 16, nodes_); record[18] = page_count_;
    put32(record + 20, sequence_);
    std::memcpy(record + 24, meta_.data(), meta_.size());
    for(uint8_t p = 0; p < page_count_; ++p) {
      put32(record + map_offset + p * 8, pending_[p].sector);
      put32(record + map_offset + p * 8 + 4, pending_[p].crc);
    }
    put32(record + wal_offset, pending_wal_); put32(record + cursor_offset, cursor_);
    put32(record + crc_offset, record_crc(record));
    return flash_.program(pending_root_ * sector_bytes, record, sizeof(record)) &&
           flash_.program(pending_root_ * sector_bytes + 5, &active, 1);
  }
  bool checkpoint() {
    pending_ = pages_; pending_root_ = pending_wal_ = none;
    for(uint8_t p = 0; p < page_count_; ++p)
      if(dirty(p) && !write_page(p)) return false;
    if(!allocate(pending_root_) || !allocate(pending_wal_)) return false;
    uint32_t next = generation_ + 1;
    if(next == 0) next = 1;
    if(!publish(next)) return false;
    pages_ = pending_; root_ = pending_root_; wal_ = pending_wal_; generation_ = next;
    pending_.fill(Page{}); pending_root_ = pending_wal_ = none;
    used_ = overlay_count_ = 0; sealed_ = false;
    return true;
  }
  bool replay() {
    used_ = overlay_count_ = 0; sealed_ = false;
    uint8_t record[record_bytes];
    for(uint8_t i = 0; i < wal_slots; ++i) {
      if(!flash_.read(record_address(i), record, sizeof(record))) return false;
      bool erased = true;
      for(uint8_t b : record) if(b != 0xff) erased = false;
      if(erased) break;
      if(std::memcmp(record, "X7WL", 4) || record[4] != 7 || record[5] != active ||
         get32(record + 8) != sequence_ + 1 || record[12] > transaction_limit ||
         record_crc(record) != get32(record + crc_offset)) { sealed_ = true; break; }
      for(uint8_t u = 0; u < record[12]; ++u) {
        Update update{};
        update.id = get16(record + 48 + u * 22);
        if(update.id >= nodes_) return false;
        std::memcpy(update.value.data(), record + 50 + u * 22, inode_bytes);
        if(!set_overlay(update)) return false;
      }
      std::memcpy(meta_.data(), record + 16, meta_.size());
      ++sequence_; ++used_;
    }
    return true;
  }

  Flash& flash_;
  uint16_t nodes_;
  uint32_t first_, end_, epoch_;
  std::array<Page, max_pages> pages_{}, pending_{};
  std::array<Update, overlay_limit> overlay_{};
  Meta meta_{};
  uint32_t root_ = none, wal_ = none, pending_root_ = none, pending_wal_ = none;
  uint32_t generation_ = 0, sequence_ = 0, cursor_;
  uint8_t page_count_ = 0, overlay_count_ = 0, used_ = 0;
  bool mounted_ = false, sealed_ = false;
};

} // namespace catalog_wear_model
#endif
