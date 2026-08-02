#include "../code/msc_memory_policy.h"

#include <assert.h>
#include <stdio.h>

#ifndef MK61_EXPECTED_MSC_PACKET_BYTES
#error "MK61_EXPECTED_MSC_PACKET_BYTES is required"
#endif

_Static_assert(MSC_MEDIA_PACKET == MK61_EXPECTED_MSC_PACKET_BYTES,
               "MSC packet policy differs");

int main(void) {
  assert(MSC_MEDIA_PACKET == MK61_EXPECTED_MSC_PACKET_BYTES);
  printf("msc_memory_policy_self_test: %u bytes\n",
         (unsigned) MSC_MEDIA_PACKET);
  return 0;
}
