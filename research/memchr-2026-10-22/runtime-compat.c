/* Exercise new SDK dispatch against exact old tables and truncated tails.
 * ASan must trap any attempted read of old_table[26] or runtime_count. */
#include "mk61_app.h"
#include <assert.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#if __has_feature(address_sanitizer)
#include <sanitizer/asan_interface.h>
#endif
typedef void* (*Search)(const void*,int,size_t);
extern Search mk61_optional_memchr;
extern void* mk61_memchr_fallback(const void*,int,size_t);
extern int mk61_app_bind_runtime(const mk61_app_api*);
const mk61_app_api* mk61_api;
static mk61_app_services services;
static unsigned queries,resident_calls;
static uint32_t call(uint32_t op,uint32_t a,uint32_t b,uint32_t c,void* payload) {
  assert(op==MK61_SERVICE_CAPABILITIES && !a && !b && !c && !payload);
  return MK61_SERVICE_CAP_RUNTIME;
}
static const void* query(uint32_t id,uint32_t version) {
  ++queries;
  assert(id==MK61_APP_SERVICE_COMMON && version==MK61_APP_SERVICES_VERSION);
  return &services;
}
static void helper(void) {}
static void* resident(const void* data,int value,size_t size) {
  ++resident_calls;
  const unsigned char* p=data;
  for(size_t i=0;i<size;++i) if(p[i]==(unsigned char)value)return (void*)(p+i);
  return NULL;
}
static void exercise(Search resolver,Search expected) {
  static const unsigned char bytes[]={0x80,0,0xff,0x80,1};
  mk61_optional_memchr=resolver;queries=resident_calls=0;
  assert(mk61_optional_memchr(bytes,-1,sizeof bytes)==bytes+2);
  assert(mk61_optional_memchr==expected);
  assert(queries==1);
  assert(mk61_optional_memchr(bytes,0x180,sizeof bytes)==bytes);
  assert(mk61_optional_memchr(bytes,1,4)==NULL);
  assert(mk61_optional_memchr(NULL,0,0)==NULL);
  assert(queries==1 && resident_calls==(expected==resident?4u:0u));
}
int main(void) {
  const Search resolver=mk61_optional_memchr;
  mk61_app_api api={0};api.magic=MK61_APP_API_MAGIC;
  api.version=MK61_APP_API_VERSION;api.struct_size=sizeof api;api.query_service=query;
  mk61_api=&api;
  services.magic=MK61_APP_SERVICES_MAGIC;services.version=MK61_APP_SERVICES_VERSION;
  services.call=call;services.struct_size=sizeof services;
  mk61_service_runtime_function* old_table=malloc(MK61_RUNTIME_BASE_COUNT*sizeof(*old_table));
  assert(old_table);
  for(unsigned i=0;i<MK61_RUNTIME_BASE_COUNT;++i)old_table[i]=helper;
  services.runtime=old_table;services.struct_size=MK61_APP_SERVICES_BASE_SIZE;
#if __has_feature(address_sanitizer)
  __asan_poison_memory_region(&services.runtime_count,sizeof services - offsetof(mk61_app_services,runtime_count));
#endif
  assert(mk61_app_get_services(&api,0)==&services);
  assert(mk61_app_runtime_count(&services)==26 && mk61_app_bind_runtime(&api));
  exercise(resolver,mk61_memchr_fallback);
#if __has_feature(address_sanitizer)
  __asan_unpoison_memory_region(&services.runtime_count,sizeof services - offsetof(mk61_app_services,runtime_count));
#endif
  mk61_service_runtime_function table[MK61_RUNTIME_COUNT];
  for(unsigned i=0;i<MK61_RUNTIME_COUNT;++i)table[i]=helper;
  table[MK61_RUNTIME_SLOT_memchr]=(mk61_service_runtime_function)resident;
  services.runtime=table;services.runtime_count=MK61_RUNTIME_COUNT;services.struct_size=sizeof services;
  assert(mk61_app_bind_runtime(&api));exercise(resolver,resident);
  services.runtime_count=26;exercise(resolver,mk61_memchr_fallback);
  services.runtime_count=25;assert(!mk61_app_bind_runtime(&api));exercise(resolver,mk61_memchr_fallback);
  services.runtime_count=MK61_RUNTIME_COUNT;table[MK61_RUNTIME_SLOT_memchr]=NULL;
  exercise(resolver,mk61_memchr_fallback);
  services.struct_size=MK61_APP_SERVICES_BASE_SIZE-1;
  assert(!mk61_app_get_services(&api,0));exercise(resolver,mk61_memchr_fallback);
  free(old_table);
  puts("PASS: exact 26-slot old host, poisoned tail, 27-slot host, malformed count, null slot, truncated services; one-time binding");
}
