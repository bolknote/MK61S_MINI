#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>

#include "../code/flash_capacity_probe.hpp"

class AliasingNor {
  public:
    explicit AliasingNor(u32 capacity, bool supports_four_byte = true)
      : bytes(capacity, 0xFF), fail_writes(false), erase_count(0),
        supports_four_byte(supports_four_byte), four_byte(false) {}

    bool rawPrepare(u32 candidate) {
      four_byte = candidate > flash_capacity_probe::THREE_BYTE_LIMIT;
      return true;
    }

    bool rawEraseSector(u32 address) {
      if(fail_writes || bytes.empty()) return false;
      address = translated(address, false);
      const u32 base = (address % bytes.size()) & ~(u32) 4095;
      memset(bytes.data() + base, 0xFF, 4096);
      erase_count++;
      return true;
    }

    bool rawWrite(u32 address, const u8* data, usize len) {
      if(fail_writes || data == NULL || bytes.empty()) return false;
      if(four_byte && !supports_four_byte) {
        address = translated(address, false);
        const usize prefix = address % bytes.size();
        if((bytes[prefix] & 0) != 0) return false;
        bytes[prefix] = 0;
        address++;
      }
      for(usize i = 0; i < len; i++) {
        const usize offset = (address + i) % bytes.size();
        if((bytes[offset] & data[i]) != data[i]) return false;
      }
      for(usize i = 0; i < len; i++) bytes[(address + i) % bytes.size()] &= data[i];
      return true;
    }

    bool rawRead(u32 address, u8* out, usize len) {
      if(out == NULL || bytes.empty()) return false;
      address = translated(address, true);
      for(usize i = 0; i < len; i++) out[i] = bytes[(address + i) % bytes.size()];
      return true;
    }

    std::vector<u8> bytes;
    bool fail_writes;
    u32 erase_count;

  private:
    u32 translated(u32 address, bool reading) const {
      if(!four_byte || supports_four_byte) return address;
      return (address >> 8) + (reading ? 1U : 0U);
    }

    bool supports_four_byte;
    bool four_byte;
};

struct ProbeEvent {
  u32 candidate;
  bool complete;
  bool distinct;
};

static std::vector<ProbeEvent> probe_events;

static void record_probe_event(u32 candidate, bool complete, bool distinct) {
  probe_events.push_back({candidate, complete, distinct});
}

static void check(u32 actual, u32 reported) {
  AliasingNor flash(actual);
  u32 detected = 0;
  assert(flash_capacity_probe::detect(flash, reported, detected));
  assert(detected == actual);
  assert(flash.erase_count <= 14);
}

int main(void) {
  assert(flash_capacity_probe::jedec_capacity_bytes(0x13) == 512U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x14) == 1U * 1024U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x18) == 16U * 1024U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x19) == 32U * 1024U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x20) == 64U * 1024U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x21) == 128U * 1024U * 1024U);
  assert(flash_capacity_probe::jedec_capacity_bytes(0x22) == 0);

  check(128U * 1024U, 16U * 1024U * 1024U);
  check(256U * 1024U, 16U * 1024U * 1024U);
  check(512U * 1024U, 16U * 1024U * 1024U);
  check(1U * 1024U * 1024U, 16U * 1024U * 1024U);
  check(2U * 1024U * 1024U, 16U * 1024U * 1024U);
  check(4U * 1024U * 1024U, 16U * 1024U * 1024U);
  check(8U * 1024U * 1024U, 16U * 1024U * 1024U);
  check(16U * 1024U * 1024U, 16U * 1024U * 1024U);
  // Identification can be false in either direction. A low reported value
  // must not truncate a larger physical device.
  check(16U * 1024U * 1024U, 512U * 1024U);
  check(32U * 1024U * 1024U, 64U * 1024U * 1024U);
  check(64U * 1024U * 1024U, 512U * 1024U);
  check(128U * 1024U * 1024U, 128U * 1024U * 1024U);

  // A W25Q128-class device produces an observable start/result pair for
  // every binary-search candidate.  This is the boot trace used to diagnose
  // a slow or stuck physical erase over the CDC terminal.
  AliasingNor traced(16U * 1024U * 1024U);
  u32 traced_size = 0;
  probe_events.clear();
  assert(flash_capacity_probe::detect(traced, 16U * 1024U * 1024U,
                                      traced_size, record_probe_event));
  assert(traced_size == 16U * 1024U * 1024U);
  const u32 candidates[] = {
    4U * 1024U * 1024U,
    32U * 1024U * 1024U,
    8U * 1024U * 1024U,
    16U * 1024U * 1024U
  };
  assert(probe_events.size() == 8U);
  for(usize index = 0; index < 4; index++) {
    const ProbeEvent& start = probe_events[index * 2];
    const ProbeEvent& finish = probe_events[index * 2 + 1];
    assert(start.candidate == candidates[index] && !start.complete);
    assert(finish.candidate == candidates[index] && finish.complete);
  }
  assert(probe_events[1].distinct);
  assert(!probe_events[3].distinct);
  assert(probe_events[5].distinct);
  assert(probe_events[7].distinct);

  // A 3-byte chip that ignores EN4B shifts a four-byte transaction instead
  // of wrapping the intended address. The protocol guards must prevent that
  // from looking like a valid 32/64 MiB boundary.
  AliasingNor ignored_en4b(16U * 1024U * 1024U, false);
  u32 ignored_en4b_size = 0;
  assert(flash_capacity_probe::detect(ignored_en4b,
                                      64U * 1024U * 1024U,
                                      ignored_en4b_size));
  assert(ignored_en4b_size == 16U * 1024U * 1024U);

  AliasingNor failed(1U * 1024U * 1024U);
  failed.fail_writes = true;
  u32 detected = 123;
  assert(!flash_capacity_probe::detect(failed, 16U * 1024U * 1024U, detected));
  assert(detected == 0);
  printf("flash capacity probe tests: OK\n");
  return 0;
}
