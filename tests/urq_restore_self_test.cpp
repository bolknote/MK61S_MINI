#include "../code/urq/engine.hpp"
#include "../code/ecma_number.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <map>
#include <string>
#include <vector>

namespace {
constexpr unsigned DURABLE = offsetof(urq::State, transient);
constexpr unsigned UNDO_CAPACITY = sizeof(urq::State::transient) + (urq::POOL_BYTES + 7) / 8;
struct Files {
  std::string folder;
  std::map<unsigned, std::vector<uint8_t>> contents;
  const std::vector<uint8_t>& file(unsigned id) {
    if(!contents.count(id)) {
      char name[32]; std::snprintf(name, sizeof(name), "p%04u.uqd", id - 1);
      std::ifstream stream(folder + "/" + (id ? name : "game.urq"), std::ios::binary);
      contents[id] = {std::istreambuf_iterator<char>(stream), {}};
    }
    return contents[id];
  }
  static bool read(void* raw, uint16_t id, uint32_t offset, uint8_t* out, uint32_t size) {
    const auto& bytes = static_cast<Files*>(raw)->file(id);
    if(offset > bytes.size() || size > bytes.size() - offset) return false;
    std::memcpy(out, bytes.data() + offset, size); return true;
  }
  static uint32_t size(void* raw, uint16_t id) { return static_cast<Files*>(raw)->file(id).size(); }
};
struct Saved {
  std::vector<uint8_t> bytes;
  unsigned reads = 0, reject = 0, pass = 0, change_pass = 0;
  uint32_t change_offset = 36;
  uint8_t change_value = 1;
  static bool write(void* raw, const uint8_t* data, uint32_t size) {
    auto& self = *static_cast<Saved*>(raw);
    self.bytes.insert(self.bytes.end(), data, data + size); return true;
  }
  static bool read(void* raw, uint32_t offset, uint8_t* out, uint32_t size) {
    auto& self = *static_cast<Saved*>(raw);
    if(++self.reads == self.reject || offset > self.bytes.size() || size > self.bytes.size() - offset) return false;
    if(offset == 32 && size == 128) ++self.pass; // validation, apply
    std::memcpy(out, self.bytes.data() + offset, size);
    if(self.pass == self.change_pass && self.change_offset >= offset && self.change_offset - offset < size)
      out[self.change_offset - offset] ^= self.change_value;
    return true;
  }
  urq::Source source() { reads = pass = 0; return {this, read, uint32_t(bytes.size())}; }
};
struct Game {
  Files files;
  urq::State state{};
  urq::Pack pack;
  urq::Engine engine;
  uint8_t cache[urq::PAGE_BYTES]{};
  explicit Game(const char* folder) : files{folder, {}} {
    assert(pack.open({&files, Files::read, Files::size, cache}));
    urq::Host host;
    host.parse = [](void*, const char* text, double& number) { return ecma_number::parse(text, number); };
    host.number = [](void*, double number, bool fixed, char* out, uint16_t size) {
      if(fixed) ecma_number::fractional(number, out, size); else ecma_number::format(number, out, size);
    };
    engine.attach(pack, state, host); assert(engine.start());
    assert(engine.run() != urq::Status::ERROR);
  }
  Saved save() {
    Saved saved; assert(engine.snapshot({&saved, Saved::write})); return saved;
  }
};
unsigned encoded_bytes(const uint8_t* bytes, unsigned length) {
  unsigned at = 0, size = 0;
  while(at < length) {
    if(bytes[at]) { ++at; ++size; continue; }
    unsigned run = 1;
    while(run < 255 && at + run < length && !bytes[at + run]) ++run;
    size += 2; at += run;
  }
  return size;
}
unsigned undo_bytes(const urq::State& state) {
  return encoded_bytes(reinterpret_cast<const uint8_t*>(&state), DURABLE);
}
void check_unchanged(const urq::State& before, const Game& game) {
  assert(!std::memcmp(&before, &game.state, DURABLE));
}
void faults(const char* folder) {
  Game game(folder);
  assert(game.state.status == urq::Status::INPUT && game.state.depth == 2);
  auto target = game.save();
  assert(game.engine.set("live_marker", {42}));
  assert(game.engine.set("score", {99}));
  const urq::State before = game.state;
  assert(undo_bytes(before) <= UNDO_CAPACITY);
  assert(game.engine.restore(target.source()));
  const unsigned total_reads = target.reads;
  assert(total_reads > 6);
  // Every callback, including the first and last apply read.
  for(unsigned fail = 1; fail <= total_reads; ++fail) {
    game.state = before;
    target.reject = fail;
    assert(!game.engine.restore(target.source()));
    assert(target.reads == fail);
    check_unchanged(before, game);
    assert(game.engine.get("live_marker").number == 42);
    urq::Value value;
    assert(game.engine.evaluate("'still'+' alive'", value));
    assert(value.type == 1 && !std::strcmp(value.text, "still alive"));
  }
  target.reject = 0;
  // A callback can succeed while returning different bytes between scans.
  for(unsigned pass : {1U, 2U}) {
    game.state = before; target.change_pass = pass;
    assert(!game.engine.restore(target.source())); // valid typed RNG, wrong CRC
    check_unchanged(before, game);
    game.state = before; target.change_offset = 52; target.change_value = 255;
    assert(!game.engine.restore(target.source())); // invalid stack depth
    check_unchanged(before, game);
    target.change_offset = 36; target.change_value = 1;
  }
  target.change_pass = 0; game.state = before;
  assert(game.engine.restore(target.source()));
  assert(game.engine.get("score").number == 17);
  assert(game.engine.get("live_marker").number == 0);
  assert(game.engine.submit("answer"));
  assert(game.engine.run() == urq::Status::PAUSE);
  game.engine.tick(30);
  assert(game.engine.run() == urq::Status::CHOICE);
  assert(game.engine.get("score").number == 18);
  std::printf("restore: %u injected read failures; undo %u/%zu bytes\n", total_reads,
              undo_bytes(before), size_t(UNDO_CAPACITY));
}
void input_length(const char* folder) {
  for(unsigned length : {255U, 256U, 600U}) {
    Game source(folder), live(folder);
    const std::string input(length, 'x');
    assert(source.engine.set("previous_input", {0, input.c_str(), 1}));
    source.state.last_input = uint16_t(source.engine.get("previous_input").text - source.state.pool);
    auto saved = source.save();
    assert(live.engine.set("live_marker", {42}));
    const urq::State before = live.state;
    assert(live.engine.restore(saved.source()) == (length == 255));
    if(length != 255) check_unchanged(before, live);
    else assert(std::strlen(live.engine.text(live.state.last_input)) == 255);
  }
}
void undo_overflow(const char* folder) {
  Game game(folder);
  auto saved = game.save();
  // Legal live strings alone can exceed the scratch undo budget.
  const std::string dense(2200, 'x');
  assert(game.engine.set("large", {0, dense.c_str(), 1}));
  assert(undo_bytes(game.state) > UNDO_CAPACITY);
  for(unsigned i = 0; i < 5; ++i) assert(game.engine.get("urqw_game_ifid").type == 1);
  const urq::State before = game.state;
  assert(!game.engine.restore(saved.source()));
  check_unchanged(before, game);
  // Failed preflight invalidates expression scratch and the package cache.
  for(unsigned i = 0; i < 3; ++i) assert(game.engine.get("urqw_game_ifid").type == 1);
  urq::Value value;
  assert(game.engine.evaluate("'kept'+' working'", value));
  assert(value.type == 1 && !std::strcmp(value.text, "kept working"));
  assert(game.engine.submit("ok"));
  assert(game.engine.run() == urq::Status::PAUSE);
  std::printf("restore: dense undo %u/%zu bytes rejected without mutation\n",
              undo_bytes(before), size_t(UNDO_CAPACITY));
}
void shipped_snapshot(const char* folder, const char* path) {
  Game game(folder); Saved saved;
  std::ifstream file(path, std::ios::binary);
  saved.bytes = {std::istreambuf_iterator<char>(file), {}};
  assert(game.engine.restore(saved.source()));
  auto again = game.save();
  const unsigned size = undo_bytes(game.state);
  assert(game.engine.restore(again.source()));
  std::printf("restore: %s undo %u/%zu bytes\n", path, size, size_t(UNDO_CAPACITY));
}
}
int main(int argc, char** argv) {
  assert(argc == 2 || argc == 3);
  if(argc == 3) { shipped_snapshot(argv[1], argv[2]); return 0; }
  faults(argv[1]); input_length(argv[1]); undo_overflow(argv[1]);
}
