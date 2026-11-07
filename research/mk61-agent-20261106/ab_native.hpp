#pragma once
#include <cstdint>
#include <cstddef>

// Pure wire grammar. It has no task text, VM, reference program, or answer table.
namespace mk61action {
enum class Action : std::uint8_t { Write, Patch, Run, Trace, Diag, Done, Unsure, None };
struct Decoder {
  Action action = Action::None;
  std::uint8_t body[512] = {};
  std::uint16_t size = 0;
  unsigned digits = 0, half = 0;
  bool ended = false;
  bool no_body() const {
    return action==Action::Trace || action==Action::Done || action==Action::Unsure;
  }
  unsigned maximum() const { return action==Action::Run ? 1 : action==Action::Diag ? 5 : 512; }
  unsigned minimum() const { return action==Action::Diag ? 5 : action==Action::Patch ? 2 : 1; }
  bool complete() const { return action!=Action::None && (no_body() || ended); }
  bool accept(std::uint16_t token, const char *piece) {
    if (action==Action::None) {
      if (token<8192 || token>8198) return false;
      action=Action(token-8192); return true;
    }
    if (no_body() || ended) return token==30;
    if (token==30) {
      if (digits!=2 || size<minimum() || size>maximum()) return false;
      ended=true; return true;
    }
    if (!piece || !*piece) return false;
    for (const char *p=piece;*p;++p) {
      if (*p==' ') {
        if (digits!=2 || size>=maximum()) return false;
        digits=0; half=0; continue;
      }
      unsigned value;
      if (*p>='0'&&*p<='9') value=unsigned(*p-'0');
      else if (*p>='A'&&*p<='F') value=unsigned(*p-'A'+10);
      else return false;
      if (digits>=2 || size>=maximum()) return false;
      half=half*16+value; ++digits;
      if (digits==2) body[size++]=std::uint8_t(half);
    }
    return true;
  }
  bool allows(std::uint16_t token,const char *piece) const {
    Decoder copy=*this; return copy.accept(token,piece);
  }
};
} // namespace mk61action
