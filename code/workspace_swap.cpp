#include "workspace_swap.hpp"

#include "crc32.hpp"
#include "zx0.hpp"

#include <stddef.h>
#include <string.h>

namespace workspace_swap {
namespace {

static constexpr u32 MAGIC = 0x31505753UL; // "SWP1"
static constexpr u8 VERSION = 1;
static constexpr usize FALLBACK_PLAN_SIZE = 256;

enum class Codec : u8 {
  RAW = 0,
  ZX0 = 1
};

struct ImageHeader {
  u32 magic;
  u32 generation;
  u32 data_crc;
  u16 raw_size;
  u16 stored_size;
  u8 version;
  u8 owner;
  u8 codec;
  u8 reserved;
  u32 header_crc;
};

static_assert(sizeof(ImageHeader) == 24, "workspace swap header changed");
static_assert(offsetof(ImageHeader, header_crc) == 20,
              "workspace swap CRC boundary changed");
static_assert(sizeof(ImageHeader) < shared_memory::BULK_SIZE,
              "workspace swap header does not fit bulk arena");

struct Counters {
  u32 generation;
  u32 capture_attempts;
  u32 captures;
  u32 restores;
  u32 evictions;
  u32 busy_failures;
  u32 encode_failures;
  u32 integrity_failures;
};

struct MemoryWriter {
  u8* data;
  usize capacity;
  usize size;
};

struct MemoryReader {
  const u8* data;
  usize size;
  usize offset;
};

static shared_memory::Lease swap_lease;
static Counters counters = {};

static void increment(u32& value) {
  if(value != 0xFFFFFFFFUL) value++;
}

static u32 portable_crc(const u8* data, usize size) {
  return mk61_crc32::finish(
      mk61_crc32::extend(mk61_crc32::INITIAL_STATE, data, size));
}

static u32 preferred_crc(const u8* data, usize size) {
  return mk61_crc32::calculate(data, size);
}

static bool write_byte(void* context, u8 value) {
  MemoryWriter& writer = *(MemoryWriter*) context;
  if(writer.size >= writer.capacity) return false;
  writer.data[writer.size++] = value;
  return true;
}

static bool read_byte(void* context, u8& value) {
  MemoryReader& reader = *(MemoryReader*) context;
  if(reader.offset >= reader.size) return false;
  value = reader.data[reader.offset++];
  return true;
}

static bool swappable_owner(shared_memory::Owner owner) {
  return owner == shared_memory::Owner::FOCAL ||
         owner == shared_memory::Owner::TINYBASIC;
}

static const ImageHeader* current_header(void) {
  return swap_lease.ok()
      ? reinterpret_cast<const ImageHeader*>(swap_lease.data()) : nullptr;
}

static bool header_valid(const ImageHeader& header) {
  if(header.magic != MAGIC || header.version != VERSION ||
     !swappable_owner((shared_memory::Owner) header.owner) ||
     header.raw_size == 0 ||
     header.raw_size > shared_memory::WORKSPACE_SIZE ||
     header.stored_size == 0 ||
     (usize) header.stored_size >
         shared_memory::BULK_SIZE - sizeof(ImageHeader) ||
     (header.codec != (u8) Codec::RAW &&
      header.codec != (u8) Codec::ZX0) ||
     (header.codec == (u8) Codec::RAW &&
      header.stored_size != header.raw_size)) return false;
  // Diagnostics may validate this header while another subsystem owns the
  // hardware CRC. A tiny header does not justify touching arbitration stats.
  return header.header_crc == portable_crc(
      reinterpret_cast<const u8*>(&header),
      offsetof(ImageHeader, header_crc));
}

static void release_image(void) {
  if(swap_lease.ok()) swap_lease.reset();
}

static bool reclaim_image(void*) {
  if(!swap_lease.ok()) return false;
  release_image();
  increment(counters.evictions);
  return true;
}

static bool ensure_backing(void) {
  if(swap_lease.ok()) return true;
  if(!swap_lease.acquire_cache(
       shared_memory::Arena::BULK,
       shared_memory::Owner::WORKSPACE_SWAP,
       shared_memory::BULK_SIZE)) return false;
  if(!swap_lease.set_reclaimer(reclaim_image)) {
    swap_lease.reset();
    return false;
  }
  return true;
}

} // namespace

bool capture_resident_before(shared_memory::Owner next_owner) {
  const shared_memory::Snapshot workspace =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  if(workspace.active_owner != shared_memory::Owner::NONE) return false;
  if(workspace.resident_owner == shared_memory::Owner::NONE ||
     workspace.resident_owner == next_owner) return true;
  if(!shared_memory::BULK_ENABLED ||
     !swappable_owner(workspace.resident_owner) ||
     workspace.resident_size == 0 ||
     workspace.resident_size > shared_memory::WORKSPACE_SIZE) return false;
  increment(counters.capture_attempts);

  shared_memory::Lease source(
      shared_memory::Arena::WORKSPACE,
      workspace.resident_owner,
      workspace.resident_size);
  if(!source.ok() || source.fresh()) {
    increment(counters.busy_failures);
    return false;
  }

  shared_memory::Lease scratch;
  alignas(4) u8 fallback_plan[FALLBACK_PLAN_SIZE];
  u8* plan_memory = fallback_plan;
  usize plan_size = sizeof(fallback_plan);
  if(scratch.acquire(shared_memory::Arena::SCRATCH,
                     shared_memory::Owner::WORKSPACE_SWAP,
                     shared_memory::SCRATCH_SIZE)) {
    plan_memory = scratch.data();
    plan_size = scratch.size();
  }

  const usize payload_capacity =
      shared_memory::BULK_SIZE - sizeof(ImageHeader);
  Codec codec = Codec::RAW;
  usize stored_size = source.size();
  zx0::Prepared prepared = {};
  const bool planned = zx0::prepare(
      source.data(), source.size(), plan_memory, plan_size, prepared);
  if(planned && prepared.output_size < stored_size &&
     prepared.output_size <= payload_capacity) {
    codec = Codec::ZX0;
    stored_size = prepared.output_size;
  } else if(stored_size > payload_capacity) {
    increment(counters.encode_failures);
    return false;
  }

  if(!ensure_backing()) {
    increment(counters.busy_failures);
    return false;
  }

  u8* const payload = swap_lease.data() + sizeof(ImageHeader);
  bool written = false;
  if(codec == Codec::RAW) {
    memcpy(payload, source.data(), stored_size);
    written = true;
  } else {
    MemoryWriter writer = {payload, payload_capacity, 0};
    const zx0::Output output = {&writer, write_byte};
    written = zx0::emit(prepared, output) && writer.size == stored_size;
  }
  if(!written) {
    increment(counters.encode_failures);
    release_image();
    return false;
  }

  increment(counters.generation);
  if(counters.generation == 0) counters.generation = 1;
  ImageHeader header = {};
  header.magic = MAGIC;
  header.generation = counters.generation;
  header.data_crc = preferred_crc(source.data(), source.size());
  header.raw_size = (u16) source.size();
  header.stored_size = (u16) stored_size;
  header.version = VERSION;
  header.owner = (u8) workspace.resident_owner;
  header.codec = (u8) codec;
  header.header_crc = preferred_crc(
      reinterpret_cast<const u8*>(&header),
      offsetof(ImageHeader, header_crc));
  memcpy(swap_lease.data(), &header, sizeof(header));
  increment(counters.captures);
  return true;
}

RestoreResult restore(shared_memory::Owner owner, usize required,
                      shared_memory::Lease& destination) {
  if(!swap_lease.ok()) return RestoreResult::NOT_FOUND;
  const ImageHeader* const stored_header = current_header();
  if(stored_header == nullptr || !header_valid(*stored_header)) {
    increment(counters.integrity_failures);
    release_image();
    return RestoreResult::NOT_FOUND;
  }
  const ImageHeader header = *stored_header;
  if((shared_memory::Owner) header.owner != owner) {
    return RestoreResult::NOT_FOUND;
  }
  if(header.raw_size != required) {
    increment(counters.integrity_failures);
    release_image();
    return RestoreResult::NOT_FOUND;
  }
  if(!destination.acquire(shared_memory::Arena::WORKSPACE,
                          owner, required)) {
    increment(counters.busy_failures);
    return RestoreResult::BUSY;
  }

  const u8* const payload = swap_lease.data() + sizeof(ImageHeader);
  bool decoded = false;
  if(header.codec == (u8) Codec::RAW) {
    memcpy(destination.data(), payload, header.raw_size);
    decoded = true;
  } else {
    MemoryReader reader = {payload, header.stored_size, 0};
    const zx0::Input input = {&reader, read_byte};
    u32 written = 0;
    decoded = zx0::decode(input, header.stored_size,
                          destination.data(), header.raw_size, written) &&
              written == header.raw_size;
  }
  decoded = decoded &&
      preferred_crc(destination.data(), header.raw_size) == header.data_crc &&
      destination.mark_restored();
  if(decoded) {
    increment(counters.restores);
  } else {
    memset(destination.data(), 0, required);
    increment(counters.integrity_failures);
  }
  release_image();
  return RestoreResult::ACQUIRED;
}

Statistics statistics(void) {
  const ImageHeader* const header = current_header();
  const bool valid = header != nullptr && header_valid(*header);
  const Statistics result = {
    shared_memory::BULK_ENABLED,
    valid,
    valid && header->codec == (u8) Codec::ZX0,
    valid ? (shared_memory::Owner) header->owner
          : shared_memory::Owner::NONE,
    valid ? (usize) header->raw_size : (usize) 0,
    valid ? (usize) header->stored_size : (usize) 0,
    valid ? header->generation : counters.generation,
    counters.capture_attempts,
    counters.captures,
    counters.restores,
    counters.evictions,
    counters.busy_failures,
    counters.encode_failures,
    counters.integrity_failures
  };
  return result;
}

void reset_statistics(void) {
  const u32 generation = counters.generation;
  counters = {};
  counters.generation = generation;
}

void discard(void) {
  release_image();
}

} // namespace workspace_swap
