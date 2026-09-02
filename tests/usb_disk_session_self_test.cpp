#include <assert.h>
#include <stdio.h>

#include <cstddef>
#include <fstream>
#include <sstream>
#include <string>

#include "usb_disk_session.hpp"

namespace {

using usb_disk_session::Action;
using usb_disk_session::Event;
using usb_disk_session::State;
using usb_disk_session::Transition;

struct NameState { const char* name; State value; };
struct NameEvent { const char* name; Event value; };
struct NameAction { const char* name; Action value; };

static constexpr NameState STATES[] = {
  {"CLOSED", State::CLOSED}, {"CLEAN", State::CLEAN},
  {"DIRTY", State::DIRTY}, {"VALIDATING", State::VALIDATING},
  {"COMMITTING", State::COMMITTING}, {"REJECTED", State::REJECTED},
  {"IO_FAILED", State::IO_FAILED}, {"CLOSING", State::CLOSING}
};

static constexpr NameEvent EVENTS[] = {
  {"OPEN", Event::OPEN}, {"WRITE_ACCEPTED", Event::WRITE_ACCEPTED},
  {"SYNC_REQUEST", Event::SYNC_REQUEST}, {"SERVICE", Event::SERVICE},
  {"COMMIT_OK", Event::COMMIT_OK},
  {"COMMIT_REJECTED", Event::COMMIT_REJECTED},
  {"COMMIT_IO_FAILED", Event::COMMIT_IO_FAILED},
  {"CLOSE_REQUEST", Event::CLOSE_REQUEST},
  {"FINALIZE_OK", Event::FINALIZE_OK},
  {"FINALIZE_REJECTED", Event::FINALIZE_REJECTED},
  {"FINALIZE_IO_FAILED", Event::FINALIZE_IO_FAILED},
  {"DISCONNECT", Event::DISCONNECT}, {"RESET", Event::RESET}
};

static constexpr NameAction ACTIONS[] = {
  {"NONE", Action::NONE}, {"SESSION_OPENED", Action::SESSION_OPENED},
  {"WRITE_TRACKED", Action::WRITE_TRACKED},
  {"SYNC_QUEUED", Action::SYNC_QUEUED},
  {"COMMIT_STARTED", Action::COMMIT_STARTED},
  {"SYNC_SUCCEEDED", Action::SYNC_SUCCEEDED},
  {"SYNC_REJECTED", Action::SYNC_REJECTED},
  {"SYNC_IO_FAILED", Action::SYNC_IO_FAILED},
  {"FINALIZE_STARTED", Action::FINALIZE_STARTED},
  {"CLOSE_SUCCEEDED", Action::CLOSE_SUCCEEDED},
  {"CLOSE_REJECTED", Action::CLOSE_REJECTED},
  {"CLOSE_IO_FAILED", Action::CLOSE_IO_FAILED},
  {"SESSION_ABORTED", Action::SESSION_ABORTED},
  {"REJECT_EVENT", Action::REJECT_EVENT}
};

template<typename Pair, usize N, typename Value>
static bool parse_name(const std::string& name, const Pair (&pairs)[N],
                       Value& value) {
  for(const Pair& pair : pairs) {
    if(name == pair.name) {
      value = pair.value;
      return true;
    }
  }
  return false;
}

static void replay(const char* path) {
  std::ifstream input(path);
  assert(input.good());
  std::string line;
  assert(std::getline(input, line));
  assert(line == "MK61-VFAT-SESSION 1");

  State state = State::CLOSED;
  std::size_t step = 0;
  std::size_t line_number = 1;
  while(std::getline(input, line)) {
    line_number++;
    const std::size_t first = line.find_first_not_of(" \t\r");
    if(first == std::string::npos || line[first] == '#') continue;
    std::istringstream fields(line);
    std::string event_name;
    std::string state_name;
    std::string action_name;
    std::string extra;
    if(!(fields >> event_name >> state_name >> action_name) ||
       (fields >> extra)) {
      fprintf(stderr, "%s:%zu: expected EVENT STATE ACTION\n",
              path, line_number);
      assert(false);
    }
    Event event = Event::COUNT;
    State expected_state = State::COUNT;
    Action expected_action = Action::REJECT_EVENT;
    assert(parse_name(event_name, EVENTS, event));
    assert(parse_name(state_name, STATES, expected_state));
    assert(parse_name(action_name, ACTIONS, expected_action));
    const Transition result = usb_disk_session::transition(state, event);
    if(!result.accepted || result.next != expected_state ||
       result.action != expected_action) {
      fprintf(stderr, "%s:%zu: replay mismatch at step %zu\n",
              path, line_number, step);
      assert(false);
    }
    state = result.next;
    step++;
  }
  assert(step != 0);
  assert(state == State::CLOSED);
}

static void exhaustive_contract(void) {
  std::size_t accepted = 0;
  for(u8 raw_state = 0; raw_state < (u8) State::COUNT; raw_state++) {
    const State state = (State) raw_state;
    for(u8 raw_event = 0; raw_event < (u8) Event::COUNT; raw_event++) {
      const Event event = (Event) raw_event;
      const Transition result = usb_disk_session::transition(state, event);
      assert((u8) result.next < (u8) State::COUNT);
      assert((u8) result.action <= (u8) Action::REJECT_EVENT);
      if(result.accepted) {
        accepted++;
        assert(result.action != Action::REJECT_EVENT);
      } else {
        assert(result.next == state);
        assert(result.action == Action::REJECT_EVENT);
      }
    }
  }
  assert(accepted == 38);

  assert(!usb_disk_session::transition(
      State::COMMITTING, Event::WRITE_ACCEPTED).accepted);
  assert(usb_disk_session::transition(
      State::REJECTED, Event::WRITE_ACCEPTED).next == State::DIRTY);
  assert(usb_disk_session::transition(
      State::IO_FAILED, Event::SYNC_REQUEST).next == State::VALIDATING);
  assert(usb_disk_session::transition(
      State::DIRTY, Event::RESET).action == Action::SESSION_ABORTED);
}

} // namespace

int main(int argc, char** argv) {
  exhaustive_contract();
  assert(argc > 1);
  for(int index = 1; index < argc; index++) replay(argv[index]);
  puts("usb_disk_session_self_test: ok");
  return 0;
}
