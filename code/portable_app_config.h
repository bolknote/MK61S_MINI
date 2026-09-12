#ifndef MK61_PORTABLE_APP_CONFIG_H
#define MK61_PORTABLE_APP_CONFIG_H

/* Running user-supplied APP files is an explicit firmware capability.  F401
 * may still use the same loader for canonical System APP while this remains
 * disabled. */
#ifndef MK61_ENABLE_USER_APPS
#define MK61_ENABLE_USER_APPS 0
#endif
#if MK61_ENABLE_USER_APPS != 0 && MK61_ENABLE_USER_APPS != 1
#error "MK61_ENABLE_USER_APPS must be 0 or 1"
#endif

/* Bundle builders enable ABI 4 and export free-RAM linker bounds. This is
 * the virtual link base, never a reservation or a physical load address.
 * A generic user-APP build selects ABI 4 automatically; the F401 builders
 * set this independently because their System APP also use the portable ABI. */
#ifndef MK61_ENABLE_PORTABLE_APPS
#define MK61_ENABLE_PORTABLE_APPS MK61_ENABLE_USER_APPS
#endif
#if MK61_ENABLE_PORTABLE_APPS != 0 && MK61_ENABLE_PORTABLE_APPS != 1
#error "MK61_ENABLE_PORTABLE_APPS must be 0 or 1"
#endif

#define MK61_PORTABLE_APP_ADDRESS 0x20000000UL
#define MK61_PORTABLE_APP_ABI 3U
#define MK61_RELOCATABLE_APP_ABI 4U
#define MK61_APP_RELOCATABLE_FLAG 4U
#define MK61_PORTABLE_APP_FLAG 1U
#define MK61_APP_ARM_THUMB_BCJ_FLAG 2U

#endif
