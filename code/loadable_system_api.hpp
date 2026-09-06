#ifndef MK61_LOADABLE_SYSTEM_API_HPP
#define MK61_LOADABLE_SYSTEM_API_HPP
#include "loadable_system_api.h"
namespace loadable_module {
const mk61_system_api& system_api();
const void* query_service(uint32_t service_id, uint32_t version);
}
#endif
