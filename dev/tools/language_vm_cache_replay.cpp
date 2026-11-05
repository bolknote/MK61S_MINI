// Host-only cache policy oracle. No VM execution, hardware or filesystem writes.
#include "language_vm_image_cache.hpp"
#include <iostream>
#include <vector>
#include <cstring>
using namespace language_vm;
struct CacheRequest { uint16_t id, size; Language language; };
template<CachePolicy Policy>
int replay(const std::vector<CacheRequest>& requests, unsigned repeats) {
  using Cache = ImageCache<24576, 16, Policy>;
  Cache cache;
  std::cout << "{\"budget\":24576,\"payload\":" << Cache::PAYLOAD_CAPACITY
            << ",\"metadata\":" << Cache::metadata_bytes() << ",\"slots\":16,\"passes\":[";
  for(unsigned pass = 0; pass < repeats; ++pass) {
    const auto before = cache.statistics();
    unsigned failures = 0;
    for(const auto& request : requests) {
      const typename Cache::Key key = {1, request.id, request.language, 0};
      auto handle = cache.find(key);
      if(!handle) {
        handle = cache.reserve(key, request.size);
        if(!handle) { ++failures; continue; }
        std::memset(cache.building(handle), 0, request.size);
        ValidatedImage certificate = {};
        certificate.magic = VALIDATED_MAGIC;
        certificate.size = request.size;
        certificate.language = request.language;
        certificate.flags = RESOURCE_FLAG | OWNED_RESOURCE_FLAG;
        if(!cache.publish(handle, certificate)) return 3;
      }
      if(!cache.release(handle)) return 3;
    }
    const auto& after = cache.statistics();
    if(pass) std::cout << ',';
    std::cout << "{\"hits\":" << after.hits - before.hits
              << ",\"misses\":" << after.misses - before.misses
              << ",\"evictions\":" << after.evictions - before.evictions
              << ",\"fallback\":" << failures << ",\"used\":" << cache.used() << '}';
  }
  std::cout << "]}\n";
  return 0;
}
int main() {
  unsigned repeats, count, policy;
  if(!(std::cin >> repeats >> count >> policy) || !repeats || repeats > 10 ||
     count > 1000000 || policy > 1) return 2;
  std::vector<CacheRequest> requests;
  for(unsigned i = 0; i < count; ++i) {
    unsigned id, size, language;
    if(!(std::cin >> id >> size >> language) || id >= 0xFFFF || size > 0xFFFF ||
       size < HEADER_SIZE || language < 1 || language > 2) return 2;
    requests.push_back({(uint16_t)id, (uint16_t)size, (Language)language});
  }
  return policy ? replay<CachePolicy::REUSE_DENSITY>(requests, repeats) :
                  replay<CachePolicy::LRU>(requests, repeats);
}
