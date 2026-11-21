#include "ai_tang.hpp"

#if defined(PICO_ON_DEVICE)
#include "ai_m3.hpp"
#include "ai_tang.pio.h"
#include "crc32.hpp"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/structs/iobank0.h"
#include "hardware/structs/pads_bank0.h"
#include "pico/time.h"
#include "io_worker.hpp"
#include "storage.hpp"
#include <algorithm>
#include <new>
#endif

namespace picocalc::ai_tang {
using namespace mk61ai;

#if defined(PICO_ON_DEVICE)
namespace {
constexpr unsigned GPIO = 28, CONTEXT = 1024, MAX_LANES = 6, MAX_ALLOWED = 24;
constexpr std::uint32_t ALLOWED_ADDRESS = 0x7fffc0, MAX_IMAGE_BYTES = 0x220000;
constexpr std::uint32_t SECOND_ALLOWED = 0x7ff000;
constexpr std::uint32_t DRAFT_FEATURE = 1u << 8;
constexpr std::uint32_t PACKAGE_MAGIC = 0x314b544d; // "MTK1" in little endian
constexpr std::uint32_t PREFIX_ADDRESS = 0x7fe000, PREFIX_MAGIC = 0x31504b54;
constexpr unsigned KV_BYTES_PER_POSITION = 512, MAX_LAYERS = 10;
constexpr unsigned PREFIX_HEADER_BYTES = 16 + 4 * MAX_LAYERS;
static_assert(MAX_IMAGE_BYTES + MAX_LAYERS * CONTEXT * KV_BYTES_PER_POSITION < PREFIX_ADDRESS);
static_assert(PREFIX_ADDRESS + PREFIX_HEADER_BYTES + CONTEXT * 2 < SECOND_ALLOWED);
constexpr char image_path[] = "/AI/MODEL.TNG";
enum Command : std::uint8_t {
  PUT = 1, GET = 2, CRC = 3, FORWARD = 6, PREFILL = 8, SEEK = 9, FEATURES = 10, VERIFY = 11
};

std::uint32_t word(const std::uint8_t *p) {
  return std::uint32_t(p[0]) | std::uint32_t(p[1]) << 8 |
         std::uint32_t(p[2]) << 16 | std::uint32_t(p[3]) << 24;
}
void write_word(std::uint8_t *p, std::uint32_t value) {
  for (unsigned i = 0; i < 4; ++i) p[i] = std::uint8_t(value >> (8 * i));
}
struct Pump {
  bool (*service)(void *);
  void *context;
  bool cancelled = false;
  bool poll() {
    if (!cancelled && service) cancelled = !service(context);
    return !cancelled;
  }
};

class Wire {
public:
  ~Wire() { close(); }
  bool open() {
    tx_ = pio_claim_unused_sm(pio0, false);
    rx_ = pio_claim_unused_sm(pio0, false);
    dma_ = dma_claim_unused_channel(false);
    if (tx_ >= 0 && rx_ >= 0 && dma_ >= 0) {
      tx_offset_ = pio_add_program(pio0, &tang_tx_program);
      if (tx_offset_ >= 0) rx_offset_ = pio_add_program(pio0, &tang_rx_program);
    }
    if (rx_offset_ < 0) { close(); return false; }
    ctrl_ = iobank0_hw->io[GPIO].ctrl;
    pad_ = pads_bank0_hw->io[GPIO];
    pio_gpio_init(pio0, GPIO);
    gpio_pull_up(GPIO);
    owns_pin_ = true;
    return true;
  }
  bool ready() const { return owns_pin_; }
  void close() {
    if (owns_pin_) {
      stop();
      iobank0_hw->io[GPIO].ctrl = ctrl_;
      pads_bank0_hw->io[GPIO] = pad_;
      owns_pin_ = false;
    }
    if (rx_offset_ >= 0) pio_remove_program(pio0, &tang_rx_program, unsigned(rx_offset_));
    if (tx_offset_ >= 0) pio_remove_program(pio0, &tang_tx_program, unsigned(tx_offset_));
    if (rx_ >= 0) pio_sm_unclaim(pio0, unsigned(rx_));
    if (tx_ >= 0) pio_sm_unclaim(pio0, unsigned(tx_));
    if (dma_ >= 0) dma_channel_unclaim(unsigned(dma_));
    tx_ = rx_ = dma_ = tx_offset_ = rx_offset_ = -1;
  }

  template<unsigned Capacity>
  bool call(Command command, unsigned address, const std::uint8_t *data, unsigned bytes,
            unsigned words, std::uint32_t (&result)[Capacity], unsigned timeout, Pump &pump) {
    std::uint8_t header[10]{0xa5, 0x5a, command, ++sequence_,
                            std::uint8_t(bytes), std::uint8_t(bytes >> 8)};
    write_word(header + 6, address);
    auto crc = mk61_crc32::extend(mk61_crc32::INITIAL_STATE, header + 2, 8);
    std::uint8_t checksum[4];
    write_word(checksum, mk61_crc32::finish(mk61_crc32::extend(crc, data, bytes)));
    std::uint8_t reply[47]{};
    configure();
    auto dma_config = dma_channel_get_default_config(unsigned(dma_));
    channel_config_set_transfer_data_size(&dma_config, DMA_SIZE_8);
    channel_config_set_read_increment(&dma_config, false);
    channel_config_set_write_increment(&dma_config, true);
    channel_config_set_dreq(&dma_config, pio_get_dreq(pio0, unsigned(rx_), false));
    auto fifo = reinterpret_cast<const volatile std::uint8_t *>(&pio0->rxf[rx_]);
    dma_channel_configure(unsigned(dma_), &dma_config, reply, fifo + 3, sizeof(reply), true);
    const bool sent = transmit(header, data, bytes, checksum);
    unsigned received = 0, needed = 10;
    const auto started = time_us_32();
    auto polled = started;
    while (sent) {
      received = sizeof(reply) - dma_channel_hw_addr(unsigned(dma_))->transfer_count;
      if (received >= 10) {
        __compiler_memory_barrier();
        needed = unsigned(reply[4]) + 14;
        if (reply[0] != 0x5a || reply[1] != 0xa5 || reply[2] != (command | 0x80) ||
            reply[3] != sequence_ || reply[5] || word(reply + 6) ||
            needed < 27 || needed > sizeof(reply) || received >= needed) break;
      }
      const auto now = time_us_32();
      if (now - started >= timeout) break;
      if (now - polled >= 4000) { pump.poll(); polled = now; }
      tight_loop_contents();
    }
    stop();
    if (!sent || received < needed || needed != 15 + 4 * words || reply[0] != 0x5a ||
        reply[1] != 0xa5 || reply[2] != (command | 0x80) || reply[3] != sequence_ ||
        reply[5] || word(reply + 6) || reply[10] ||
        word(reply + needed - 4) != mk61_crc32::calculate(reply + 2, needed - 6)) return false;
    for (unsigned i = 0; i < std::min(Capacity, words); ++i) result[i] = word(reply + 11 + i * 4);
    return true;
  }

private:
  int tx_ = -1, rx_ = -1, dma_ = -1, tx_offset_ = -1, rx_offset_ = -1;
  std::uint32_t ctrl_ = 0, pad_ = 0;
  std::uint8_t sequence_ = 0;
  bool owns_pin_ = false;

  void configure() {
    // Both state machines use 8 cycles per bit at 1 Mbaud.
    const unsigned divider = (clock_get_hz(clk_sys) + 15625) / 31250;
    auto tx = tang_tx_program_get_default_config(unsigned(tx_offset_));
    sm_config_set_out_pins(&tx, GPIO, 1);
    sm_config_set_set_pins(&tx, GPIO, 1);
    sm_config_set_sideset_pins(&tx, GPIO);
    sm_config_set_out_shift(&tx, true, false, 32);
    sm_config_set_fifo_join(&tx, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv_int_frac(&tx, divider >> 8, divider & 255);
    pio_sm_init(pio0, unsigned(tx_), unsigned(tx_offset_), &tx);
    auto rx = tang_rx_program_get_default_config(unsigned(rx_offset_));
    sm_config_set_in_pins(&rx, GPIO);
    sm_config_set_jmp_pin(&rx, GPIO);
    sm_config_set_in_shift(&rx, true, false, 32);
    sm_config_set_fifo_join(&rx, PIO_FIFO_JOIN_RX);
    sm_config_set_clkdiv_int_frac(&rx, divider >> 8, divider & 255);
    pio_sm_init(pio0, unsigned(rx_), unsigned(rx_offset_), &rx);
  }
  void stop() {
    pio_sm_set_enabled(pio0, unsigned(tx_), false);
    pio_sm_set_enabled(pio0, unsigned(rx_), false);
    pio_sm_exec(pio0, unsigned(tx_), pio_encode_set(pio_pindirs, 0));
    dma_channel_abort(unsigned(dma_));
  }
  bool transmit(const std::uint8_t (&header)[10], const std::uint8_t *data, unsigned bytes,
                const std::uint8_t (&crc)[4]) {
    if (!gpio_get(GPIO)) return false;
    pio_sm_exec(pio0, unsigned(tx_), pio_encode_set(pio_pins, 1));
    pio_sm_put(pio0, unsigned(tx_), header[0]);
    pio_sm_exec(pio0, unsigned(tx_), pio_encode_set(pio_pindirs, 1));
    const auto started = time_us_32();
    pio_sm_set_enabled(pio0, unsigned(tx_), true);
    auto put = [&](const std::uint8_t *p, unsigned n) {
      for (unsigned i = 0; i < n; ++i) {
        while (pio_sm_is_tx_fifo_full(pio0, unsigned(tx_)))
          if (time_us_32() - started > 20000) return false;
        pio_sm_put(pio0, unsigned(tx_), p[i]);
      }
      return true;
    };
    if (!put(header + 1, 9) || !put(data, bytes) || !put(crc, 4)) return false;
    const auto stalled = 1u << (PIO_FDEBUG_TXSTALL_LSB + unsigned(tx_));
    pio0->fdebug = stalled;
    while (!(pio0->fdebug & stalled))
      if (time_us_32() - started > 20000) return false;
    busy_wait_us_32(2);
    pio_sm_set_enabled(pio0, unsigned(tx_), false);
    pio_sm_exec(pio0, unsigned(tx_), pio_encode_set(pio_pindirs, 0));
    pio_sm_set_enabled(pio0, unsigned(rx_), true);
    return true;
  }
};
} // namespace

struct Backend::State {
  explicit State(Model &model) : local(model) {}
  ~State() { if (draft_open) ai_m3::close_draft(); }
  Model &local;
  Wire wire;
  std::uint16_t history[CONTEXT];
  std::uint32_t image_crc = 0;
  unsigned position = 0, remote_position = 0, lanes = 0;
  bool can_verify = false, draft_open = false, draft_unavailable = false;
  std::uint32_t single_us = 0, pair_us = 0;
  static constexpr unsigned spec_tokens = sizeof(SpecProtocol::OUTPUT_TOKENS) / sizeof(std::uint16_t);
  char pieces[spec_tokens][16]{};
  bool pieces_ready = false;

  bool seek(unsigned n) {
    if (n > position) return false;
    position = n;
    if (local.position() > n) local.rewind(n);
    return true;
  }
  ModelStatus prepare(std::uint32_t package_crc, std::uint32_t package_bytes, Pump &pump) {
    files::Entry info{};
    std::uint8_t block[1024];
    unsigned got = 0;
    if (!files::stat(image_path, info) || info.directory || info.size < 48) return ModelStatus::IO;
    const unsigned size = info.size - 16;
    struct ReleaseReader { ~ReleaseReader() { files::release_read_cursor(); } } reader;
    if ((size & 3) || size > MAX_IMAGE_BYTES ||
        !files::read_range(image_path, size, block, 16, got) || got != 16 ||
        word(block) != PACKAGE_MAGIC || word(block + 4) != package_crc ||
        word(block + 8) != package_bytes) return ModelStatus::FORMAT;
    image_crc = word(block + 12);
    std::uint32_t result[3];
    if (!pump.poll()) return ModelStatus::CANCELLED;
    if (!wire.open() || !wire.call(FEATURES, 0, nullptr, 0, 3, result, 25000, pump) ||
        result[0] != PACKAGE_MAGIC || result[1] < 1 || result[1] > MAX_LANES ||
        result[2] != MAX_ALLOWED) return ModelStatus::IO;
    lanes = result[1];
    if (wire.call(FEATURES, 1, nullptr, 0, 3, result, 25000, pump))
      can_verify = result[0] == PACKAGE_MAGIC && result[1] == lanes &&
                   result[2] == (DRAFT_FEATURE | MAX_ALLOWED) && lanes >= 2;
    auto verify = [&]() {
      std::uint8_t length[4]; write_word(length, size);
      return wire.call(CRC, 0, length, 4, 3, result, 4000000, pump) && result[0] == image_crc;
    };
    if (!verify()) {
      for (unsigned offset = 0; offset < size;) {
        if (!pump.poll()) return ModelStatus::CANCELLED;
        const unsigned bytes = std::min(size - offset, unsigned(sizeof(block)));
        if (!files::read_range(image_path, offset, block, bytes, got) || got != bytes ||
            !wire.call(PUT, offset, block, bytes, 3, result, 25000, pump) || result[0] != bytes)
          return ModelStatus::IO;
        offset += bytes;
      }
      if (!verify()) return ModelStatus::IO;
    }
    if (!pump.poll()) return ModelStatus::CANCELLED;
    // Seeking to capacity reports the current boundary and preserves resident KV.
    if (!wire.call(SEEK, CONTEXT, nullptr, 0, 3, result, 25000, pump) || result[0] > CONTEXT)
      return ModelStatus::IO;
    remote_position = result[0];
    return pump.cancelled ? ModelStatus::CANCELLED : ModelStatus::OK;
  }

  struct Mask {
    std::uint16_t token[MAX_ALLOWED]{};
    unsigned count = 0;
    bool contains(std::uint16_t id) const {
      return std::binary_search(token, token + count, id);
    }
  };
  void fill_mask(const SpecProtocol &spec, Mask &mask) const {
    for (unsigned i = 0; i < spec_tokens; ++i) {
      const auto id = SpecProtocol::OUTPUT_TOKENS[i];
      if (mask.count < MAX_ALLOWED && spec.allows(id, pieces[i])) mask.token[mask.count++] = id;
    }
  }
  bool send_mask(unsigned address, const Mask &mask, Pump &pump) {
    const auto bytes = (mask.count + 1) / 2 * 4;
    std::uint8_t data[MAX_ALLOWED * 2]{};
    for (unsigned i = 0; i < mask.count; ++i) {
      data[2 * i] = std::uint8_t(mask.token[i]);
      data[2 * i + 1] = std::uint8_t(mask.token[i] >> 8);
    }
    std::uint32_t reply[3];
    return wire.call(PUT, address, data, bytes, 3, reply, 25000, pump) && reply[0] == bytes;
  }
  void release_draft() {
    if (draft_open) ai_m3::close_draft();
    draft_open = draft_unavailable = false;
  }
  ModelStatus verify(const SpecProtocol &spec, std::uint16_t token, unsigned generated,
                     VerifiedTokens &out, Pump &pump) {
    if (!can_verify || !wire.ready() || draft_unavailable || !single_us ||
        position > CONTEXT - 2 || !spec.action() || spec.ended())
      return ModelStatus::OK;
    if (!pump.poll()) return ModelStatus::CANCELLED;
    if (!pieces_ready) {
      for (unsigned i = 0; i < spec_tokens; ++i) {
        unsigned bytes;
        if (local.decode(SpecProtocol::OUTPUT_TOKENS[i], pieces[i], sizeof(pieces[i]), bytes) != ModelStatus::OK) {
          draft_unavailable = true;
          return ModelStatus::OK;
        }
      }
      pieces_ready = true;
    }
    if (!draft_open) {
      draft_open = ai_m3::open_draft();
      if (!draft_open) {
        draft_unavailable = true;
        return ModelStatus::OK;
      }
    }

    const auto draft_started = time_us_32();
    Mask first, second;
    struct Prepare { const State &backend; const SpecProtocol &spec; Mask &mask; } job{*this, spec, first};
    const auto prepare = [](void *raw) {
      auto &job = *static_cast<Prepare *>(raw);
      job.backend.fill_mask(job.spec, job.mask);
    };
    const bool queued = io_worker::submit_compute(&job, prepare);
    const unsigned from = position + 1 > ai_m3::draft_history_limit ?
                              position + 1 - ai_m3::draft_history_limit : 0;
    history[position] = token;
    std::uint16_t guess{};
    std::uint8_t confidence{};
    const bool predicted = ai_m3::predict(history + from, position + 1 - from, generated, guess, confidence);
    if (queued) io_worker::join_compute();
    else prepare(&job);
    if (!pump.poll()) return ModelStatus::CANCELLED;
    if (!predicted) {
      release_draft();
      draft_unavailable = true;
      return ModelStatus::OK;
    }
    if (!confidence || guess == SpecProtocol::END || !first.contains(guess))
      return ModelStatus::OK;
    const auto *which = std::lower_bound(SpecProtocol::OUTPUT_TOKENS,
                                       SpecProtocol::OUTPUT_TOKENS + spec_tokens, guess);
    SpecProtocol hypothetical = spec;
    if (!hypothetical.accept(guess, pieces[which - SpecProtocol::OUTPUT_TOKENS]))
      return ModelStatus::OK;
    fill_mask(hypothetical, second);
    if (!second.count) return ModelStatus::OK;

    std::uint32_t reply[5];
    const auto failed = [&] {
      wire.close();
      release_draft();
      return pump.cancelled ? ModelStatus::CANCELLED : ModelStatus::OK;
    };
    if (remote_position != position) {
      if (!wire.call(SEEK, position, nullptr, 0, 3, reply, 25000, pump) || reply[0] != position)
        return failed();
      remote_position = position;
    }
    if (!send_mask(ALLOWED_ADDRESS, first, pump) || !send_mask(SECOND_ALLOWED, second, pump))
      return failed();
    if (pump.cancelled) return ModelStatus::CANCELLED;
    std::uint8_t data[12];
    write_word(data, token | (std::uint32_t(guess) << 16));
    write_word(data + 4, confidence);
    const auto single = std::clamp<std::uint32_t>(single_us / 8, 1, 65535);
    const auto prepare_us = time_us_32() - draft_started;
    const auto estimate_us = pair_us ? pair_us : single_us * 3 / 2;
    const auto pair = std::clamp<std::uint32_t>((estimate_us + prepare_us) / 8, 1, 65535);
    write_word(data + 8, single | (pair << 16));
    const auto before = time_us_32();
    if (!wire.call(VERIFY, first.count | second.count << 5, data, sizeof(data), 5, reply, 2000000, pump))
      return failed();
    const auto elapsed = time_us_32() - before;
    const auto advanced = (reply[0] >> 16) - position;
    const auto scheduled = reply[4] >> 16;
    const auto predicted_first = std::uint16_t(reply[4]);
    const auto predicted_last = std::uint16_t(reply[0]);
    if (scheduled > 1 || !first.contains(predicted_first) ||
        (advanced == 1 ? predicted_last != predicted_first || reply[1] != reply[3] ||
                             (scheduled && predicted_first == guess)
                       : advanced != 2 || !scheduled || predicted_first != guess || !second.contains(predicted_last)))
      return failed();
    remote_position = position + advanced;
    if (pump.cancelled) return ModelStatus::CANCELLED;
    if (advanced == 2) pair_us = pair_us ? (pair_us * 3 + elapsed) / 4 : elapsed;
    if (!scheduled) single_us = (single_us * 3 + elapsed) / 4;
    const std::uint16_t tokens[2]{token, guess};
    publish(tokens, advanced);
    out.token[0] = predicted_first;
    out.token[1] = predicted_last;
    out.count = advanced;
    return ModelStatus::OK;
  }

  ModelStatus prefix(const std::uint16_t *tokens, unsigned count, bool save, Pump &pump) {
    const unsigned layers = local.config().layers;
    if (!wire.ready() || !count || count >= CONTEXT || remote_position < count ||
        !layers || layers > MAX_LAYERS)
      return ModelStatus::FORMAT;
    if (save && (position != count || !std::equal(tokens, tokens + count, history)))
      return ModelStatus::FORMAT;
    auto failure = [&] { return pump.cancelled ? ModelStatus::CANCELLED : ModelStatus::IO; };
    std::uint32_t result[3];
    auto get = [&](unsigned address) {
      return pump.poll() && wire.call(GET, address, nullptr, 0, 3, result, 25000, pump);
    };
    auto put = [&](unsigned address, const std::uint8_t *data, unsigned bytes) {
      return pump.poll() && wire.call(PUT, address, data, bytes, 3, result, 25000, pump) && result[0] == bytes;
    };
    auto token_word = [&](unsigned index) {
      return std::uint32_t(tokens[index]) |
             (index + 1 < count ? std::uint32_t(tokens[index + 1]) << 16 : 0);
    };
    std::uint8_t header[PREFIX_HEADER_BYTES]{};
    write_word(header + 4, image_crc);
    write_word(header + 8, count);
    write_word(header + 12, layers);
    if (!save) {
      for (unsigned offset = 0; offset < 16; offset += 4) {
        if (!get(PREFIX_ADDRESS + offset)) return failure();
        if (result[0] != (offset == 0 ? PREFIX_MAGIC : word(header + offset))) return ModelStatus::FORMAT;
      }
      for (unsigned index = 0; index < count; index += 2) {
        if (!get(PREFIX_ADDRESS + PREFIX_HEADER_BYTES + index * 2)) return failure();
        if (result[0] != token_word(index)) return ModelStatus::FORMAT;
      }
    }
    // Validate the live KV spans in addition to the token list. Another client
    // can reuse the same model and cursor with different input.
    std::uint8_t length[4];
    write_word(length, count * KV_BYTES_PER_POSITION);
    for (unsigned layer = 0; layer < layers; ++layer) {
      const unsigned address = MAX_IMAGE_BYTES + layer * CONTEXT * KV_BYTES_PER_POSITION;
      if (!pump.poll() || !wire.call(CRC, address, length, 4, 3, result, 4000000, pump)) return failure();
      const auto checksum = result[0];
      if (save) {
        write_word(header + 16 + layer * 4, checksum);
      } else {
        if (!get(PREFIX_ADDRESS + 16 + layer * 4)) return failure();
        if (result[0] != checksum) return ModelStatus::FORMAT;
      }
    }
    if (save) {
      if (!put(PREFIX_ADDRESS, header, sizeof(header))) return failure();
      std::uint8_t block[256];
      const unsigned padded = (count + 1) & ~1U;
      for (unsigned index = 0; index < padded;) {
        const unsigned words = std::min((padded - index) / 2, unsigned(sizeof(block) / 4));
        for (unsigned j = 0; j < words; ++j) write_word(block + j * 4, token_word(index + j * 2));
        if (!put(PREFIX_ADDRESS + PREFIX_HEADER_BYTES + index * 2, block, words * 4)) return failure();
        index += words * 2;
      }
      // Publish only after both the metadata and all token IDs are present.
      write_word(header, PREFIX_MAGIC);
      if (!put(PREFIX_ADDRESS, header, 4)) return failure();
    } else {
      if (!pump.poll() || !wire.call(SEEK, count, nullptr, 0, 3, result, 25000, pump)) return failure();
      remote_position = result[0];
      if (remote_position != count) return ModelStatus::FORMAT;
      if (!pump.cancelled) {
        std::copy_n(tokens, count, history);
        position = count;
      }
    }
    return pump.cancelled ? ModelStatus::CANCELLED : ModelStatus::OK;
  }

  ModelStatus step(const std::uint16_t *tokens, unsigned count, bool output, std::uint16_t &best,
                   bool (*service)(void *), void *raw, Arithmetic mode,
                   bool (*allowed)(void *, std::uint16_t), void *policy) {
    if (count > CONTEXT - position) return ModelStatus::CONTEXT;
    Pump pump{service, raw};
    if (!pump.poll()) return ModelStatus::CANCELLED;
    if (wire.ready()) {
      const bool completed = forward(tokens, count, output, best, allowed, policy, pump);
      if (!completed) wire.close();
      if (pump.cancelled) return ModelStatus::CANCELLED;
      if (completed) {
        publish(tokens, count);
        return ModelStatus::OK;
      }
    }
    // Replay only committed input tokens. Position remains at the Agent's
    // boundary while the local backend rebuilds its cache, even across pauses.
    while (local.position() < position) {
      std::uint16_t unused;
      const auto status = local.forward(history[local.position()], false, unused, service, raw, mode);
      if (status != ModelStatus::OK) return status;
    }
    for (unsigned i = 0; i < count; ++i) {
      const auto status = local.forward(tokens[i], output, best, service, raw, mode, nullptr, allowed, policy);
      if (status != ModelStatus::OK) {
        local.rewind(position);
        return status;
      }
    }
    publish(tokens, count);
    return ModelStatus::OK;
  }

  void publish(const std::uint16_t *tokens, unsigned count) {
    std::copy_n(tokens, count, history + position);
    position += count;
  }
  bool forward(const std::uint16_t *tokens, unsigned count, bool output, std::uint16_t &best,
               bool (*allowed)(void *, std::uint16_t), void *policy, Pump &pump) {
    std::uint32_t result[3];
    if (remote_position != position) {
      if (!wire.call(SEEK, position, nullptr, 0, 3, result, 25000, pump) || result[0] != position) return false;
      remote_position = position;
      if (pump.cancelled) return true;
    }
    if (count > 1) {
      std::uint8_t ids[MAX_LANES * 2];
      for (unsigned i = 0; i < count; ++i) {
        ids[2 * i] = std::uint8_t(tokens[i]);
        ids[2 * i + 1] = std::uint8_t(tokens[i] >> 8);
      }
      if (!wire.call(PREFILL, 0, ids, count * 2, count + 2, result, 10000000, pump)) return false;
    } else {
      Mask mask;
      if (output && allowed) {
        for (const auto id : SpecProtocol::OUTPUT_TOKENS) if (allowed(policy, id)) {
          if (mask.count == MAX_ALLOWED) return false;
          mask.token[mask.count++] = id;
        }
        if (!mask.count || !send_mask(ALLOWED_ADDRESS, mask, pump)) return false;
        if (pump.cancelled) return true;
      }
      const auto address = tokens[0] | (unsigned(output) << 16) | (mask.count << 17);
      const auto before = time_us_32();
      if (!wire.call(FORWARD, address, nullptr, 0, 3, result, 2000000, pump)) return false;
      if (output) {
        const auto elapsed = time_us_32() - before;
        single_us = single_us ? (single_us * 3 + elapsed) / 4 : elapsed;
      }
    }
    if (result[0] >> 16 != position + count) return false;
    best = std::uint16_t(result[0]);
    if (output && (best >= local.config().vocab || (allowed && !allowed(policy, best)))) return false;
    remote_position = position + count;
    return true;
  }
};
#else
struct Backend::State {};
#endif

Backend::Backend(Model &local) : local_(local) {}
Backend::~Backend() = default;
void Backend::close() { state_.reset(); }
void Backend::release_draft() {
#if defined(PICO_ON_DEVICE)
  if (state_) state_->release_draft();
#endif
}
ModelStatus Backend::prefix(const std::uint16_t *tokens, unsigned count, bool save,
                            bool (*service)(void *), void *context) {
#if defined(PICO_ON_DEVICE)
  if (!state_) return ModelStatus::FORMAT;
  Pump pump{service, context};
  return state_->prefix(tokens, count, save, pump);
#else
  return ModelStatus::FORMAT;
#endif
}
bool Backend::online() const {
#if defined(PICO_ON_DEVICE)
  return state_ && state_->wire.ready();
#else
  return false;
#endif
}
ModelStatus Backend::open(std::uint32_t package_header_crc, std::uint32_t package_bytes,
                          bool (*service)(void *), void *context) {
#if defined(PICO_ON_DEVICE)
  std::unique_ptr<State> candidate(new (std::nothrow) State(local_));
  if (!candidate) return ModelStatus::MEMORY;
  Pump pump{service, context};
  const auto status = candidate->prepare(package_header_crc, package_bytes, pump);
  if (status == ModelStatus::OK) state_ = std::move(candidate);
  return status;
#else
  return ModelStatus::IO;
#endif
}
Inference Backend::inference() {
#if defined(PICO_ON_DEVICE)
  local_.reset();
  auto *s = state_.get();
  Inference result{};
  result.context = s;
  result.configuration = [](void *p) -> const ModelConfig & { return static_cast<State *>(p)->local.config(); };
  result.cursor = [](void *p) { return static_cast<State *>(p)->position; };
  result.seek = [](void *p, unsigned n) { return static_cast<State *>(p)->seek(n); };
  result.encode_text = [](void *p, const char *t, std::uint16_t *ids, unsigned cap, unsigned &n, bool bos) {
    return static_cast<State *>(p)->local.encode(t, ids, cap, n, bos);
  };
  result.decode_token = [](void *p, std::uint16_t t, char *out, unsigned cap, unsigned &n) {
    return static_cast<State *>(p)->local.decode(t, out, cap, n);
  };
  result.step = [](void *p, std::uint16_t token, bool output, std::uint16_t &best,
                   bool (*service)(void *), void *raw, Arithmetic mode,
                   bool (*allowed)(void *, std::uint16_t), void *policy) {
    return static_cast<State *>(p)->step(&token, 1, output, best, service, raw, mode, allowed, policy);
  };
  result.batch_capacity = [](void *p) { auto &s = *static_cast<State *>(p); return s.wire.ready() ? s.lanes : 0U; };
  result.batch_step = [](void *p, const std::uint16_t *ids, unsigned n, Arithmetic mode,
                         bool (*service)(void *), void *raw) {
    std::uint16_t unused;
    return static_cast<State *>(p)->step(ids, n, false, unused, service, raw, mode, nullptr, nullptr);
  };
  if (s->can_verify) {
    result.verify_spec = [](void *p, const SpecProtocol &spec, std::uint16_t token, unsigned generated,
                             VerifiedTokens &out, bool (*service)(void *), void *context) {
      Pump pump{service, context};
      return static_cast<State *>(p)->verify(spec, token, generated, out, pump);
    };
  }
  return result;
#else
  return local_inference(local_);
#endif
}
} // namespace picocalc::ai_tang
