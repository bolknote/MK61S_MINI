#ifndef PROGRAM_STORE_HOST_SPIFLASH_H
#define PROGRAM_STORE_HOST_SPIFLASH_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

class SPIFlash {
  public:
    static constexpr uint32_t SECTOR_SIZE = 4096;
    static constexpr uint32_t CAPACITY = 2U * 1024U * 1024U;

    SPIFlash(uint8_t = 0) {}

    bool begin(uint32_t = 0) { return true; }
    uint32_t getCapacity(void) const { return CAPACITY; }

    uint8_t readByte(uint32_t address) const {
      return address < CAPACITY ? storage[address] : 0xFF;
    }

    bool readByteArray(uint32_t address, uint8_t* out, size_t len) const {
      if(out == NULL || address > CAPACITY || len > CAPACITY - address) return false;
      memcpy(out, storage + address, len);
      return true;
    }

    bool writeByte(uint32_t address, uint8_t value, bool = true) {
      return writeByteArray(address, &value, 1);
    }

    bool writeByteArray(uint32_t address, uint8_t* data, size_t len, bool = true) {
      if(data == NULL || address > CAPACITY || len > CAPACITY - address || fails(address, len)) return false;
      for(size_t i = 0; i < len; i++) {
        if((storage[address + i] & data[i]) != data[i]) return false;
      }
      for(size_t i = 0; i < len; i++) storage[address + i] &= data[i];
      programmed_bytes += len;
      return true;
    }

    bool eraseSector(uint32_t address) {
      const uint32_t base = address - address % SECTOR_SIZE;
      if(base >= CAPACITY || fails(base, SECTOR_SIZE)) return false;
      memset(storage + base, 0xFF, SECTOR_SIZE);
      erase_count++;
      return true;
    }

    static void reset(void) {
      memset(storage, 0xFF, sizeof(storage));
      erase_count = 0;
      programmed_bytes = 0;
      fail_after_operations = -1;
      clearFailure();
    }

    static uint32_t eraseCount(void) { return erase_count; }
    static uint64_t programmedBytes(void) { return programmed_bytes; }

    static void failAfterOperations(int32_t successful_operations) {
      fail_after_operations = successful_operations;
    }

    static void failRange(uint32_t begin, uint32_t end) {
      fail_begin = begin;
      fail_end = end;
    }

    static void clearFailure(void) {
      fail_begin = CAPACITY;
      fail_end = CAPACITY;
      fail_after_operations = -1;
    }

    static void corrupt(uint32_t address, uint8_t value) {
      if(address < CAPACITY) storage[address] = value;
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

    static inline uint8_t storage[CAPACITY];
    static inline uint32_t fail_begin = CAPACITY;
    static inline uint32_t fail_end = CAPACITY;
    static inline uint32_t erase_count;
    static inline uint64_t programmed_bytes;
    static inline int32_t fail_after_operations = -1;
};

#endif
