#ifndef MK61_SPI1_ARBITER_HPP
#define MK61_SPI1_ARBITER_HPP

#include "rust_types.h"

namespace spi1_arbiter {

enum class Owner : u8 {
  NONE,
  DISPLAY_CLIENT,
  FLASH_CLIENT
};

enum class State : u8 {
  IDLE,
  ACTIVE,
  ERROR
};

enum class Result : u8 {
  NONE,
  ACQUIRED,
  RELEASED,
  RECOVERED,
  CONTENTION,
  DOUBLE_ACQUIRE,
  NOT_ACTIVE,
  WRONG_OWNER,
  INVALID_OWNER,
  ERROR_LATCHED,
  NOT_IN_ERROR
};

static constexpr u16 DIAGNOSTIC_MAX = 0xFFFFU;

inline const char* owner_name(Owner owner) {
  switch(owner) {
    case Owner::NONE: return "none";
    case Owner::DISPLAY_CLIENT: return "display";
    case Owner::FLASH_CLIENT: return "flash";
  }
  return "invalid";
}

inline const char* state_name(State state) {
  switch(state) {
    case State::IDLE: return "idle";
    case State::ACTIVE: return "active";
    case State::ERROR: return "error";
  }
  return "invalid";
}

inline const char* result_name(Result result) {
  switch(result) {
    case Result::NONE: return "none";
    case Result::ACQUIRED: return "acquired";
    case Result::RELEASED: return "released";
    case Result::RECOVERED: return "recovered";
    case Result::CONTENTION: return "contention";
    case Result::DOUBLE_ACQUIRE: return "double-acquire";
    case Result::NOT_ACTIVE: return "not-active";
    case Result::WRONG_OWNER: return "wrong-owner";
    case Result::INVALID_OWNER: return "invalid-owner";
    case Result::ERROR_LATCHED: return "error-latched";
    case Result::NOT_IN_ERROR: return "not-in-error";
  }
  return "invalid";
}

struct Snapshot {
  State state;
  Owner owner;
  Result last_result;
  Result last_fault;
  u16 acquisitions;
  u16 releases;
  u16 failures;
  u16 contentions;
  u16 double_acquires;
  u16 inactive_releases;
  u16 wrong_owner_releases;
  u16 invalid_owners;
  u16 rejected_while_error;
  u16 recoveries;
};

// Pure single-context state machine. It deliberately has no SPI, IRQ, timing or
// global-instance dependency; production clients remain unchanged until the
// polling integration phase. Every protocol violation latches ERROR so a
// caller cannot silently continue with ambiguous bus ownership.
class Arbiter {
  public:
    constexpr Arbiter(void)
      : state_(State::IDLE), owner_(Owner::NONE), last_result_(Result::NONE),
        last_fault_(Result::NONE), acquisitions_(0), releases_(0), failures_(0),
        contentions_(0), double_acquires_(0), inactive_releases_(0),
        wrong_owner_releases_(0), invalid_owners_(0),
        rejected_while_error_(0), recoveries_(0) {}

    Result acquire(Owner requested_owner) {
      if(state_ == State::ERROR) return reject_while_error();
      if(!valid_owner(requested_owner)) {
        increment(invalid_owners_);
        return fail(Result::INVALID_OWNER);
      }
      if(state_ == State::ACTIVE) {
        if(owner_ == requested_owner) {
          increment(double_acquires_);
          return fail(Result::DOUBLE_ACQUIRE);
        }
        increment(contentions_);
        return fail(Result::CONTENTION);
      }

      owner_ = requested_owner;
      state_ = State::ACTIVE;
      increment(acquisitions_);
      last_result_ = Result::ACQUIRED;
      return last_result_;
    }

    Result release(Owner releasing_owner) {
      if(state_ == State::ERROR) return reject_while_error();
      if(!valid_owner(releasing_owner)) {
        increment(invalid_owners_);
        return fail(Result::INVALID_OWNER);
      }
      if(state_ != State::ACTIVE) {
        increment(inactive_releases_);
        return fail(Result::NOT_ACTIVE);
      }
      if(owner_ != releasing_owner) {
        increment(wrong_owner_releases_);
        return fail(Result::WRONG_OWNER);
      }

      owner_ = Owner::NONE;
      state_ = State::IDLE;
      increment(releases_);
      last_result_ = Result::RELEASED;
      return last_result_;
    }

    // Recovery is explicit and only clears a latched protocol error. Calling
    // it during a valid lease cannot be used as an implicit foreign release.
    Result recover(void) {
      if(state_ != State::ERROR) {
        last_result_ = Result::NOT_IN_ERROR;
        return last_result_;
      }
      state_ = State::IDLE;
      owner_ = Owner::NONE;
      increment(recoveries_);
      last_result_ = Result::RECOVERED;
      return last_result_;
    }

    Snapshot snapshot(void) const {
      const Snapshot result = {
        state_, owner_, last_result_, last_fault_, acquisitions_, releases_,
        failures_, contentions_, double_acquires_, inactive_releases_,
        wrong_owner_releases_, invalid_owners_, rejected_while_error_,
        recoveries_
      };
      return result;
    }

  private:
    static bool valid_owner(Owner owner) {
      return owner == Owner::DISPLAY_CLIENT || owner == Owner::FLASH_CLIENT;
    }

    static void increment(u16& value) {
      if(value != DIAGNOSTIC_MAX) value++;
    }

    Result fail(Result fault) {
      state_ = State::ERROR;
      last_fault_ = fault;
      last_result_ = fault;
      increment(failures_);
      return last_result_;
    }

    Result reject_while_error(void) {
      increment(rejected_while_error_);
      last_result_ = Result::ERROR_LATCHED;
      return last_result_;
    }

    State state_;
    Owner owner_;
    Result last_result_;
    Result last_fault_;
    u16 acquisitions_;
    u16 releases_;
    u16 failures_;
    u16 contentions_;
    u16 double_acquires_;
    u16 inactive_releases_;
    u16 wrong_owner_releases_;
    u16 invalid_owners_;
    u16 rejected_while_error_;
    u16 recoveries_;
};

} // namespace spi1_arbiter

#endif
