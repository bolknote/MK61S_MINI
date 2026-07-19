#ifndef PROGRAM_STORE_HOST_SPIFLASH_H
#define PROGRAM_STORE_HOST_SPIFLASH_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

class SPIFlash {
  public:
    static constexpr uint32_t SECTOR_SIZE = 4096;
    static constexpr uint32_t DEFAULT_CAPACITY = 2U * 1024U * 1024U;
    static constexpr uint32_t MAX_CAPACITY = 16U * 1024U * 1024U;

    SPIFlash(uint8_t = 0) {}

    bool begin(uint32_t = 0) { return true; }
    uint32_t getCapacity(void) const { return selected_capacity; }
    uint32_t getJEDECID(void) const { return 0xEF4018; }
    bool sfdpPresent(void) const { return true; }

    uint8_t readByte(uint32_t address) const {
      read_operations++;
      return address < actual_capacity ? storage[address] : 0xFF;
    }

    bool readByteArray(uint32_t address, uint8_t* out, size_t len) const {
      if(out == NULL || address > actual_capacity || len > actual_capacity - address) return false;
      read_operations++;
      read_bytes += len;
      memcpy(out, storage + address, len);
      return true;
    }

    bool writeByte(uint32_t address, uint8_t value, bool = true) {
      return writeByteArray(address, &value, 1);
    }

    bool writeByteArray(uint32_t address, uint8_t* data, size_t len, bool = true) {
      if(data == NULL || address > actual_capacity || len > actual_capacity - address || fails(address, len)) return false;
      for(size_t i = 0; i < len; i++) {
        if((storage[address + i] & data[i]) != data[i]) return false;
      }
      for(size_t i = 0; i < len; i++) storage[address + i] &= data[i];
      programmed_bytes += len;
      mutation_operations++;
      return true;
    }

    bool eraseSector(uint32_t address) {
      const uint32_t base = address - address % SECTOR_SIZE;
      if(base >= actual_capacity || fails(base, SECTOR_SIZE)) return false;
      memset(storage + base, 0xFF, SECTOR_SIZE);
      erase_count++;
      sector_erases[base / SECTOR_SIZE]++;
      mutation_operations++;
      return true;
    }

    static void reset(uint32_t capacity = DEFAULT_CAPACITY) {
      if(capacity > MAX_CAPACITY || capacity < SECTOR_SIZE) capacity = DEFAULT_CAPACITY;
      actual_capacity = capacity;
      selected_capacity = capacity;
      probe_upper = capacity;
      memset(storage, 0xFF, sizeof(storage));
      memset(sector_erases, 0, sizeof(sector_erases));
      erase_count = 0;
      programmed_bytes = 0;
      mutation_operations = 0;
      read_operations = 0;
      read_bytes = 0;
      fail_after_operations = -1;
      clearFailure();
    }

    static uint32_t eraseCount(void) { return erase_count; }
    static uint32_t sectorEraseCount(uint32_t sector) {
      return sector < MAX_CAPACITY / SECTOR_SIZE ? sector_erases[sector] : 0;
    }
    static uint64_t programmedBytes(void) { return programmed_bytes; }
    static uint32_t mutationOperations(void) { return mutation_operations; }
    static uint32_t readOperations(void) { return read_operations; }
    static uint64_t readBytes(void) { return read_bytes; }
    static void resetOperationCounts(void) {
      mutation_operations = 0;
      read_operations = 0;
      read_bytes = 0;
    }

    static void setReportedCapacity(uint32_t capacity) {
      selected_capacity = capacity;
      probe_upper = capacity;
    }
    static uint32_t actualCapacity(void) { return actual_capacity; }
    uint32_t capacityProbeUpper(void) const { return probe_upper; }
    bool setCapacity(uint32_t capacity) {
      if(capacity == 0 || capacity > actual_capacity) return false;
      selected_capacity = capacity;
      return true;
    }
    bool rawPrepare(uint32_t candidate) {
      (void) candidate;
      return true;
    }

    bool rawRead(uint32_t address, uint8_t* out, size_t len) const {
      if(out == NULL || actual_capacity == 0) return false;
      read_operations++;
      read_bytes += len;
      for(size_t i = 0; i < len; i++) out[i] = storage[(address + (uint32_t) i) % actual_capacity];
      return true;
    }

    bool rawWrite(uint32_t address, const uint8_t* data, size_t len) {
      if(data == NULL || actual_capacity == 0 || fails(address, len)) return false;
      for(size_t i = 0; i < len; i++) {
        const uint32_t target = (address + (uint32_t) i) % actual_capacity;
        if((storage[target] & data[i]) != data[i]) return false;
      }
      for(size_t i = 0; i < len; i++) {
        storage[(address + (uint32_t) i) % actual_capacity] &= data[i];
      }
      programmed_bytes += len;
      mutation_operations++;
      return true;
    }

    bool rawEraseSector(uint32_t address) {
      if(actual_capacity == 0 || fails(address, SECTOR_SIZE)) return false;
      const uint32_t base = (address % actual_capacity) & ~(SECTOR_SIZE - 1U);
      memset(storage + base, 0xFF, SECTOR_SIZE);
      erase_count++;
      sector_erases[base / SECTOR_SIZE]++;
      mutation_operations++;
      return true;
    }

    static void failAfterOperations(int32_t successful_operations) {
      fail_after_operations = successful_operations;
    }

    static void failRange(uint32_t begin, uint32_t end) {
      fail_begin = begin;
      fail_end = end;
    }

    static void clearFailure(void) {
      fail_begin = MAX_CAPACITY;
      fail_end = MAX_CAPACITY;
      fail_after_operations = -1;
    }

    static void corrupt(uint32_t address, uint8_t value) {
      if(address < actual_capacity) storage[address] = value;
    }

  private:
    static bool fails(uint32_t address, size_t len) {
      const uint32_t end = address + (uint32_t) len;
      if(address < fail_end && end > fail_begin) return true;
      if(fail_after_operations < 0) return false;
      if(fail_after_operations == 0) return true;
      fail_after_operations--;
      return false;
    }

    static inline uint8_t storage[MAX_CAPACITY];
    static inline uint32_t sector_erases[MAX_CAPACITY / SECTOR_SIZE];
    static inline uint32_t actual_capacity = DEFAULT_CAPACITY;
    static inline uint32_t selected_capacity = DEFAULT_CAPACITY;
    static inline uint32_t probe_upper = DEFAULT_CAPACITY;
    static inline uint32_t fail_begin = MAX_CAPACITY;
    static inline uint32_t fail_end = MAX_CAPACITY;
    static inline uint32_t erase_count;
    static inline uint64_t programmed_bytes;
    static inline uint32_t mutation_operations;
    static inline uint32_t read_operations;
    static inline uint64_t read_bytes;
    static inline int32_t fail_after_operations = -1;
};

#endif
