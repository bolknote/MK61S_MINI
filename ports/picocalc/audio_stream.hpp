#ifndef MK61_PICOCALC_AUDIO_STREAM_HPP
#define MK61_PICOCALC_AUDIO_STREAM_HPP
#include "loadable_app_services.h"
namespace picocalc::audio_stream {
bool active();
void close();
uint32_t call(uint32_t operation,mk61_service_audio* request,unsigned master_volume);
uint32_t synth(const mk61_service_audio_synth& request,unsigned master_volume);
}
#endif
