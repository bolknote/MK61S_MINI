#ifndef MK61_USB_DISK_SESSION_HPP
#define MK61_USB_DISK_SESSION_HPP

#include "rust_types.h"

namespace usb_disk_session {

// Control-plane state only. Sector bytes remain owned by virtual_fat and its
// persistent staging journal; this model decides when the host may be
// acknowledged and what an interrupted USB session is allowed to publish.
enum class State : u8 {
  CLOSED = 0,
  CLEAN,
  DIRTY,
  VALIDATING,
  COMMITTING,
  REJECTED,
  IO_FAILED,
  CLOSING,
  COUNT
};

enum class Event : u8 {
  OPEN = 0,
  WRITE_ACCEPTED,
  SYNC_REQUEST,
  SERVICE,
  COMMIT_OK,
  COMMIT_REJECTED,
  COMMIT_IO_FAILED,
  CLOSE_REQUEST,
  FINALIZE_OK,
  FINALIZE_REJECTED,
  FINALIZE_IO_FAILED,
  DISCONNECT,
  RESET,
  COUNT
};

enum class Action : u8 {
  NONE = 0,
  SESSION_OPENED,
  WRITE_TRACKED,
  SYNC_QUEUED,
  COMMIT_STARTED,
  SYNC_SUCCEEDED,
  SYNC_REJECTED,
  SYNC_IO_FAILED,
  FINALIZE_STARTED,
  CLOSE_SUCCEEDED,
  CLOSE_REJECTED,
  CLOSE_IO_FAILED,
  SESSION_ABORTED,
  REJECT_EVENT
};

struct Transition {
  State next;
  Action action;
  bool accepted;
};

constexpr Transition reject(State state) {
  return {state, Action::REJECT_EVENT, false};
}

constexpr Transition accept(State state, Action action) {
  return {state, action, true};
}

constexpr bool may_accept_write(State state) {
  return state == State::CLEAN || state == State::DIRTY ||
         state == State::REJECTED || state == State::IO_FAILED;
}

constexpr bool may_request_sync(State state) {
  return may_accept_write(state);
}

constexpr bool is_open(State state) {
  return state != State::CLOSED;
}

constexpr u8 packed(State state, Action action) {
  return (u8) (((u8) action << 3) | (u8) state);
}

constexpr u8 rejected(State state) {
  return packed(state, Action::REJECT_EVENT);
}

// One byte per state/event pair: low three bits are the next state and the
// upper four bits are the action. Besides being easy to audit, this is much
// smaller on the Flash-constrained F401 than several inlined switch ladders.
static constexpr u8 TRANSITIONS[(u8) State::COUNT][(u8) Event::COUNT] = {
  // OPEN, WRITE, SYNC, SERVICE, COMMIT OK/REJECT/IO, CLOSE,
  // FINAL OK/REJECT/IO, DISCONNECT, RESET
  {
    packed(State::CLEAN, Action::SESSION_OPENED),
    rejected(State::CLOSED), rejected(State::CLOSED),
    rejected(State::CLOSED), rejected(State::CLOSED),
    rejected(State::CLOSED), rejected(State::CLOSED),
    rejected(State::CLOSED), rejected(State::CLOSED),
    rejected(State::CLOSED), rejected(State::CLOSED),
    packed(State::CLOSED, Action::NONE), packed(State::CLOSED, Action::NONE)
  },
  {
    rejected(State::CLEAN), packed(State::DIRTY, Action::WRITE_TRACKED),
    packed(State::VALIDATING, Action::SYNC_QUEUED), rejected(State::CLEAN),
    rejected(State::CLEAN), rejected(State::CLEAN), rejected(State::CLEAN),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::CLEAN), rejected(State::CLEAN), rejected(State::CLEAN),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::DIRTY), packed(State::DIRTY, Action::WRITE_TRACKED),
    packed(State::VALIDATING, Action::SYNC_QUEUED), rejected(State::DIRTY),
    rejected(State::DIRTY), rejected(State::DIRTY), rejected(State::DIRTY),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::DIRTY), rejected(State::DIRTY), rejected(State::DIRTY),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::VALIDATING), rejected(State::VALIDATING),
    rejected(State::VALIDATING),
    packed(State::COMMITTING, Action::COMMIT_STARTED),
    rejected(State::VALIDATING), rejected(State::VALIDATING),
    rejected(State::VALIDATING),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::VALIDATING), rejected(State::VALIDATING),
    rejected(State::VALIDATING),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::COMMITTING), rejected(State::COMMITTING),
    rejected(State::COMMITTING), rejected(State::COMMITTING),
    packed(State::CLEAN, Action::SYNC_SUCCEEDED),
    packed(State::REJECTED, Action::SYNC_REJECTED),
    packed(State::IO_FAILED, Action::SYNC_IO_FAILED),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::COMMITTING), rejected(State::COMMITTING),
    rejected(State::COMMITTING),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::REJECTED), packed(State::DIRTY, Action::WRITE_TRACKED),
    packed(State::VALIDATING, Action::SYNC_QUEUED), rejected(State::REJECTED),
    rejected(State::REJECTED), rejected(State::REJECTED),
    rejected(State::REJECTED),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::REJECTED), rejected(State::REJECTED),
    rejected(State::REJECTED),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::IO_FAILED), packed(State::DIRTY, Action::WRITE_TRACKED),
    packed(State::VALIDATING, Action::SYNC_QUEUED), rejected(State::IO_FAILED),
    rejected(State::IO_FAILED), rejected(State::IO_FAILED),
    rejected(State::IO_FAILED),
    packed(State::CLOSING, Action::FINALIZE_STARTED),
    rejected(State::IO_FAILED), rejected(State::IO_FAILED),
    rejected(State::IO_FAILED),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  },
  {
    rejected(State::CLOSING), rejected(State::CLOSING),
    rejected(State::CLOSING), rejected(State::CLOSING),
    rejected(State::CLOSING), rejected(State::CLOSING),
    rejected(State::CLOSING), rejected(State::CLOSING),
    packed(State::CLOSED, Action::CLOSE_SUCCEEDED),
    packed(State::CLOSED, Action::CLOSE_REJECTED),
    packed(State::CLOSED, Action::CLOSE_IO_FAILED),
    packed(State::CLOSED, Action::SESSION_ABORTED),
    packed(State::CLOSED, Action::SESSION_ABORTED)
  }
};

// Firmware, replay tests and host tooling consume the same transition table.
constexpr Transition transition(State state, Event event) {
  if((u8) state >= (u8) State::COUNT ||
     (u8) event >= (u8) Event::COUNT) return reject(State::CLOSED);
  const u8 value = TRANSITIONS[(u8) state][(u8) event];
  const Action action = (Action) (value >> 3);
  return {(State) (value & 0x07U), action,
          action != Action::REJECT_EVENT};
}

static_assert(sizeof(State) == 1 && sizeof(Event) == 1 && sizeof(Action) == 1,
              "USB disk session model must remain byte-sized");
static_assert(transition(State::REJECTED, Event::WRITE_ACCEPTED).next ==
              State::DIRTY,
              "a host must be able to repair a rejected staging transaction");
static_assert(transition(State::IO_FAILED, Event::DISCONNECT).next ==
              State::CLOSED,
              "disconnect must never publish retryable staging");

} // namespace usb_disk_session

#endif
