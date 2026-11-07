#ifndef MK61_BLOCK_READ_HPP
#define MK61_BLOCK_READ_HPP
#include <cstdint>
namespace block_io {
// Offsets belong to the source allocation. A successful begin consumes the
// descriptors immediately, but owns destination bytes until finish returns.
// A refused begin starts no transfer and never retains a destination.
struct ReadSpan {
  std::uint32_t offset;
  void *destination;
  unsigned bytes;
};
}
#endif
