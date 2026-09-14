#ifndef MK61_PORTABLE_APP_CONFIG_H
#define MK61_PORTABLE_APP_CONFIG_H

/* There is no separate "user APP" permission. If the common loader is in the
 * firmware, APPLICATION is available with the same ABI, services, cache and
 * execution policy as canonical System APP. */
#ifdef MK61_ENABLE_USER_APPS
#error "MK61_ENABLE_USER_APPS was removed; use MK61_ENABLE_LOADABLE_MODULES"
#endif

/* There is one executable format. Stale switches fail loudly instead of
 * silently selecting a second loader or fixed-address image. */
#ifdef MK61_ENABLE_PORTABLE_APPS
#error "MK61_ENABLE_PORTABLE_APPS was removed; ABI 5 is mandatory"
#endif

#define MK61_PORTABLE_APP_ADDRESS 0x20000000UL
/* ABI 5 unifies System and ordinary APP startup: INITIALIZE always receives
 * mk61_app_api*, image CRC and Kind.  ABI 2/3/4 are deliberately rejected. */
#define MK61_CURRENT_APP_ABI 5U
#define MK61_RELOCATABLE_APP_ABI MK61_CURRENT_APP_ABI
#define MK61_APP_RELOCATABLE_FLAG 4U
#define MK61_PORTABLE_APP_FLAG 1U
#define MK61_APP_ARM_THUMB_BCJ_FLAG 2U

#endif
