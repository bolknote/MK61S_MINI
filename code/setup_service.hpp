#ifndef MK61_SETUP_SERVICE_HPP
#define MK61_SETUP_SERVICE_HPP
#include "rust_types.h"
#include "loadable_system_api.h"
namespace setup_ui {
u32 service(u32 operation, u32 a = 0, u32 b = 0, void* payload = nullptr);
}
#endif
