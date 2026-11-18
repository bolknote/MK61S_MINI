#pragma once
#ifdef __cplusplus
extern "C" {
#endif
enum Phase {
    PH_FRAME,
    PH_PRESENT,
    PH_HASH,
    PH_TIMER,
    PH_FENCE,
    PH_NEXT,
    PH_AUDIO,
    PH_POLYGON,
    PH_COPY,
    PH_FILL,
    PH_PREP,
    PH_SUBMIT = PH_PREP + 8,
    PH_QUEUE = PH_SUBMIT + 8,
    PH_COUNT = PH_QUEUE + 8
};
unsigned ph_enter(unsigned phase);
void ph_leave(unsigned saved);
unsigned ph_prepare(unsigned x, unsigned y, unsigned w, unsigned h, unsigned fill);
#ifdef __cplusplus
}
#endif
