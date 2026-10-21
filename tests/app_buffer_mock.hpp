#ifndef MK61_TEST_APP_BUFFER_MOCK_HPP
#define MK61_TEST_APP_BUFFER_MOCK_HPP
#include <vector>
#include <cassert>
#include <cstring>
struct AppBufferMock {
  std::vector<uint8_t> bytes;
  bool enabled=false,active=false,fail_read=false,fail_write=false,fail_acquire=false;
  unsigned acquires=0,releases=0,reads=0,writes=0;
  uint32_t capabilities() const {
    return enabled?MK61_SERVICE_CAP_BUFFERS|MK61_SERVICE_CAP_EXTERNAL_BUFFERS:0;
  }
  uint32_t call(uint32_t operation,uint32_t b,uint32_t c,void* payload) {
    assert(!b && c==sizeof(mk61_service_buffer) && payload);
    auto& r=*(mk61_service_buffer*)payload;
    if(!enabled) return 0;
    if(operation==MK61_BUFFER_ACQUIRE) {
      assert(!active && !r.handle && r.size && r.access==MK61_BUFFER_EXTERNAL);
      if(fail_acquire) return 0;
      bytes.assign(r.size,0xA7);active=true;++acquires;
      r.handle=1;r.storage=MK61_BUFFER_PSRAM;r.data=nullptr;return 1;
    }
    assert(active && r.handle==1);
    if(operation==MK61_BUFFER_RELEASE) { active=false;++releases;r={};return 1; }
    assert(r.offset<=bytes.size() && r.size<=bytes.size()-r.offset && r.size<=MK61_BUFFER_IO_BYTES);
    if(operation==MK61_BUFFER_READ) {
      ++reads;if(fail_read)return 0;std::memcpy(r.data,bytes.data()+r.offset,r.size);return 1;
    }
    assert(operation==MK61_BUFFER_WRITE);
    ++writes;if(fail_write)return 0;std::memcpy(bytes.data()+r.offset,r.data,r.size);return 1;
  }
};
#endif
