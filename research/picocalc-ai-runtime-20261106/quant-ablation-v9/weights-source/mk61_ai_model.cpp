#include "mk61_ai_model.hpp"
#include "research_codebook.hpp"
#include "mk61_ai_kernels.h"
#include "mk61_ai_linear.hpp"
#include "mk61_ai_swar.hpp"
#include <algorithm>
#include <cfloat>
#include <cmath>
#include <cstring>

namespace mk61ai {
namespace {
std::uint32_t crc(const std::uint8_t *p, unsigned n,
                  std::uint32_t value = ~0U) {
  static constexpr std::uint32_t table[16] = {
      0,          0x1db71064, 0x3b6e20c8, 0x26d930ac, 0x76dc4190, 0x6b6b51f4,
      0x4db26158, 0x5005713c, 0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
      0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c};
  while (n--) {
    value ^= *p++;
    value = (value >> 4) ^ table[value & 15];
    value = (value >> 4) ^ table[value & 15];
  }
  return value;
}
bool extent(std::uint32_t offset, std::uint32_t bytes, std::uint32_t size) {
  return offset <= size && bytes <= size - offset;
}
bool transfer(const Memory &m, std::uint32_t offset, void *data, unsigned bytes,
              bool writing = false) {
  if (!extent(offset, bytes, m.size) || (writing ? !m.write : !m.read))
    return false;
  auto *p = static_cast<std::uint8_t *>(data);
  while (bytes) {
    const unsigned n = std::min(bytes, 4096U);
    if (writing ? !m.write(m.context, offset, p, n)
                : !m.read(m.context, offset, p, n))
      return false;
    p += n;
    offset += n;
    bytes -= n;
  }
  return true;
}
float half(std::uint16_t h) {
  const unsigned sign = h >> 15, exponent = (h >> 10) & 31, mantissa = h & 1023;
  if (exponent == 31)
    return mantissa ? NAN : sign ? -INFINITY : INFINITY;
  float value;
  if (exponent) {
    const std::uint32_t bits = ((exponent + 112) << 23) | (mantissa << 13);
    std::memcpy(&value, &bits, 4);
  } else
    value = float(mantissa) * 0x1p-24f;
  return sign ? -value : value;
}
unsigned code(const std::uint8_t *data, unsigned at, unsigned bits) {
  const unsigned bit = at * bits, shift = bit & 7;
  unsigned value = data[bit >> 3] >> shift;
  if (shift + bits > 8)
    value |= unsigned(data[(bit >> 3) + 1]) << (8 - shift);
  return value & ((1U << bits) - 1);
}
unsigned tensor_code(const std::uint8_t *data, unsigned at, unsigned bits,
                     bool planes) {
  if (!planes)
    return code(data, at, bits);
  const unsigned group = at / 32, quartet = (at % 32) / 4, lane = at % 4;
  unsigned value = 0;
  for (unsigned b = 0; b < bits; ++b) {
    const unsigned index =
        (data[group * bits * 4 + b * 4 + quartet / 2] >> (4 * (quartet % 2))) &
        15;
    value |= ((index >> lane) & 1) << b;
  }
  return value;
}
} // namespace
bool Model::read(std::uint32_t offset, void *out, unsigned n) const {
  return transfer(package_, offset, out, n);
}
bool Model::tensor(unsigned index, Tensor &t) const {
  return read(header_[15] + index * 32, &t, sizeof(t));
}
ModelStatus Model::open(Memory package, bool verify) {
  package_ = package;
  workspace_ = nullptr;
  bound_ = 0;
  position_ = 0;
  cache_ = {};
  config_ = {};
  if (package.size < 128 || !read(0, header_, 128))
    return ModelStatus::IO;
  if (std::memcmp(header_, "M61AI01\0", 8) || header_[2] != 1 ||
      header_[3] != package.size ||
      ~crc(reinterpret_cast<const std::uint8_t *>(header_), 124) != header_[31])
    return ModelStatus::FORMAT;
  std::memcpy(&config_, header_ + 4, 40);
  std::memcpy(&config_.epsilon, header_ + 14, 4);
  const auto &c = config_;
  if (!c.layers || c.layers > 32 || !c.hidden || c.hidden > 512 ||
      c.hidden % 32 || !c.intermediate || c.intermediate > 2048 ||
      c.intermediate % 32 || !c.heads || c.heads > 16 || !c.kv_heads ||
      c.heads % c.kv_heads || !c.head_dim || c.head_dim > 128 ||
      c.head_dim % 2 || c.heads * c.head_dim > 1024 ||
      c.kv_heads * c.head_dim > 1024 || !c.vocab || c.vocab > 65535 ||
      !c.context || c.context > 2048 || c.bos >= c.vocab || c.eos >= c.vocab ||
      !std::isfinite(c.epsilon) || c.epsilon <= 0 || header_[28] != 1)
    return ModelStatus::FORMAT;
  const unsigned counts[] = {
      2 + 11 * c.layers, c.vocab,     header_[18], 256,
      header_[21],       header_[23], header_[25], c.context * c.head_dim};
  const unsigned sizes[] = {32, 8, 12, 2, 24, 12, 12, 4};
  const unsigned indices[] = {15, 16, 17, 19, 20, 22, 24, 26};
  for (unsigned i = 0; i < 8; ++i)
    if (counts[i] > package.size / sizes[i] ||
        !extent(header_[indices[i]], counts[i] * sizes[i], package.size))
      return ModelStatus::FORMAT;
  for (unsigned i = 0; i < 2 + 11 * c.layers; ++i) {
    Tensor t{};
    if (!tensor(i, t))
      return ModelStatus::IO;
    unsigned rows = 1, cols = c.hidden;
    if (i == 0)
      rows = c.vocab;
    else if (i >= 2)
      switch ((i - 2) % 11) {
      case 1:
        rows = c.heads * c.head_dim;
        break;
      case 2:
      case 3:
        rows = c.kv_heads * c.head_dim;
        break;
      case 4:
      case 5:
        cols = c.head_dim;
        break;
      case 6:
        rows = c.hidden;
        cols = c.heads * c.head_dim;
        break;
      case 8:
      case 9:
        rows = c.intermediate;
        break;
      case 10:
        rows = c.hidden;
        cols = c.intermediate;
        break;
      }
    if (t.rows != rows || t.cols != cols ||
        !extent(t.data, t.bytes, package.size) ||
        !extent(t.scale, t.scales, package.size))
      return ModelStatus::FORMAT;
    const bool vector =
        i == 1 || (i >= 2 && ((i - 2) % 11 == 0 || (i - 2) % 11 == 4 ||
                              (i - 2) % 11 == 5 || (i - 2) % 11 == 7));
    if (vector ? t.bits != 32 || t.bytes != cols * 4 || t.scales || t.grid
               : (t.bits != 2 && t.bits != 3 && t.bits != 4) || cols % 32 ||
                     t.bytes != rows * cols * t.bits / 8 ||
                     t.scales != rows * cols / 16 ||
                     (t.grid & ~(256U|512U|1024U)) != (t.bits == 4 ? 0U : 1U))
      return ModelStatus::FORMAT;
  }
  if (verify) {
    std::uint8_t buffer[256];
    std::uint32_t value = ~0U;
    for (unsigned offset = 128; offset < package.size;) {
      const unsigned n =
          std::min<unsigned>(unsigned(sizeof(buffer)), package.size - offset);
      if (!read(offset, buffer, n))
        return ModelStatus::IO;
      value = crc(buffer, n, value);
      offset += n;
    }
    if (~value != header_[29])
      return ModelStatus::FORMAT;
  }
  return ModelStatus::OK;
}
std::uint32_t Model::cache_bytes() const {
  return 8 * config_.layers * config_.context * config_.kv_heads *
         config_.head_dim;
}
std::size_t Model::workspace_bytes() const {
  const auto &c = config_;
  const unsigned columns =
      std::max(std::max(c.hidden, c.intermediate), c.heads * c.head_dim);
  const unsigned floats = 3 * c.hidden + 2 * c.heads * c.head_dim +
                          2 * c.kv_heads * c.head_dim + 2 * c.intermediate +
                          c.context;
  const unsigned raw =
      std::max<unsigned>(4 * std::max(c.hidden, c.head_dim), columns * 9 / 16);
  const unsigned needed =
      4 * floats + raw + 2 * columns + 4 * (columns / 8 + columns / 32) + 16 * columns +
      16 * (columns * 9 / 16) + 8 * sizeof(float) + 16;
  return std::max(needed, 6U * MAX_TEXT);
}
ModelStatus Model::bind(void *workspace, std::size_t n, Memory cache) {
  if (!workspace || reinterpret_cast<std::uintptr_t>(workspace) % 4 ||
      n < workspace_bytes() || cache.size < cache_bytes() || !cache.read ||
      !cache.write)
    return ModelStatus::MEMORY;
  workspace_ = static_cast<std::uint8_t *>(workspace);
  bound_ = n;
  cache_ = cache;
  position_ = 0;
  return ModelStatus::OK;
}
ModelStatus Model::forward(std::uint16_t token, bool output,
                           std::uint16_t &best, bool (*service)(void *),
                           void *context, Arithmetic arithmetic, float *logits,
                           bool (*allowed)(void *, std::uint16_t),
                           void *policy) {
  if (!workspace_)
    return ModelStatus::MEMORY;
  if (token >= config_.vocab)
    return ModelStatus::FORMAT;
  if (position_ >= config_.context)
    return ModelStatus::CONTEXT;
  compute_metrics_ = {};
  // Every exit, including cancellation and I/O/numeric faults, thaws the
  // screen. Per-tile joins below happen before this scope can be left.
  struct Busy {
    ComputeExecution execution;
    explicit Busy(ComputeExecution e) : execution(e) {
      if (execution.busy) execution.busy(execution.context, true);
    }
    ~Busy() {
      if (execution.busy) execution.busy(execution.context, false);
    }
  } busy(execution_);
  const auto &c = config_;
  const unsigned qn = c.heads * c.head_dim, kn = c.kv_heads * c.head_dim;
  float *cursor = reinterpret_cast<float *>(workspace_);
  auto take = [&](unsigned n) {
    float *p = cursor;
    cursor += n;
    return p;
  };
  float *x = take(c.hidden), *n = take(c.hidden), *q = take(qn), *k = take(kn),
        *v = take(kn), *a = take(qn), *o = take(c.hidden),
        *gate = take(c.intermediate), *up = take(c.intermediate),
        *scores = take(c.context);
  auto *raw = reinterpret_cast<std::uint8_t *>(cursor);
  const unsigned columns =
      std::max(std::max(c.hidden, c.intermediate), c.heads * c.head_dim);
  const unsigned raw_bytes =
      std::max<unsigned>(4 * std::max(c.hidden, c.head_dim), columns * 9 / 16);
  auto *quant = reinterpret_cast<std::int8_t *>(raw + raw_bytes);
  auto *quant16 = reinterpret_cast<std::int16_t *>(quant);
  auto *activation_scales = reinterpret_cast<float *>(
      (reinterpret_cast<std::uintptr_t>(quant + 2 * columns) + 3) &
      ~std::uintptr_t(3));
  auto *input_sums = activation_scales + columns / 8;
  auto *lookup = input_sums + columns / 32;
  auto *tile = reinterpret_cast<std::uint8_t *>(lookup + 4 * columns);
  const unsigned tile_bytes = 8 * columns * 9 / 16;
  auto *tile_output = reinterpret_cast<float *>(tile + 2 * tile_bytes);
  ModelStatus status = ModelStatus::OK;
  auto alive = [&]() {
    if (service && !service(context)) {
      status = ModelStatus::CANCELLED;
      return false;
    }
    return true;
  };
  auto record_value = [&](float value) {
    std::uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    compute_metrics_.checksum = (compute_metrics_.checksum ^ bits) * 16777619U;
  };
  auto row = [&](const Tensor &t, unsigned r) -> bool {
    const unsigned bytes = t.cols * t.bits / 8, scales = t.cols / 16;
    if (!read(t.data + r * bytes, raw, bytes) ||
        !read(t.scale + r * scales, raw + bytes, scales)) {
      status = ModelStatus::IO;
      return false;
    }
    return true;
  };
  auto weight = [&](const Tensor &t, unsigned j) -> float {
    const unsigned at = t.cols * t.bits / 8 + 2 * (j / 32);
    const float scale =
        half(std::uint16_t(raw[at]) | (std::uint16_t(raw[at + 1]) << 8));
    const unsigned u = tensor_code(raw, j, t.bits, (t.grid & 256) != 0);
    if(t.grid&1536U)return float(research_coefficient(t.grid,u))*scale;
    return ((t.grid & 1)
                ? (float(u) * (2.0f / float((1U << t.bits) - 1)) - 1.0f)
                : float(int(u) - 8)) *
           scale;
  };
  auto linear = [&](unsigned index, const float *input, float *dest,
                    bool head) -> bool {
    Tensor t{};
    if (!tensor(index, t)) {
      status = ModelStatus::IO;
      return false;
    }
    const Quantization settings=execution_.precision?execution_.precision(execution_.context,index,position_,arithmetic):Quantization{arithmetic};
    const Arithmetic mode=settings.mode;
    const unsigned activation_group=settings.group;
    if((activation_group!=8 && activation_group!=16 && activation_group!=32) ||
       ((mode==Arithmetic::LUT_FLOAT32 || mode==Arithmetic::LUT_INT8 || mode==Arithmetic::SWAR_INT8) && activation_group!=32)) {
      status=ModelStatus::FORMAT;return false;
    }
    const bool integer =
        mode == Arithmetic::INT8 || mode == Arithmetic::LUT_INT8 ||
        mode == Arithmetic::SWAR_INT8 || mode == Arithmetic::INT16;
    const bool tables = mode == Arithmetic::LUT_INT8 ||
                        mode == Arithmetic::LUT_FLOAT32;
    if(integer) {
      const int limit=mode==Arithmetic::INT16?32767:127;
      std::uint32_t rng=settings.seed^(0x9e3779b9U*(index+1))^(0x85ebca6bU*(position_+1));if(!rng)rng=1;
      for(unsigned at=0;at<t.cols;at+=activation_group) {
        float maximum=0;
        for(unsigned j=0;j<activation_group;++j)maximum=std::max(maximum,std::fabs(input[at+j]));
        if(!std::isfinite(maximum)){status=ModelStatus::NUMERIC;return false;}
        const float scale=maximum/float(limit);activation_scales[at/activation_group]=scale;
        for(unsigned j=0;j<activation_group;++j) {
          int q=0;
          if(scale) {
            const float value=input[at+j]/scale;
            if(settings.stochastic) {
              const float magnitude=std::fabs(value);q=int(magnitude);
              rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
              if(float(rng>>8)*0x1p-24f<magnitude-float(q))++q;
              if(value<0)q=-q;
            } else q=int(std::round(value));
            q=std::max(-limit,std::min(limit,q));
          }
          if(mode==Arithmetic::INT16)quant16[at+j]=std::int16_t(q);else quant[at+j]=std::int8_t(q);
        }
      }
    }
    if (mode == Arithmetic::SWAR_INT8) {
      for (unsigned g = 0; g < t.cols / 32; ++g)
        input_sums[g] = float(swar::prepare32(quant + 32 * g,
            reinterpret_cast<std::uint32_t *>(lookup) + 16 * g));
    }
    if (tables) {
      for (unsigned g = 0; g < t.cols / 32; ++g) {
        float total = 0;
        for (unsigned quartet = 0; quartet < 8; ++quartet) {
          const unsigned start = g * 32 + quartet * 4;
          const unsigned at = (g * 8 + quartet) * 16;
          if (integer) {
            auto *table = reinterpret_cast<std::int16_t *>(lookup) + at;
            table[0] = 0;
            for (unsigned lane = 0; lane < 4; ++lane)
              for (unsigned mask = 0; mask < (1U << lane); ++mask)
                table[mask + (1U << lane)] =
                    std::int16_t(table[mask] + quant[start + lane]);
            total += float(table[15]);
          } else {
            float *table = lookup + at;
            table[0] = 0;
            for (unsigned lane = 0; lane < 4; ++lane)
              for (unsigned mask = 0; mask < (1U << lane); ++mask)
                table[mask + (1U << lane)] = table[mask] + input[start + lane];
            total += table[15];
          }
        }
        input_sums[g] = total;
      }
    }
    if(head && logits && execution_.filter_logits)std::fill(logits,logits+c.vocab,-FLT_MAX);
    float maximum = -FLT_MAX;
    best = 0;
    if (execution_.kernel != LinearKernel::REFERENCE) {
      constexpr unsigned TILE = 8;
      const unsigned bytes = t.cols * t.bits / 8, scales = t.cols / 16;
      auto kernel = execution_.kernel == LinearKernel::SRAM
                        ? linear_batch_sram : linear_batch_flash;
      struct Tile {
        std::uint8_t *data;
        std::uint16_t indices[TILE]{};
        unsigned count = 0;
      } tiles[2]{{tile}, {tile + tile_bytes}};
      // No service, tokenizer, KV or other PSRAM access is made while the
      // read is outstanding. Destruction drains even numeric/cancel exits.
      struct Pending {
        Memory memory;
        bool active = false;
        bool finish() {
          if (!active) return true;
          active = false;
          return memory.read_finish(memory.context);
        }
        ~Pending() { finish(); }
      } pending{package_};
      const bool prefetch = execution_.prefetch && package_.read_begin && package_.read_finish;
      auto stamp = [&]() { return execution_.micros ? execution_.micros(execution_.context) : 0U; };
      unsigned r = 0;
      auto load = [&](Tile &target, bool asynchronous) {
        target.count = 0;
        if (r == t.rows) return true;
        if (!alive()) return false;
        for (; r < t.rows && target.count < TILE; ++r) {
          if (head && execution_.filter_head && allowed && (!logits || execution_.filter_logits) &&
              !allowed(policy, std::uint16_t(r))) {
            ++compute_metrics_.skipped_rows;
            // A completely masked vocabulary still services Esc/USB.
            if ((r & 31U) == 31 && !alive()) return false;
            continue;
          }
          target.indices[target.count++] = std::uint16_t(r);
        }
        if (!target.count) return true;
        auto *tile_scales = target.data + TILE * bytes;
        block_io::ReadSpan spans[2 * TILE];
        unsigned span_count = 0;
        for (unsigned part = 0; part < 2; ++part) {
          const unsigned stride = part ? scales : bytes;
          for (unsigned start = 0; start < target.count;) {
            unsigned end = start + 1;
            while (end < target.count && target.indices[end] == target.indices[end - 1] + 1) ++end;
            spans[span_count++] = {
                (part ? t.scale : t.data) + unsigned(target.indices[start]) * stride,
                (part ? tile_scales : target.data) + start * stride,
                (end - start) * stride};
            start = end;
          }
        }
        const auto read_started = stamp();
        if (asynchronous) {
          bool valid = true;
          unsigned total = 0;
          for (unsigned i = 0; i < span_count; ++i) {
            valid = valid && extent(spans[i].offset, spans[i].bytes, package_.size);
            total += spans[i].bytes;
          }
          if (valid && package_.read_begin(package_.context, spans, span_count)) {
            pending.active = true;
            ++compute_metrics_.prefetches;
            compute_metrics_.prefetched_bytes += total;
            compute_metrics_.read_us += stamp() - read_started;
            return true;
          }
        }
        // Coalesce adjacent rows. Sparse grammar masks do not fetch weights
        // of rejected tokens; no tokenizer/embedding IDs are changed.
        for (unsigned start = 0; start < target.count;) {
          unsigned end = start + 1;
          while (end < target.count && target.indices[end] == target.indices[end - 1] + 1) ++end;
          if (!read(t.data + unsigned(target.indices[start]) * bytes,
                    target.data + start * bytes, (end - start) * bytes) ||
              !read(t.scale + unsigned(target.indices[start]) * scales,
                    tile_scales + start * scales, (end - start) * scales)) {
            status = ModelStatus::IO;
            return false;
          }
          start = end;
        }
        compute_metrics_.read_us += stamp() - read_started;
        return true;
      };
      unsigned current = 0;
      if (!load(tiles[current], false)) return false;
      while (tiles[current].count) {
        auto &active = tiles[current];
        auto &next = tiles[current ^ 1];
        // Both cores use only active.data and the immutable LUT. DMA owns
        // next.data and a persistent driver command list until the join.
        if (prefetch && !load(next, true)) return false;
        const unsigned count = active.count;
        const auto matmul_started = stamp();
        LinearBatch first{};
        first.arithmetic = mode;first.quant16=quant16;first.activation_group=activation_group;
        first.columns = t.cols;first.bits = t.bits;first.grid = t.grid;
        first.rows = count;first.input = input;first.quant = quant;
        first.activation_scales = activation_scales;
        first.input_sums = input_sums;first.lookup = lookup;
        first.weights = active.data;first.scales = active.data + TILE * bytes;
        first.output = tile_output;
        LinearBatch second = first;
        bool submitted = false;
        if (count > 1 && execution_.submit && execution_.join) {
          const unsigned local = (count + 1) / 2;
          second.rows = count - local;
          second.weights += local * bytes;second.scales += local * scales;
          second.output += local;
          submitted = execution_.submit(execution_.context, kernel, &second);
          if (submitted) {
            first.rows = local;
            ++compute_metrics_.worker_jobs;
            compute_metrics_.worker_rows += second.rows;
          }
        }
        kernel(&first);
        // Join even if local computation failed: the descriptor and shared
        // LUT must remain alive until core 1 has published completion.
        if (submitted) execution_.join(execution_.context);
        compute_metrics_.matmul_us += stamp() - matmul_started;
        if (pending.active) {
          const auto wait_started = stamp();
          const bool complete = pending.finish();
          compute_metrics_.wait_us += stamp() - wait_started;
          if (!complete) {
            status = ModelStatus::IO;
            return false;
          }
        }
        if (first.status != ModelStatus::OK ||
            (submitted && second.status != ModelStatus::OK)) {
          status = first.status != ModelStatus::OK ? first.status : second.status;
          return false;
        }
        compute_metrics_.rows += count;
        for (unsigned j = 0; j < count; ++j) {
          const unsigned at = active.indices[j];
          const float value = tile_output[j];
          record_value(value);
          if (head) {
            if (logits) logits[at] = value;
            if (value > maximum && (!allowed || allowed(policy, std::uint16_t(at)))) {
              maximum = value;best = std::uint16_t(at);
            }
          } else dest[at] = value;
        }
        if (!prefetch && !load(next, false)) return false;
        current ^= 1;
      }
      if (head && maximum == -FLT_MAX) {
        status = ModelStatus::FORMAT;
        return false;
      }
      return true;
    }
    for (unsigned r = 0; r < t.rows; ++r) {
      if ((r & 7U) == 0 && !alive())
        return false;
      if (!row(t, r))
        return false;
      ++compute_metrics_.rows;
      float value = 0;
      if (mode == Arithmetic::FLOAT32)
        for (unsigned g = 0; g < t.cols / 32; ++g) {
          const unsigned at = t.cols * t.bits / 8 + 2 * g;
          const float scale =
              half(std::uint16_t(raw[at]) | (std::uint16_t(raw[at + 1]) << 8));
          for (unsigned j = 0; j < 32; ++j) {
            const unsigned u =
                tensor_code(raw, g * 32 + j, t.bits, (t.grid & 256) != 0);
            const float coefficient =
                (t.grid & 1)
                    ? float(u) * (2.0f / float((1U << t.bits) - 1)) - 1.0f
                    : float(int(u) - 8);
            value += input[g * 32 + j] * (coefficient * scale);
          }
        }
      else if (!tables) {
        for(unsigned g=0;g<t.cols/32;++g) {
          const unsigned at=t.cols*t.bits/8+2*g;
          float scale=half(std::uint16_t(raw[at])|(std::uint16_t(raw[at+1])<<8));
          if(t.grid&1)scale/=float((1U<<t.bits)-1);
          for(unsigned part=0;part<32;part+=activation_group) {
            std::int32_t sum=0;
            for(unsigned j=0;j<activation_group;++j) {
              const unsigned col=32*g+part+j;
              const int u=int(tensor_code(raw,col,t.bits,(t.grid&256)!=0));
              const int weight=(t.grid&1)?2*u-int((1U<<t.bits)-1):u-8;
              sum+=weight*(mode==Arithmetic::INT16?int(quant16[col]):int(quant[col]));
            }
            value+=float(sum)*scale*activation_scales[(32*g+part)/activation_group];
          }
        }
      }
      else
        for (unsigned g = 0; g < t.cols / 32; ++g) {
          std::uint8_t converted[16];
          const std::uint8_t *indices = raw + g * t.bits * 4;
          if (!(t.grid & 256)) {
            if (t.bits == 4)
              mk61ai_pack_q4_planes32(indices, converted);
            else if (t.bits == 2)
              mk61ai_pack_q2_planes32(indices, converted);
            else {
              std::memset(converted, 0, 12);
              for (unsigned bit = 0; bit < 3; ++bit)
                for (unsigned quartet = 0; quartet < 8; ++quartet) {
                  unsigned index = 0;
                  for (unsigned lane = 0; lane < 4; ++lane)
                    index |= ((code(indices, quartet * 4 + lane, 3) >> bit) & 1)
                             << lane;
                  converted[bit * 4 + quartet / 2] |=
                      std::uint8_t(index << (4 * (quartet % 2)));
                }
            }
            indices = converted;
          }
          float weighted = 0;
          std::int32_t weighted_integer = 0;
          for (unsigned bit = 0; bit < t.bits; ++bit) {
            float sum = 0;
            std::int32_t isum = 0;
            for (unsigned quartet = 0; quartet < 8; ++quartet) {
              const unsigned index = (indices[bit * 4 + quartet / 2] >>
                                      (4 * (quartet % 2))) &
                                     15,
                             at = (g * 8 + quartet) * 16 + index;
              if (integer)
                isum += reinterpret_cast<const std::int16_t *>(lookup)[at];
              else
                sum += lookup[at];
            }
            if (integer)
              weighted_integer += isum * int(1U << bit);
            else
              weighted += sum * float(1U << bit);
          }
          const unsigned at = t.cols * t.bits / 8 + 2 * g;
          const float scale =
              half(std::uint16_t(raw[at]) | (std::uint16_t(raw[at + 1]) << 8));
          if (integer) {
            const std::int32_t sum =
                (t.grid & 1) ? 2 * weighted_integer -
                                   int((1U << t.bits) - 1) * int(input_sums[g])
                             : weighted_integer - 8 * int(input_sums[g]);
            value +=
                float(sum) *
                ((t.grid & 1) ? scale / float((1U << t.bits) - 1) : scale) *
                activation_scales[g];
          } else
            value +=
                ((t.grid & 1) ? weighted * (2.0f / float((1U << t.bits) - 1)) -
                                    input_sums[g]
                              : weighted - 8.0f * input_sums[g]) *
                scale;
        }
      if (!std::isfinite(value)) {
        status = ModelStatus::NUMERIC;
        return false;
      }
      record_value(value);
      if (head) {
        if (logits)
          logits[r] = value;
        if (value > maximum &&
            (!allowed || allowed(policy, std::uint16_t(r)))) {
          maximum = value;
          best = std::uint16_t(r);
        }
      } else
        dest[r] = value;
    }
    if (head && maximum == -FLT_MAX) {
      status = ModelStatus::FORMAT;
      return false;
    }
    return true;
  };
  auto normalize = [&](unsigned index, const float *input, float *dest,
                       unsigned groups, unsigned width) -> bool {
    Tensor t{};
    if (!tensor(index, t) || !read(t.data, raw, width * 4)) {
      status = ModelStatus::IO;
      return false;
    }
    const auto *weights = reinterpret_cast<const float *>(raw);
    for (unsigned g = 0; g < groups; ++g) {
      float sum = 0;
      for (unsigned j = 0; j < width; ++j) {
        const float value = input[g * width + j];
        sum += value * value;
      }
      const float factor = 1.0f / std::sqrt(sum / float(width) + c.epsilon);
      if (!std::isfinite(factor)) {
        status = ModelStatus::NUMERIC;
        return false;
      }
      for (unsigned j = 0; j < width; ++j)
        dest[g * width + j] = (input[g * width + j] * factor) * weights[j];
    }
    return true;
  };
  Tensor embedding{};
  if (!tensor(0, embedding) || !row(embedding, token))
    return status == ModelStatus::OK ? ModelStatus::IO : status;
  for (unsigned j = 0; j < c.hidden; ++j)
    x[j] = weight(embedding, j);
  for (unsigned layer = 0; layer < c.layers; ++layer) {
    const unsigned base = 2 + 11 * layer;
    if (!normalize(base, x, n, 1, c.hidden) || !linear(base + 1, n, q, false) ||
        !linear(base + 2, n, k, false) || !linear(base + 3, n, v, false) ||
        !normalize(base + 4, q, q, c.heads, c.head_dim) ||
        !normalize(base + 5, k, k, c.kv_heads, c.head_dim))
      return status;
    if (!read(header_[26] + position_ * c.head_dim * 4, raw, c.head_dim * 4))
      return ModelStatus::IO;
    const auto *rotary = reinterpret_cast<const float *>(raw);
    for (unsigned which = 0; which < 2; ++which) {
      float *values = which ? k : q;
      const unsigned heads = which ? c.kv_heads : c.heads;
      for (unsigned h = 0; h < heads; ++h)
        for (unsigned j = 0; j < c.head_dim / 2; ++j) {
          float &left = values[h * c.head_dim + j];
          float &right = values[h * c.head_dim + j + c.head_dim / 2];
          const float old = left, cosine = rotary[2 * j],
                      sine = rotary[2 * j + 1];
          left = old * cosine - right * sine;
          right = right * cosine + old * sine;
        }
    }
    const unsigned layer_offset = layer * c.context * kn * 8;
    if (!transfer(cache_, layer_offset + position_ * kn * 8, k, kn * 4, true) ||
        !transfer(cache_, layer_offset + position_ * kn * 8 + kn * 4, v, kn * 4,
                  true))
      return ModelStatus::IO;
    const float attention_scale = 1.0f / std::sqrt(float(c.head_dim));
    for (unsigned h = 0; h < c.heads; ++h) {
      float maximum = -FLT_MAX, sum = 0;
      const unsigned kh = h / (c.heads / c.kv_heads);
      for (unsigned t = 0; t <= position_; ++t) {
        if ((t & 31U) == 0 && !alive())
          return status;
        if (!transfer(cache_, layer_offset + t * kn * 8 + kh * c.head_dim * 4,
                      k, c.head_dim * 4))
          return ModelStatus::IO;
        float dot = 0;
        for (unsigned j = 0; j < c.head_dim; ++j)
          dot += q[h * c.head_dim + j] * k[j];
        scores[t] = dot * attention_scale;
        maximum = std::max(maximum, scores[t]);
      }
      for (unsigned t = 0; t <= position_; ++t) {
        scores[t] = std::exp(scores[t] - maximum);
        sum += scores[t];
      }
      if (!std::isfinite(sum) || sum <= 0)
        return ModelStatus::NUMERIC;
      std::fill(a + h * c.head_dim, a + (h + 1) * c.head_dim, 0.0f);
      for (unsigned t = 0; t <= position_; ++t) {
        if (!transfer(cache_,
                      layer_offset + t * kn * 8 + kn * 4 + kh * c.head_dim * 4,
                      v, c.head_dim * 4))
          return ModelStatus::IO;
        const float factor = scores[t] / sum;
        for (unsigned j = 0; j < c.head_dim; ++j)
          a[h * c.head_dim + j] += factor * v[j];
      }
    }
    if (!linear(base + 6, a, o, false))
      return status;
    for (unsigned j = 0; j < c.hidden; ++j)
      x[j] += o[j];
    if (!normalize(base + 7, x, n, 1, c.hidden) ||
        !linear(base + 8, n, gate, false) || !linear(base + 9, n, up, false))
      return status;
    for (unsigned j = 0; j < c.intermediate; ++j)
      gate[j] = (gate[j] / (1.0f + std::exp(-gate[j]))) * up[j];
    if (!linear(base + 10, gate, o, false))
      return status;
    for (unsigned j = 0; j < c.hidden; ++j)
      x[j] += o[j];
  }
  if (output &&
      (!normalize(1, x, n, 1, c.hidden) || !linear(0, n, nullptr, true)))
    return status;
  ++position_;
  return ModelStatus::OK;
}
const char *model_status_text(ModelStatus s) {
  static const char *const names[] = {"OK",
                                      "model I/O error",
                                      "invalid model package",
                                      "not enough memory",
                                      "text too long",
                                      "context exhausted",
                                      "cancelled",
                                      "non-finite model result"};
  return names[unsigned(s) < 8 ? unsigned(s) : 2];
}
} // namespace mk61ai
