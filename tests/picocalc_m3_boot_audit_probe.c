/* Read-only UART qualification of the updater's real client and baud switch. */
#define main unused_updater_main
#include "../examples/portable-apps/BIOSUPD/main.c"
#undef main
int main(void) {
  svc = mk61_app_get_services(mk61_api, MK61_SERVICE_CAP_FORMAT |
                                            MK61_SERVICE_CAP_DEBUG_IO);
  if (!svc)
    return MK61_APP_RUNTIME_ERROR;
  if (!stm3_pico_uart1_begin(&uart, micros, 0, 48000000, 2250000)) {
    debug("M3AUDIT CLAIM_FAIL\n");
    return MK61_APP_OK;
  }
  for (unsigned phase = 0; phase < 4; ++phase) {
    if (phase == 1 || phase == 3)
      baud(2250000);
    if (phase == 2)
      baud(M3B_BAUD);
    reply_bytes = 0;
    memset(reply, 0, sizeof(reply));
    int error = request(phase == 2 ? M3B_WIRE_VERSION : 1, 1, 0, 0, 300000);
    char text[256];
    mk61_app_snprintf(
        svc, text, sizeof(text),
        "M3AUDIT phase=%u error=%d bytes=%u abi=%08lX target=%08lX state=%lu "
        "flags=%08lX uart_errors=%lu ibrd=%lu fbrd=%lu\n",
        phase, error, reply_bytes, (unsigned long)m3b_get(reply),
        (unsigned long)m3b_get(reply + 4), (unsigned long)m3b_get(reply + 16),
        (unsigned long)m3b_get(reply + 32), (unsigned long)uart.errors,
        (unsigned long)REG(0x40038024u), (unsigned long)REG(0x40038028u));
    debug(text);
  }
  stm3_pico_uart1_end(&uart);
  debug("M3AUDIT DONE\n");
  return MK61_APP_OK;
}
