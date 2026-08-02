#include "workspace_swap.hpp"

#include "crc32.hpp"
#include "zx0.hpp"

#include <stddef.h>
#include <string.h>
#include <type_traits>

namespace workspace_swap {
namespace {

static constexpr u32 MAGIC = 0x31505753UL; // "SWP1"
static constexpr u8 VERSION = 2;
static constexpr usize FALLBACK_PLAN_SIZE = 256;

enum class Codec : u8 {
  RAW = 0,
  ZX0 = 1
};

enum class RestoreResult : u8 {
  NOT_FOUND = 0,
  ACQUIRED,
  BUSY
};

enum class ExchangePreparation : u8 {
  NOT_NEEDED = 0,
  READY,
  UNAVAILABLE
};

struct ImageHeader {
  u32 magic;
  u32 generation;
  u32 raw_crc;
  u32 payload_crc;
  u16 raw_size;
  u16 stored_size;
  u8 version;
  u8 owner;
  u8 codec;
  u8 schema;
  u32 header_crc;
};

static_assert(sizeof(ImageHeader) == 28, "workspace swap header changed");
static_assert(std::is_standard_layout<ImageHeader>::value &&
              std::is_trivially_copyable<ImageHeader>::value,
              "workspace swap envelope must remain byte-copyable");
static_assert(offsetof(ImageHeader, magic) == 0 &&
              offsetof(ImageHeader, generation) == 4 &&
              offsetof(ImageHeader, raw_crc) == 8 &&
              offsetof(ImageHeader, payload_crc) == 12 &&
              offsetof(ImageHeader, raw_size) == 16 &&
              offsetof(ImageHeader, stored_size) == 18 &&
              offsetof(ImageHeader, version) == 20 &&
              offsetof(ImageHeader, owner) == 21 &&
              offsetof(ImageHeader, codec) == 22 &&
              offsetof(ImageHeader, schema) == 23,
              "workspace swap header layout changed");
static_assert(offsetof(ImageHeader, header_crc) == 24,
              "workspace swap CRC boundary changed");
static_assert(sizeof(ImageHeader) < shared_memory::BULK_SIZE,
              "workspace swap header does not fit bulk arena");

struct Counters {
  u32 generation;
  u32 capture_attempts;
  u32 captures;
  u32 restores;
  // Two saturating diagnostic counters share one word: successful exchanges
  // in the low half, non-exchanged attempts in the high half.
  u32 exchange_counts;
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

struct StagedResident {
  ImageHeader header;
  usize payload_offset;
  u32 resident_epoch;
};

static shared_memory::Lease swap_lease;
static Counters counters = {};

static void increment(u32& value) {
  if(value != 0xFFFFFFFFUL) value++;
}

static void increment_exchange(bool success) {
  if(success) {
    if((counters.exchange_counts & 0xFFFFU) != 0xFFFFU) {
      counters.exchange_counts++;
    }
    return;
  }
  if((counters.exchange_counts >> 16) != 0xFFFFU) {
    counters.exchange_counts += 0x10000UL;
  }
}

static u32 exchange_successes(void) {
  return counters.exchange_counts & 0xFFFFU;
}

static u32 exchange_fallbacks(void) {
  return counters.exchange_counts >> 16;
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

// Keeps the ZX0 plan alive between sizing and emission. The object is local to
// a transition: its 256-byte fallback is stack storage, while the preferred
// plan borrows the shared SCRATCH arena. No second payload-sized buffer exists.
class PreparedPayload {
  public:
    PreparedPayload(void)
      : scratch_(), fallback_{}, prepared_{}, source_(nullptr),
        stored_size_(0), codec_(Codec::RAW), ready_(false) {}

    bool prepare(const u8* source, usize raw_size, usize capacity) {
      if(source == nullptr || raw_size == 0 || raw_size > 0xFFFFU ||
         capacity == 0) return false;
      source_ = source;
      stored_size_ = raw_size;
      codec_ = Codec::RAW;

      u8* plan_memory = fallback_;
      usize plan_size = sizeof(fallback_);
      if(scratch_.acquire(shared_memory::Arena::SCRATCH,
                          shared_memory::Owner::WORKSPACE_SWAP,
                          shared_memory::SCRATCH_SIZE)) {
        plan_memory = scratch_.data();
        plan_size = scratch_.size();
      }

      const bool planned = zx0::prepare(
          source_, (u32) raw_size, plan_memory, plan_size, prepared_);
      if(planned && prepared_.output_size < stored_size_ &&
         prepared_.output_size <= capacity) {
        codec_ = Codec::ZX0;
        stored_size_ = prepared_.output_size;
      } else if(stored_size_ > capacity) {
        return false;
      }
      ready_ = true;
      return true;
    }

    bool emit(u8* output, usize capacity) const {
      if(!ready_ || output == nullptr || stored_size_ > capacity) return false;
      if(codec_ == Codec::RAW) {
        memcpy(output, source_, stored_size_);
        return true;
      }
      MemoryWriter writer = {output, capacity, 0};
      const zx0::Output sink = {&writer, write_byte};
      return zx0::emit(prepared_, sink) && writer.size == stored_size_;
    }

    Codec codec(void) const { return codec_; }
    usize stored_size(void) const { return stored_size_; }

  private:
    shared_memory::Lease scratch_;
    alignas(4) u8 fallback_[FALLBACK_PLAN_SIZE];
    zx0::Prepared prepared_;
    const u8* source_;
    usize stored_size_;
    Codec codec_;
    bool ready_;
};

static bool swappable_owner(shared_memory::Owner owner) {
  return shared_memory::owner_snapshot_schema(owner) != 0;
}

static bool read_header(ImageHeader& header) {
  if(!swap_lease.ok()) return false;
  // The backing arena is byte storage. Copying into a real local object avoids
  // depending on C++ object-lifetime and strict-aliasing exceptions.
  memcpy(&header, swap_lease.data(), sizeof(header));
  return true;
}

static bool header_valid(const ImageHeader& header) {
  if(header.magic != MAGIC || header.generation == 0 ||
     header.version != VERSION ||
     !swappable_owner((shared_memory::Owner) header.owner) ||
     header.schema != shared_memory::owner_snapshot_schema(
         (shared_memory::Owner) header.owner) ||
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

static ImageHeader make_image_header(shared_memory::Owner owner,
                                     const u8* source, usize raw_size,
                                     const PreparedPayload& encoded,
                                     const u8* payload) {
  ImageHeader header = {};
  header.magic = MAGIC;
  header.raw_crc = preferred_crc(source, raw_size);
  header.payload_crc = preferred_crc(payload, encoded.stored_size());
  header.raw_size = (u16) raw_size;
  header.stored_size = (u16) encoded.stored_size();
  header.version = VERSION;
  header.owner = (u8) owner;
  header.codec = (u8) encoded.codec();
  header.schema = shared_memory::owner_snapshot_schema(owner);
  return header;
}

// Canonicalization is the commit point: payload first (overlap-safe), header
// last, so a partial transition can never be accepted as the new image.
static bool commit_image(ImageHeader header, const u8* payload) {
  if(!swap_lease.ok() || payload == nullptr || header.stored_size == 0 ||
     (usize) header.stored_size >
         shared_memory::BULK_SIZE - sizeof(ImageHeader)) return false;
  u8* const canonical_payload =
      swap_lease.data() + sizeof(ImageHeader);
  memmove(canonical_payload, payload, header.stored_size);
  increment(counters.generation);
  if(counters.generation == 0) counters.generation = 1;
  header.generation = counters.generation;
  header.header_crc = preferred_crc(
      reinterpret_cast<const u8*>(&header),
      offsetof(ImageHeader, header_crc));
  memcpy(swap_lease.data(), &header, sizeof(header));
  return true;
}

static void release_image(void) {
  if(swap_lease.ok()) swap_lease.reset();
}

static shared_memory::EvictionDecision prepare_image_eviction(void) {
  if(!swap_lease.ok()) return shared_memory::EvictionDecision::KEEP;
  increment(counters.evictions);
  return shared_memory::EvictionDecision::RELEASE;
}

static bool ensure_backing(void) {
  if(swap_lease.ok()) return true;
  if(!swap_lease.acquire_cache(
       shared_memory::Arena::BULK,
       shared_memory::Owner::WORKSPACE_SWAP,
       shared_memory::BULK_SIZE)) return false;
  if(!swap_lease.set_evictable(prepare_image_eviction)) {
    swap_lease.reset();
    return false;
  }
  return true;
}

static ExchangePreparation stage_resident_for_exchange(
    const ImageHeader& target, StagedResident& staged) {
  const shared_memory::Snapshot workspace =
      shared_memory::snapshot(shared_memory::Arena::WORKSPACE);
  if(workspace.active_owner != shared_memory::Owner::NONE ||
     workspace.resident_owner == shared_memory::Owner::NONE ||
     workspace.resident_owner == (shared_memory::Owner) target.owner ||
     !swappable_owner(workspace.resident_owner) ||
     workspace.resident_size == 0 ||
     workspace.resident_size > shared_memory::WORKSPACE_SIZE) {
    return ExchangePreparation::NOT_NEEDED;
  }

  increment(counters.capture_attempts);
  const usize occupied = sizeof(ImageHeader) + target.stored_size;
  if(occupied >= shared_memory::BULK_SIZE) {
    increment_exchange(false);
    return ExchangePreparation::UNAVAILABLE;
  }

  shared_memory::Lease source(
      shared_memory::Arena::WORKSPACE,
      workspace.resident_owner, workspace.resident_size);
  if(!source.ok() || source.fresh()) {
    increment(counters.busy_failures);
    increment_exchange(false);
    return ExchangePreparation::UNAVAILABLE;
  }

  PreparedPayload encoded;
  const usize staging_capacity = shared_memory::BULK_SIZE - occupied;
  if(!encoded.prepare(source.data(), source.size(), staging_capacity)) {
    increment_exchange(false);
    return ExchangePreparation::UNAVAILABLE;
  }
  const usize payload_offset =
      shared_memory::BULK_SIZE - encoded.stored_size();
  u8* const payload = swap_lease.data() + payload_offset;
  if(payload_offset < occupied ||
     !encoded.emit(payload, shared_memory::BULK_SIZE - payload_offset)) {
    increment(counters.encode_failures);
    increment_exchange(false);
    return ExchangePreparation::UNAVAILABLE;
  }

  staged.header = make_image_header(
      workspace.resident_owner, source.data(), source.size(), encoded,
      payload);
  staged.payload_offset = payload_offset;
  source.reset();
  const shared_memory::ResidentToken token =
      shared_memory::resident_token(shared_memory::Arena::WORKSPACE);
  if(!token.valid() || token.owner() != workspace.resident_owner ||
     token.size() != workspace.resident_size) {
    increment(counters.busy_failures);
    increment_exchange(false);
    return ExchangePreparation::UNAVAILABLE;
  }
  staged.resident_epoch = token.epoch();
  return ExchangePreparation::READY;
}

} // namespace

static bool capture_resident_before(shared_memory::Owner next_owner) {
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

  const usize payload_capacity =
      shared_memory::BULK_SIZE - sizeof(ImageHeader);
  PreparedPayload encoded;
  if(!encoded.prepare(source.data(), source.size(), payload_capacity)) {
    increment(counters.encode_failures);
    return false;
  }

  if(!ensure_backing()) {
    increment(counters.busy_failures);
    return false;
  }

  u8* const payload = swap_lease.data() + sizeof(ImageHeader);
  if(!encoded.emit(payload, payload_capacity)) {
    increment(counters.encode_failures);
    release_image();
    return false;
  }

  const ImageHeader header = make_image_header(
      workspace.resident_owner, source.data(), source.size(), encoded,
      payload);
  if(!commit_image(header, payload)) {
    increment(counters.encode_failures);
    release_image();
    return false;
  }

  // The image is complete before the resident marker is touched. Acquiring
  // the source advanced the epoch, so obtain the commit token only after the
  // source lease has been released. Any intervening acquisition makes it
  // stale and leaves the resident state intact.
  source.reset();
  const shared_memory::ResidentToken token =
      shared_memory::resident_token(shared_memory::Arena::WORKSPACE);
  if(!token.valid() || token.owner() != workspace.resident_owner ||
     token.size() != workspace.resident_size ||
     !shared_memory::commit_resident_handoff(token)) {
    increment(counters.busy_failures);
    release_image();
    return false;
  }
  increment(counters.captures);
  return true;
}

static RestoreResult restore(shared_memory::Owner owner, usize required,
                             shared_memory::Lease& destination) {
  if(!swap_lease.ok()) return RestoreResult::NOT_FOUND;
  ImageHeader header = {};
  if(!read_header(header) || !header_valid(header)) {
    increment(counters.integrity_failures);
    release_image();
    return RestoreResult::NOT_FOUND;
  }
  if((shared_memory::Owner) header.owner != owner) {
    return RestoreResult::NOT_FOUND;
  }
  if(header.raw_size != required) {
    increment(counters.integrity_failures);
    release_image();
    return RestoreResult::NOT_FOUND;
  }
  const u8* const payload = swap_lease.data() + sizeof(ImageHeader);
  if(preferred_crc(payload, header.stored_size) != header.payload_crc) {
    increment(counters.integrity_failures);
    release_image();
    return RestoreResult::NOT_FOUND;
  }

  StagedResident staged = {};
  ExchangePreparation exchange =
      stage_resident_for_exchange(header, staged);
  if(exchange == ExchangePreparation::READY) {
    const shared_memory::ResidentToken current =
        shared_memory::resident_token(shared_memory::Arena::WORKSPACE);
    if(!current.valid() || current.owner() !=
         (shared_memory::Owner) staged.header.owner ||
       current.size() != staged.header.raw_size ||
       current.epoch() != staged.resident_epoch) {
      increment(counters.busy_failures);
      increment_exchange(false);
      exchange = ExchangePreparation::UNAVAILABLE;
    }
  }
  if(!destination.acquire(shared_memory::Arena::WORKSPACE,
                          owner, required)) {
    increment(counters.busy_failures);
    if(exchange == ExchangePreparation::READY) increment_exchange(false);
    return RestoreResult::BUSY;
  }

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
      preferred_crc(destination.data(), header.raw_size) == header.raw_crc &&
      destination.mark_restored();
  if(decoded) {
    increment(counters.restores);
  } else {
    memset(destination.data(), 0, required);
    increment(counters.integrity_failures);
  }
  if(exchange == ExchangePreparation::READY) {
    const u8* const staged_payload =
        swap_lease.data() + staged.payload_offset;
    if(commit_image(staged.header, staged_payload)) {
      increment(counters.captures);
      increment_exchange(true);
    } else {
      increment(counters.encode_failures);
      increment_exchange(false);
      release_image();
    }
  } else {
    release_image();
  }
  return RestoreResult::ACQUIRED;
}

static bool direct_acquire(shared_memory::Owner owner, usize required,
                           AcquireMode mode,
                           shared_memory::Lease& destination) {
  return mode == AcquireMode::OPPORTUNISTIC
      ? destination.acquire_cache(shared_memory::Arena::WORKSPACE,
                                  owner, required)
      : destination.acquire(shared_memory::Arena::WORKSPACE,
                            owner, required);
}

bool acquire(shared_memory::Owner owner, usize required, AcquireMode mode,
             shared_memory::Lease& destination) {
  if(mode != AcquireMode::REQUIRED &&
     mode != AcquireMode::OPPORTUNISTIC) return false;
  if(destination.ok()) return direct_acquire(owner, required, mode,
                                             destination);
  if(owner == shared_memory::Owner::NONE ||
     !shared_memory::owner_allowed(shared_memory::Arena::WORKSPACE, owner) ||
     required == 0 || required > shared_memory::WORKSPACE_SIZE ||
     (mode == AcquireMode::OPPORTUNISTIC &&
      !shared_memory::owner_cache_allowed(
          shared_memory::Arena::WORKSPACE, owner))) {
    return direct_acquire(owner, required, mode, destination);
  }

  // Nested/repeated access to the same resident bytes must never consult an
  // older swap image for that owner.
  if(shared_memory::active_owner(shared_memory::Arena::WORKSPACE) == owner ||
     shared_memory::resident_owner(shared_memory::Arena::WORKSPACE) == owner) {
    return direct_acquire(owner, required, mode, destination);
  }

  if(shared_memory::owner_snapshot_schema(owner) != 0) {
    const RestoreResult restored = restore(owner, required, destination);
    if(restored == RestoreResult::ACQUIRED) return true;
    if(restored == RestoreResult::BUSY) return false;
  }

  (void) capture_resident_before(owner);
  return direct_acquire(owner, required, mode, destination);
}

Statistics statistics(void) {
  ImageHeader header = {};
  const bool header_ok = read_header(header) && header_valid(header);
  // `valid` in terminal diagnostics means that the complete stored image is
  // usable, not merely that its small envelope survived. Raw CRC is checked
  // after decoding because validating it here would require another 8 KiB
  // destination; stored payload CRC is sufficient to reject RAM corruption.
  const bool valid = header_ok && portable_crc(
      swap_lease.data() + sizeof(ImageHeader), header.stored_size) ==
      header.payload_crc;
  const Statistics result = {
    shared_memory::BULK_ENABLED,
    valid,
    valid && header.codec == (u8) Codec::ZX0,
    valid ? (shared_memory::Owner) header.owner
          : shared_memory::Owner::NONE,
    valid ? header.schema : (u8) 0,
    valid ? (usize) header.raw_size : (usize) 0,
    valid ? (usize) header.stored_size : (usize) 0,
    valid ? header.generation : counters.generation,
    counters.capture_attempts,
    counters.captures,
    counters.restores,
    exchange_successes() + exchange_fallbacks(),
    exchange_successes(),
    exchange_fallbacks(),
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
