// Host shim of debug.h. Force-included (clang -include) so it runs before the
// real code/debug.h; by claiming that header's include guard it suppresses the
// firmware macros entirely. Those macros perform pointer-to-usize casts that are
// lossy (and thus hard errors) on a 64-bit host, so we replace them with no-ops.
#ifndef DEBUG_OUTPUT_TO_SERIAL
#define DEBUG_OUTPUT_TO_SERIAL

#define dbg(MODULE, ...)        do {} while(0)
#define dbgln(MODULE, ...)      do {} while(0)
#define dbghex(MODULE, ...)     do {} while(0)
#define dbghexln(MODULE, ...)   do {} while(0)
#define dbgtrace(MODULE, ...)   do {} while(0)

#endif
