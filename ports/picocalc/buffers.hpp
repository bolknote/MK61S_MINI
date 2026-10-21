#ifndef MK61_PICOCALC_BUFFERS_HPP
#define MK61_PICOCALC_BUFFERS_HPP
#include "shared_memory.hpp"
namespace picocalc::buffers {
bool init();
struct TestResult { bool passed; u32 bytes, allocation, write_us, read_us; };
TestResult self_test(void (*service)() = nullptr);
}
#endif
