#ifndef MK61_FOCAL_TRACE_HPP
#define MK61_FOCAL_TRACE_HPP
#include <stdint.h>
#if defined(MK61_FOCAL_TRACE) && MK61_FOCAL_TRACE
#if defined(MK61_BUILD_PORTABLE_SYSTEM)
#include <stdio.h>
#include <string.h>
inline void focal_trace_write(const char *text) {
  if (portable_system::call(MK61_SERVICE_CAPABILITIES) &
      MK61_SERVICE_CAP_DEBUG_IO)
    (void)portable_system::call(MK61_SERVICE_DEBUG_WRITE, (u32)strlen(text), 0,
                                0, (void *)text);
}
inline void focal_trace_message(const char *action, const char *text) {
  char line[128];
  snprintf(line, sizeof(line), "FOCAL %s %s\n", action, text ? text : "");
  focal_trace_write(line);
}
inline void focal_trace_execution(const char *instruction, uint16_t pc,
                                  double source_line) {
  char line[96];
  snprintf(line, sizeof(line), "FOCAL EXEC line=%u pc=%u op=%u\n",
           (unsigned)source_line, (unsigned)pc,
           (unsigned)(uint8_t)*instruction);
  focal_trace_write(line);
}
#else
#ifdef FOCAL_HOST_TEST
#include "../tests/focal_host_fixture.hpp"
#define FOCAL_TRACE_SINK focal_host_fixture::serial
#else
#include "Arduino.h"
#define FOCAL_TRACE_SINK Serial
#endif
inline void focal_trace_message(const char *action, const char *text) {
  FOCAL_TRACE_SINK.print("FOCAL ");
  FOCAL_TRACE_SINK.print(action);
  if (text) {
    FOCAL_TRACE_SINK.print(" ");
    FOCAL_TRACE_SINK.print(text);
  }
  FOCAL_TRACE_SINK.println();
  FOCAL_TRACE_SINK.flush();
}
inline void focal_trace_execution(const char *instruction, uint16_t pc,
                                  double line) {
  FOCAL_TRACE_SINK.print("FOCAL EXEC line=");
  FOCAL_TRACE_SINK.print((unsigned)line);
  FOCAL_TRACE_SINK.print(" pc=");
  FOCAL_TRACE_SINK.print((unsigned)pc);
  FOCAL_TRACE_SINK.print(" op=");
  FOCAL_TRACE_SINK.print((unsigned)(uint8_t)*instruction);
  FOCAL_TRACE_SINK.println();
  FOCAL_TRACE_SINK.flush();
}
#endif
#else
inline void focal_trace_message(const char *, const char *) {}
inline void focal_trace_execution(const char *, uint16_t, double) {}
#endif
#endif
