/* The measured veneer is the unmodified sdk/portable/system/runtime.S.
 * Hardware binds this pointer to the actual host's 26-slot runtime table. */
#include "loadable_app_services.h"
const mk61_service_runtime_function* bench_strlen_runtime;
_Static_assert(MK61_RUNTIME_COUNT == 26, "No runtime ABI extension");
_Static_assert(MK61_RUNTIME_SLOT_strlen == 20, "Use the actual strlen slot");
