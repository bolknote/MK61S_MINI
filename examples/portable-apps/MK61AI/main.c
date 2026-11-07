#include "mk61_app.h"
#include "loadable_ai_service.h"
static uint32_t launch(uint32_t file) {
    const mk61_ai_service* service=(const mk61_ai_service*)mk61_api->query_service(MK61_APP_SERVICE_AI,MK61_AI_SERVICE_VERSION);
    if(!service || service->magic!=MK61_AI_SERVICE_MAGIC || service->version!=MK61_AI_SERVICE_VERSION ||
       service->struct_size<sizeof(*service) || !service->run) {
        mk61_api->display_clear();
        mk61_api->display_write_m8(0,0,"Update Pico firmware",20);
        mk61_api->key_wait();return MK61_APP_RUNTIME_ERROR;
    }
    return service->run(file);
}
uint32_t mk61_app_open_file(uint32_t file) {return launch(file);}
int main(void){return (int)launch(MK61_SERVICE_INVALID_ID);}
