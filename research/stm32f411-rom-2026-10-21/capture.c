/* Temporary RAM APP: read factory System Memory, never program the MCU. */
#include "mk61_app.h"
#include <stdint.h>

static int write_binary(const mk61_app_services* services, const char* name,
                        const void* data, uint32_t size) {
  mk61_service_write request = {name, (const uint8_t*)data, size,
                                MK61_SERVICE_INVALID_ID};
  return services->call(MK61_SERVICE_FILE_WRITE, MK61_SERVICE_ROOT_ID,
      MK61_SERVICE_INVALID_ID, MK61_SERVICE_FILE_MK61_BINARY, &request);
}

int main(void) {
  const mk61_app_services* services =
      mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FILES);
  if (!services) return MK61_APP_RUNTIME_ERROR;
  const volatile uint8_t* rom = (const volatile uint8_t*)0x1FFF0000u;
  uint32_t crc = 0xFFFFFFFFu;
  for (uint32_t i = 0; i < 0x7800u; ++i) {
    crc ^= rom[i];
    for (unsigned b = 0; b < 8; ++b)
      crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    if ((i & 1023u) == 0) mk61_api->service();
  }
  uint32_t info[] = {0x314D4F52u, 0x1FFF0000u, 0x7800u, ~crc,
    *(const volatile uint32_t*)0xE000ED00u,
    *(const volatile uint32_t*)0xE0042000u,
    *(const volatile uint16_t*)0x1FFF7A22u};
  /* The binary file type has a 4096-byte limit. */
  for (unsigned i = 0; i < 8; ++i) {
    char name[] = "ROMC0";
    name[4] += i;
    if (!write_binary(services, name, (const void*)(rom + i * 4096u),
                      i == 7 ? 2048u : 4096u)) return MK61_APP_IO_ERROR;
  }
  if (!write_binary(services, "ROMINFO", info, sizeof(info)))
    return MK61_APP_IO_ERROR;
  return MK61_APP_OK;
}
