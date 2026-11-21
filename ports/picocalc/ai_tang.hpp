#ifndef MK61_PICOCALC_AI_TANG_HPP
#define MK61_PICOCALC_AI_TANG_HPP

#include "mk61_ai_agent.hpp"

namespace picocalc::ai_tang {
class Backend {
public:
  explicit Backend(mk61ai::Model &);
  ~Backend();
  mk61ai::ModelStatus open(std::uint32_t package_header_crc, std::uint32_t package_bytes,
                           bool (*service)(void *), void *);
  void close();
  bool online() const;
  mk61ai::ModelStatus prefix(const std::uint16_t *tokens, unsigned count, bool save,
                            bool (*service)(void *), void *);
  mk61ai::Inference inference();

private:
  struct State;
  mk61ai::Model &local_;
  std::unique_ptr<State> state_;
};
} // namespace picocalc::ai_tang
#endif
