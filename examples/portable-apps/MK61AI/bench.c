#include "mk61_app.h"
#include "loadable_ai_service.h"
#ifndef MK61_AI_DIAGNOSTIC_DIRECTORY
#define MK61_AI_DIAGNOSTIC_DIRECTORY "/AI/DIAG"
#endif
int main(void){
    const mk61_ai_diagnostic_service* s=(const mk61_ai_diagnostic_service*)mk61_api->query_service(MK61_APP_SERVICE_AI,MK61_AI_DIAGNOSTIC_VERSION);
    if(!s||s->magic!=MK61_AI_SERVICE_MAGIC||s->struct_size<sizeof(*s)||!s->benchmark)return MK61_APP_RUNTIME_ERROR;
    return (int)s->benchmark(MK61_AI_DIAGNOSTIC_DIRECTORY);
}
