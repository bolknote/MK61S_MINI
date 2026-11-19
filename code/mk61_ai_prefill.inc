// Included by mk61_ai_model.cpp so both paths use the same package reader,
// tensor unpacker, INT8 preparation, kernels and KV stream.
#if defined(PICO_ON_DEVICE)
#define MK61_PREFILL_CODE __attribute__((section(".ai_prefill_extension"),noinline))
#else
#define MK61_PREFILL_CODE
#endif
namespace {
constexpr unsigned pair_head_width = 32, pair_heads = 4, pair_kv_heads = 2;
constexpr unsigned pair_hidden = pair_heads * pair_head_width;
constexpr unsigned pair_kv = pair_kv_heads * pair_head_width;
constexpr unsigned pair_kv_tile = 16 * pair_head_width * sizeof(float);

struct PairLayout {
  unsigned columns, rows, tile, lookup, scores, state, linear, attention;
  explicit PairLayout(const ModelConfig &c, const ComputeExecution &ex)
      : columns(std::max(c.hidden, c.intermediate)), rows(row_limit(ex.tile_rows)),
        tile(weight_tile_bytes(columns,c.hidden,rows)), lookup(lookup_bytes(columns,ex.lut8)),
        scores(2*c.context*sizeof(float)),
        state(2*(3*pair_hidden+2*pair_kv+2*c.intermediate)*sizeof(float)),
        linear(lookup+2*tile+2*(columns+2*(columns/32)*sizeof(float))),
        attention(scores+2*pair_kv_tile) {}
  unsigned extra() const { return std::max(lookup,scores); }
  unsigned base() const { return state+std::max(linear,attention); }
};
} // namespace

MK61_PREFILL_CODE std::size_t Model::prefill_pair_workspace_bytes(Arithmetic arithmetic) const {
  if(arithmetic!=Arithmetic::INT8 || !workspace_ || !parameters_ ||
     execution_.kernel==LinearKernel::REFERENCE || !execution_.share_kv ||
     execution_.remote_prepare || execution_.remote_submit || execution_.remote_join ||
     config_.hidden!=pair_hidden || config_.heads!=pair_heads ||
     config_.kv_heads!=pair_kv_heads || config_.head_dim!=pair_head_width)
    return 0;
  const PairLayout layout(config_,execution_);
  return bound_>=layout.base()?layout.extra():0;
}

MK61_PREFILL_CODE ModelStatus Model::prefill_pair(const std::uint16_t (&tokens)[2], void *extra,
                               std::size_t extra_bytes, Arithmetic arithmetic,
                               bool (*service)(void *), void *context,
                               std::uint32_t *checksums) {
  const auto need=prefill_pair_workspace_bytes(arithmetic);
  const auto base_address=reinterpret_cast<std::uintptr_t>(workspace_);
  const auto extra_address=reinterpret_cast<std::uintptr_t>(extra);
  if(!need || !extra || extra_bytes<need || extra_address%alignof(float) ||
     (extra_address>=base_address ? extra_address-base_address<bound_ : base_address-extra_address<need))
    return ModelStatus::MEMORY;
  const auto &c=config_;
  if(tokens[0]>=c.vocab || tokens[1]>=c.vocab) return ModelStatus::FORMAT;
  if(position_>=c.context || c.context-position_<2) return ModelStatus::CONTEXT;
  const PairLayout sizes(c,execution_);
  const auto &ex=execution_;
  auto &m=compute_metrics_;
  m={};
  auto stamp=[&] { return ex.micros?ex.micros(ex.context):0U; };
  const auto busy_started=stamp();
  if(ex.busy) ex.busy(ex.context,true);
  m.presentation_us+=stamp()-busy_started;
  struct BusyGuard {
    const ComputeExecution &ex;
    ComputeMetrics &m;
    ~BusyGuard() {
      const auto before=ex.micros?ex.micros(ex.context):0U;
      if(ex.busy) ex.busy(ex.context,false);
      if(ex.micros) m.presentation_us+=ex.micros(ex.context)-before;
    }
  } busy{ex,m};
  const auto start=stamp();
  auto alive=[&] {
    if(!service) return true;
    const auto before=stamp();
    const bool ok=service(context);
    m.service_us+=stamp()-before;
    ++m.service_calls;
    return ok;
  };

  struct Lane {
    float *x,*n,*q,*kv,*gate,*up;
    LinearBatch shape{};
    std::uint32_t checksum=2166136261U;
    unsigned columns=0;
    bool lut_ready=false;
  } lanes[2]{};
  auto *cursor=reinterpret_cast<float *>(workspace_);
  auto take=[&](unsigned count) { auto *out=cursor;cursor+=count;return out; };
  auto *kv=take(4*pair_kv);
  for(unsigned lane=0;lane<2;++lane) {
    auto &v=lanes[lane];
    v.x=take(pair_hidden);v.n=take(pair_hidden);v.q=take(pair_hidden);
    v.kv=kv+lane*2*pair_kv;
    v.gate=take(c.intermediate);v.up=take(c.intermediate);
  }
  // Attention borrows weight/activation scratch; linear jobs are joined and
  // neither packed input is reused across that boundary.
  auto *arena=reinterpret_cast<std::uint8_t *>(cursor);
  auto *second=reinterpret_cast<float *>(extra);
  lanes[0].shape.lookup=cursor;
  lanes[1].shape.lookup=second;
  auto *tile_base=arena+sizes.lookup;
  auto *prepared=tile_base+2*sizes.tile;
  for(auto &v:lanes) {
    v.shape.arithmetic=Arithmetic::INT8;
    v.shape.quant=reinterpret_cast<std::int8_t *>(prepared);
    prepared+=sizes.columns;
    v.shape.activation_scales=reinterpret_cast<float *>(prepared);
    prepared+=sizes.columns/32*sizeof(float);
    v.shape.quant_sums=reinterpret_cast<std::int32_t *>(prepared);
    prepared+=sizes.columns/32*sizeof(std::int32_t);
  }

  auto normalise=[&](const float *weights,const float *input,float *out,
                      unsigned groups,unsigned width) {
    for(unsigned g=0;g<groups;++g) {
      float sum=0;
      for(unsigned j=0;j<width;++j) {
        const float value=input[g*width+j];
        sum=math::add(sum,math::mul(value,value));
      }
      const float factor=math::div(1.0f,math::sqrt(math::add(math::div(sum,float(width)),c.epsilon)));
      if(!std::isfinite(factor)) return false;
      for(unsigned j=0;j<width;++j)
        out[g*width+j]=math::mul(math::mul(input[g*width+j],factor),weights[j]);
    }
    return true;
  };
  auto linear=[&](unsigned index,const float *in0,const float *in1,float *out0,float *out1,
                   bool reuse=false) MK61_PREFILL_CODE -> ModelStatus {
    Tensor tensor_info{};
    if(!tensor(index,tensor_info)) return ModelStatus::IO;
    const auto &t=tensor_info;
    const bool lut=ex.lut8 && t.bits==4 && t.grid==256 && t.cols==128;
    auto kernel=ex.kernel==LinearKernel::SRAM?linear_batch_sram:linear_batch_flash;
    if(lut) kernel=ex.kernel==LinearKernel::SRAM?linear_batch_lut8_sram:linear_batch_lut8_flash;
    const float *inputs[]{in0,in1};
    float *outputs[]{out0,out1};
    for(unsigned i=0;i<2;++i) {
      auto &v=lanes[i];
      auto &shape=v.shape;
      if(!ex.reuse_activations || !reuse || shape.input!=inputs[i] || v.columns!=t.cols) {
        ++m.activation_preparations;
        v.lut_ready=false;
        for(unsigned g=0;g<t.cols/32;++g) {
          if(!quantize_int8_group(inputs[i]+32*g,const_cast<float *>(shape.activation_scales)[g],
                const_cast<std::int8_t *>(shape.quant)+32*g,
                const_cast<std::int32_t *>(shape.quant_sums)[g])) return ModelStatus::NUMERIC;
        }
      } else ++m.activation_reuses;
      if(lut) {
        if(v.lut_ready) ++m.lut8_reuses;
        else {
          auto *tables=reinterpret_cast<mk61ai_lut8x32 *>(const_cast<float *>(shape.lookup));
          for(unsigned g=0;g<4;++g) mk61ai_prepare_lut8x32(shape.quant+32*g,tables+g);
          ++m.lut8_preparations;v.lut_ready=true;
        }
      }
      v.columns=t.cols;shape.input=inputs[i];
      shape.columns=t.cols;shape.bits=t.bits;shape.grid=t.grid;
    }
    const unsigned weights=t.cols*t.bits/8, scales=t.cols/16;
    unsigned capacity=std::min<unsigned>(sizes.rows,sizes.tile/(t.cols*9/16));
    if(sizes.rows==28) capacity&=~1U;
    if(!capacity) return ModelStatus::FORMAT;
    struct Tile { std::uint8_t *data;unsigned first=0,count=0; };
    Tile tiles[2]={{tile_base},{tile_base+sizes.tile}};
    unsigned r=0;
    const bool prefetch=ex.prefetch && package_.read_begin && package_.read_finish;
    bool pending=false;
    const auto load=[&](Tile &tile,bool async) -> ModelStatus {
      tile.count=0;
      if(r==t.rows) return ModelStatus::OK;
      if(!alive()) return ModelStatus::CANCELLED;
      tile.first=r;tile.count=std::min<unsigned>(capacity,t.rows-r);r+=tile.count;
      const block_io::ReadSpan spans[]{
        {t.data+tile.first*weights,tile.data,tile.count*weights},
        {t.scale+tile.first*scales,tile.data+tile.count*weights,tile.count*scales}};
      const auto started=stamp();
      if(async && package_.read_begin(package_.context,spans,2)) {
        pending=true;
        ++m.prefetches;
        m.prefetched_bytes+=tile.count*(weights+scales);
      } else for(const auto &span:spans) {
        if(!read(span.offset,span.destination,span.bytes)) return ModelStatus::IO;
      }
      m.read_us+=stamp()-started;
      return ModelStatus::OK;
    };
    auto status=load(tiles[0],false);
    if(status!=ModelStatus::OK) return status;
    for(unsigned active=0;tiles[active].count;active^=1) {
      const Tile &here=tiles[active];
      auto &next=tiles[active^1];
      if(prefetch && (status=load(next,true))!=ModelStatus::OK) return status;
      const auto matmul_started=stamp();
      LinearBatch jobs[2]={lanes[0].shape,lanes[1].shape};
      for(unsigned i=0;i<2;++i) {
        jobs[i].rows=here.count;jobs[i].weights=here.data;
        jobs[i].scales=here.data+here.count*weights;
        jobs[i].output=outputs[i]+here.first;
      }
      const bool submitted=ex.submit && ex.join && ex.submit(ex.context,kernel,&jobs[1]);
      kernel(&jobs[0]);
      if(submitted) {
        ex.join(ex.context);++m.worker_jobs;m.worker_rows+=here.count;
      } else kernel(&jobs[1]);
      m.matmul_us+=stamp()-matmul_started;
      if(pending) {
        const auto before=stamp();
        const bool ok=package_.read_finish(package_.context);
        pending=false;
        m.wait_us+=stamp()-before;
        if(!ok) return ModelStatus::IO;
      }
      for(unsigned i=0;i<2;++i) {
        if(jobs[i].status!=ModelStatus::OK) return jobs[i].status;
        for(unsigned j=0;j<here.count;++j) {
          std::uint32_t bits;
          std::memcpy(&bits,jobs[i].output+j,sizeof(bits));
          lanes[i].checksum=(lanes[i].checksum^bits)*16777619U;
        }
      }
      m.rows+=2*here.count;
      if(lut) m.lut8_rows+=2*here.count;
      if(!prefetch && (status=load(next,false))!=ModelStatus::OK) return status;
    }
    return ModelStatus::OK;
  };

  Tensor embedding{};
  if(!tensor(0,embedding)) return ModelStatus::IO;
  const unsigned e_bytes=embedding.cols*embedding.bits/8,e_scales=embedding.cols/16;
  for(unsigned i=0;i<2;++i) {
    if(i==1 && tokens[0]==tokens[1]) {
      std::memcpy(lanes[1].x,lanes[0].x,pair_hidden*sizeof(float));
      break;
    }
    alignas(4) std::uint8_t raw[pair_hidden*9/16];
    const unsigned id=tokens[i];
    if(!read(embedding.data+id*e_bytes,raw,e_bytes) ||
       !read(embedding.scale+id*e_scales,raw+e_bytes,e_scales)) return ModelStatus::IO;
    for(unsigned j=0;j<pair_hidden;++j) {
      const unsigned offset=e_bytes+2*(j/32);
      const float scale=half(std::uint16_t(raw[offset])|std::uint16_t(raw[offset+1])<<8);
      const unsigned u=tensor_code(raw,j,embedding.bits,embedding.grid&256);
      lanes[i].x[j]=((embedding.grid&1)?float(u)*(2.0f/float((1U<<embedding.bits)-1))-1.0f:
                     float(int(u)-8))*scale;
    }
  }

  float rotary[2][pair_head_width];
  if(!read(header_[26]+position_*pair_head_width*sizeof(float),rotary,sizeof(rotary)))
    return ModelStatus::IO;
  const unsigned lengths[]{position_+1,position_+2};
  constexpr unsigned kv_stride=2*pair_kv*sizeof(float);
  const auto *cached_norms=reinterpret_cast<const float *>(parameters_+descriptor_bytes()+rotary_bytes());
  auto &l=lanes[0];auto &r=lanes[1];
  for(unsigned layer=0;layer<c.layers;++layer) {
    const unsigned base=2+11*layer;
    const auto *norms=cached_norms+c.hidden+layer*layer_norm_values();
    for(auto &v:lanes)
      if(!normalise(norms,v.x,v.n,1,pair_hidden)) return ModelStatus::NUMERIC;
    auto status=linear(base+1,l.n,r.n,l.q,r.q);
    if(status==ModelStatus::OK) status=linear(base+2,l.n,r.n,l.kv,r.kv,true);
    if(status==ModelStatus::OK) status=linear(base+3,l.n,r.n,l.kv+pair_kv,r.kv+pair_kv,true);
    if(status!=ModelStatus::OK) return status;
    for(unsigned i=0;i<2;++i) {
      auto &v=lanes[i];
      if(!normalise(norms+pair_hidden,v.q,v.q,pair_heads,pair_head_width) ||
         !normalise(norms+pair_hidden+pair_head_width,v.kv,v.kv,pair_kv_heads,pair_head_width))
        return ModelStatus::NUMERIC;
      for(unsigned which=0;which<2;++which) {
        float *values=which?v.kv:v.q;
        for(unsigned h=0;h<(which?pair_kv_heads:pair_heads);++h)
          for(unsigned j=0;j<pair_head_width/2;++j) {
            float &a=values[h*pair_head_width+j],&b=values[h*pair_head_width+j+pair_head_width/2];
            const float old=a,cosine=rotary[i][2*j],sine=rotary[i][2*j+1];
            a=math::sub(math::mul(old,cosine),math::mul(b,sine));
            b=math::add(math::mul(b,cosine),math::mul(old,sine));
          }
      }
    }
    const auto attention_started=stamp();
    const unsigned offset=layer*c.context*kv_stride;
    // Both adjacent K/V rows are ready before the causal scans. The first
    // query never touches the second row; no earlier slot is written.
    if(!transfer(cache_,offset+position_*kv_stride,kv,2*kv_stride,true)) return ModelStatus::IO;
    auto *scores0=cursor;
    float *scores[]{scores0,second};
    auto *buffer=scores0+2*c.context;
    KVStream stream{cache_,buffer,pair_kv_tile,m,ex.batch_kv};
    if(ex.overlap_kv && position_>=127 && ex.batch_kv && cache_.read_begin && cache_.read_finish)
      stream.alternate=buffer+pair_kv_tile/sizeof(float);
    const float scale=math::div(1.0f,math::sqrt(float(pair_head_width)));
    for(unsigned group=0;group<pair_kv_heads;++group) {
      float maxima[2][2]={{-FLT_MAX,-FLT_MAX},{-FLT_MAX,-FLT_MAX}}, sums[2][2]{};
      for(unsigned phase=0;phase<2;++phase) {
        for(unsigned pos=0;pos<lengths[1];) {
          if(!alive()) return ModelStatus::CANCELLED;
          const unsigned at=offset+pos*kv_stride+(phase*pair_kv+group*pair_head_width)*sizeof(float);
          const unsigned remaining=lengths[1]-pos;
          const auto before=stamp();
          const auto *rows=stream.read(at,pair_head_width*sizeof(float),kv_stride,remaining);
          if(!rows) return ModelStatus::IO;
          const unsigned count=stream.rows;
          if(stream.alternate && remaining-count>1) stream.prefetch(at,pair_head_width*sizeof(float),kv_stride,remaining);
          m.attention_io_us+=stamp()-before;
          for(unsigned i=0;i<2;++i) {
            if(pos>=lengths[i]) continue;
            const unsigned limit=std::min(count,lengths[i]-pos);
            AttentionBatch jobs[2];
            for(unsigned head=0;head<2;++head) {
              const unsigned d=(2*group+head)*pair_head_width;
              auto *score=scores[i]+head*c.context+pos;
              jobs[head]={phase?nullptr:lanes[i].q+d,rows,phase?score:nullptr,
                          phase?lanes[i].n+d:score,limit,pair_head_width,scale,sums[i][head]};
            }
            attention_pair(jobs,2,ex,m);
            if(!phase) for(unsigned p=0;p<limit;++p) for(unsigned head=0;head<2;++head)
              maxima[i][head]=std::max(maxima[i][head],scores[i][head*c.context+pos+p]);
          }
          if(stream.staged_rows) {
            const auto before_wait=stamp();
            const bool ok=stream.wait();
            m.attention_io_us+=stamp()-before_wait;
            if(!ok) return ModelStatus::IO;
          }
          pos+=count;
        }
        if(!phase) for(unsigned i=0;i<2;++i) {
          const bool separate=lengths[i]>=128 && ex.parallel_softmax &&
              softmax_pair(scores[i],c.context,lengths[i],maxima[i],sums[i],ex);
          if(separate) ++m.softmax_worker_jobs;
          for(unsigned head=0;head<2;++head) {
            if(!separate) {
              SoftmaxJob softmax{scores[i]+head*c.context,lengths[i],maxima[i][head]};
              SoftmaxJob::run(&softmax);sums[i][head]=softmax.sum;
            }
            if(!std::isfinite(sums[i][head]) || sums[i][head]<=0) return ModelStatus::NUMERIC;
          }
          std::fill_n(lanes[i].n+2*group*pair_head_width,2*pair_head_width,0.0f);
        }
      }
    }
    m.attention_us+=stamp()-attention_started;

    if((status=linear(base+6,l.n,r.n,l.q,r.q))!=ModelStatus::OK) return status;
    for(auto &v:lanes) {
      for(unsigned j=0;j<pair_hidden;++j) v.x[j]=math::add(v.x[j],v.q[j]);
      if(!normalise(norms+pair_hidden+2*pair_head_width,v.x,v.n,1,pair_hidden)) return ModelStatus::NUMERIC;
    }
    if((status=linear(base+8,l.n,r.n,l.gate,r.gate))!=ModelStatus::OK) return status;
    if((status=linear(base+9,l.n,r.n,l.up,r.up,true))!=ModelStatus::OK) return status;
    FeedForwardActivation jobs[]={{l.gate,l.up,c.intermediate},{r.gate,r.up,c.intermediate}};
    const bool submitted=ex.submit && ex.join && ex.submit(ex.context,FeedForwardActivation::run,&jobs[1]);
    FeedForwardActivation::run(&jobs[0]);
    if(submitted) ex.join(ex.context);else FeedForwardActivation::run(&jobs[1]);
    if((status=linear(base+10,l.gate,r.gate,l.q,r.q))!=ModelStatus::OK) return status;
    for(auto &v:lanes)
      for(unsigned j=0;j<pair_hidden;++j) v.x[j]=math::add(v.x[j],v.q[j]);
  }

  m.layers_us=stamp()-start;
  m.checksum=lanes[1].checksum;
  if(checksums) {checksums[0]=lanes[0].checksum;checksums[1]=m.checksum;}
  position_+=2;
  return ModelStatus::OK;
}

#undef MK61_PREFILL_CODE
