#ifndef MK61_CLASSIC_TIMER_HPP
#define MK61_CLASSIC_TIMER_HPP

#include "classic_scheduler.hpp"
#include "rust_types.h"

namespace classic_timer {

// Аппаратно-зависимый объект создаётся явно из setup(), после premain.
void construct(void);
void initialize(void);

// synchronize() одновременно управляет фазой таймера. Переход false -> true
// начинает новый полный CLASSIC-период; повторный вызов с тем же состоянием
// дешёв и используется как страховка в общем цикле.
void synchronize(bool active);
bool take_step(void);

void reset_statistics(void);
classic_scheduler::Snapshot statistics(void);

const char* backend_name(void);
u32 configured_period_us(void);

} // namespace classic_timer

#endif
