/* Finite HIL helper: save one existing SETUP profile from a sibling text
 * file. Uses the same resident service as the settings dialog. */
#include "mk61_app.h"

uint32_t mk61_app_flow_step(mk61_app_flow* flow) {
  if(!mk61_app_flow_compatible(flow)) return 0;
  const mk61_app_services* s = mk61_app_get_services(mk61_api,
      MK61_SERVICE_CAP_FILES | MK61_SERVICE_CAP_SETUP | MK61_SERVICE_CAP_FORMAT);
  if(!s) return 0;
  mk61_service_file app = {0}, selection = {0};
  if(!s->call(MK61_SERVICE_FILE_ENTRY, 0, flow->current.file_id, 0, &app)) return 0;
  uint32_t step = 1, info = 0, saved = 0, status;
  uint8_t profile = 0;
  status = s->call(MK61_SERVICE_FILE_RESOLVE, app.parent, MK61_SERVICE_FILE_TEXT,
          (uint32_t)(uintptr_t)"profile.txt", &selection);
  if(status != 0 || selection.size != 1) goto finished;
  step = 2;
  if(mk61_api->file_read(selection.id, 0, &profile, 1) != 1 ||
      profile < '0' || profile > '7') goto finished;
  profile -= '0';
  step = 3;
  info = s->call(MK61_SERVICE_SETUP, MK61_SETUP_COMPUTE_CLOCK, 0, 0, NULL);
  if(profile >= (info >> 24) ||
      !s->call(MK61_SERVICE_SETUP, MK61_SETUP_COMPUTE_CLOCK, 1, profile, NULL)) goto finished;
  const uint32_t began = mk61_api->millis_ms();
  while((uint32_t)(mk61_api->millis_ms() - began) < 2000U) {
    mk61_api->service();
    mk61_api->delay_ms(5);
  }
  saved = s->call(MK61_SERVICE_SETUP, MK61_SETUP_COMPUTE_CLOCK, 0, 0, NULL);
  step = (saved & 255U) == profile ? 4 : 5;
finished:;
  char report[160];
  int length = mk61_app_snprintf(s, report, sizeof(report),
      "SELECT STEP=%lu STATUS=%lu SIZE=%lu VALUE=%u INFO=%lu SAVED=%lu\n",
      (unsigned long)step, (unsigned long)status, (unsigned long)selection.size,
      (unsigned)profile, (unsigned long)info, (unsigned long)saved);
  if(length > 0 && length < (int)sizeof(report)) {
    mk61_service_write file = {"select", (const uint8_t*)report, (uint32_t)length, MK61_SERVICE_INVALID_ID};
    s->call(MK61_SERVICE_FILE_WRITE, app.parent, MK61_SERVICE_INVALID_ID, MK61_SERVICE_FILE_TEXT, &file);
  }
  mk61_app_flow_exit(flow, step == 4 ? MK61_APP_OK : MK61_APP_RUNTIME_ERROR,
      MK61_FLOW_OK);
  return 1; /* FLOW_STEP accepted and populated flow->action. */
}
