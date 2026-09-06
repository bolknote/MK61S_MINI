#include "mk61_app.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#if __has_feature(address_sanitizer)
#include <sanitizer/asan_interface.h>
#endif

extern int mk61_app_bind_runtime(const mk61_app_api*);
static mk61_app_services services;
static unsigned queries, calls;
static uint32_t capabilities;

static uint32_t call(uint32_t operation, uint32_t a, uint32_t b,
                     uint32_t c, void* payload) {
  assert(operation == MK61_SERVICE_CAPABILITIES);
  assert(!a && !b && !c && !payload);
  ++calls;
  return capabilities;
}
static const void* query(uint32_t id, uint32_t version) {
  ++queries;
  return id == MK61_APP_SERVICE_COMMON && version == MK61_APP_SERVICES_VERSION
      ? &services : NULL;
}
static void helper(void) {}

int main(void) {
  /* Poison the unavailable tail: ASan catches reading a newer field while
   * preserving a complete C object for the object-size sanitizer. */
  mk61_app_api* old = (mk61_app_api*) calloc(1, sizeof(*old));
  assert(old);
  old->magic = MK61_APP_API_MAGIC;
  old->version = MK61_APP_API_VERSION;
  old->struct_size = offsetof(mk61_app_api, query_service);
#if __has_feature(address_sanitizer)
  __asan_poison_memory_region(&old->query_service, sizeof(old->query_service));
#endif
  assert(!mk61_app_api_compatible(old, sizeof(*old), 0));
  assert(!mk61_app_get_services(old, 0));
  assert(!mk61_app_bind_runtime(old));
  free(old);
  assert(!queries && !calls);

  mk61_app_api api = {0};
  api.magic = MK61_APP_API_MAGIC;
  api.version = MK61_APP_API_VERSION;
  api.struct_size = sizeof(api);
  assert(!mk61_app_get_services(&api, 0));
  api.query_service = query;
  assert(!mk61_app_get_services(NULL, 0));
  assert(!query(0xFFFFFFFFU, 1) && !query(MK61_APP_SERVICE_COMMON, 2));
  assert(!mk61_app_get_services(&api, 0));
  services.magic = MK61_APP_SERVICES_MAGIC;
  services.version = MK61_APP_SERVICES_VERSION;
  services.struct_size = sizeof(services);
  assert(!mk61_app_get_services(&api, 0));
  services.call = call;
  assert(mk61_app_get_services(&api, 0) == &services && !calls);
  capabilities = MK61_SERVICE_CAP_FILES;
  assert(mk61_app_get_services(&api, MK61_SERVICE_CAP_FILES) == &services);
  assert(!mk61_app_get_services(&api, MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_MATH));
  services.struct_size--;
  assert(!mk61_app_get_services(&api, 0));
  services.struct_size++;
  services.version++;
  assert(!mk61_app_get_services(&api, 0));
  services.version--;
  capabilities |= MK61_SERVICE_CAP_RUNTIME;
  assert(!mk61_app_bind_runtime(&api));
  mk61_service_runtime_function runtime[MK61_RUNTIME_COUNT];
  for(unsigned i = 0; i < MK61_RUNTIME_COUNT; ++i) runtime[i] = helper;
  services.runtime = runtime;
  assert(mk61_app_bind_runtime(&api));
  runtime[MK61_RUNTIME_COUNT - 1] = NULL;
  assert(!mk61_app_bind_runtime(&api));
  puts("APP services: truncated tables, versions, capabilities and runtime validation PASS");
  return 0;
}
