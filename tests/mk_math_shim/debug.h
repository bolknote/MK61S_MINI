// Хостовая заглушка debug.h. Принудительно подключается (clang -include) до
// настоящего code/debug.h и, занимая его защитный макрос, полностью подавляет
// макросы прошивки. Они приводят указатели к usize с потерями, что является
// безусловной ошибкой на 64-разрядном хосте, поэтому заменяются пустыми операциями.
#ifndef DEBUG_OUTPUT_TO_SERIAL
#define DEBUG_OUTPUT_TO_SERIAL

#define dbg(MODULE, ...)        do {} while(0)
#define dbgln(MODULE, ...)      do {} while(0)
#define dbghex(MODULE, ...)     do {} while(0)
#define dbghexln(MODULE, ...)   do {} while(0)
#define dbgtrace(MODULE, ...)   do {} while(0)

#endif
