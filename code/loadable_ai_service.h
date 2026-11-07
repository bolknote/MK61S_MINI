#ifndef MK61_LOADABLE_AI_SERVICE_H
#define MK61_LOADABLE_AI_SERVICE_H
#include <stdint.h>
// Optional, independent service family. The common API and its capability
// bit assignments are unchanged. APPs check magic/version/size before calling.
#define MK61_APP_SERVICE_AI 2U
#define MK61_AI_SERVICE_VERSION 1U
#define MK61_AI_SERVICE_MAGIC 0x3149414dUL
typedef struct mk61_ai_service {
    uint32_t magic;
    uint16_t version,struct_size;
    uint32_t (*run)(uint32_t file_id);
} mk61_ai_service;
// Version 1 remains available to existing launchers.
#define MK61_AI_DIAGNOSTIC_VERSION 2U
typedef struct mk61_ai_diagnostic_service {
    uint32_t magic;
    uint16_t version,struct_size;
    uint32_t (*run)(uint32_t file_id);
    uint32_t (*benchmark)(const char* diagnostic_directory);
} mk61_ai_diagnostic_service;
#endif
