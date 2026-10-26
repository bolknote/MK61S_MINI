// Shared checked Q62 exp argument stage; no coefficient or error-bound changes.
  // The same certified residual polynomial covers finite results up
  // through overflow and gradual underflow. Far endpoints remain exact.
  if(argument.high>=(negative_argument?746U:710U)) M0_POW_EXP_RESULT(negative_argument?0:D::Infinity);
  const U p0=wide32(uint32_t(argument.low>>32),0xB8AA3B29U);
  const U p1=wide32(uint32_t(argument.high),0xB8AA3B29U)+(p0>>32);
  const uint32_t n=uint32_t((p1+(1U<<21))>>22);
  const U reduction=wide32(uint32_t(exp_step_high),n)+(U(uint32_t(exp_step_high>>32)*n)<<32);
  U r=argument.low-reduction-uint32_t(wide32(n,exp_step_low)>>32);
  int k=int(n);
  if(negative_argument) {r=U(0)-r;k=-k;}
  const bool negative=(r>>63)!=0;
  const U magnitude=negative?U(0)-r:r;
  // Protect the polynomial's certified domain independently of the segment
  // estimate. Opposing truncations keep split reduction error below
  // 1.001 Q64 units; certify_m0_exp_fast.py checks the complete interval.
  if(magnitude>UINT64_C(12912720851596686)) M0_POW_EXP_REJECT(); // 0.0007
  const U z=exp_high_square(magnitude)&((U(1)<<44)-1);
  const uint32_t t=uint32_t((magnitude+(1U<<21))>>22); // |r| in Q42
  // Evaluate r/6+r*r/24+r*r*r/120 in Q44; it still fits int32.
  // The combined coefficient error is <3 Q44 units. Including the fifth
  // term costs fewer wide products than the old Q40 fourth-degree path.
  const uint32_t linear=pow_exp_linear32(t);
  const uint32_t square=uint32_t((z+(1U<<22))>>23);
  const uint32_t quadratic=uint32_t(wide32(square+1,0xAAAAAAABU)>>33);
  const uint32_t cubic=(uint32_t(z>>32)*(t>>16)+(1U<<16))>>17;
  const uint32_t fifth=((cubic+7)*2185U)>>15;
  const int32_t tail=(negative?-int32_t(linear):int32_t(linear))+int32_t(quadratic)+
    (negative?-int32_t(fifth):int32_t(fifth));
  const uint32_t tail_magnitude=tail<0?uint32_t(-tail):uint32_t(tail);
  const U p=wide32(uint32_t(z),tail_magnitude);
  const U c=(wide32(uint32_t(z>>32),tail_magnitude)+(p>>32))>>12;
  const U delta=r+(z>>1)+(tail<0?U(0)-c:c);
  const unsigned index=unsigned(k)&511U;
  k=(k-int(index))/512;
  U q=exp_table[index];
  const bool below=(delta>>63)!=0;
  const U d=below?U(0)-delta:delta;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  // The rounded13-product specialization has error<=1/2+2^-15.
  const U correction=mk61_m0_pow_exp_table_product(q,d);
#else
  const U cross=wide32(uint32_t(q),uint32_t(d>>32))+
    wide32(uint32_t(q>>32),uint32_t(d));
  const U correction=wide32(uint32_t(q>>32),uint32_t(d>>32))+(cross>>32)+1;
#endif
  q=below?q-correction:q+correction;
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  unsigned error=(input_error<=129?3U:4U)+(input_error+1)/2;
#else
  unsigned error=4+(input_error+1)/2;
#endif
  if(error>=256) M0_POW_EXP_REJECT();
  if(q<(U(1)<<62)) {q<<=1;--k;error*=2;}
  if(k>1023) {
    // At exponent1024 the overflow midpoint is Q62 2^62-256.
    if(k>1024 || q-(U(1)<<62)+256>error) M0_POW_EXP_RESULT(D::Infinity);
    M0_POW_EXP_REJECT();
  }
  if(k<-1022) {
    if(k<-1075) {
      const U half=U(1)<<63;
      if(k<-1076 || (q<half && half-q>error)) M0_POW_EXP_ZERO();
    } else {
      const unsigned shift=unsigned(-k-1012);
      const U mask=(U(1)<<shift)-1,half=U(1)<<(shift-1),tail=q&mask;
      const U distance=tail>half?tail-half:half-tail;
      if(distance>error) {
        const U retained=q>>shift;
        M0_POW_EXP_RESULT(retained+U(tail>half || (tail==half && (retained&1))));
      }
    }
    M0_POW_EXP_REJECT();
  }
  const uint32_t rounding_tail=uint32_t(q)&1023U;
#ifdef M0_POW_EXP_FIRST_CELL
  const U cell=(U(k+1022)<<52)+(q>>10);
  if(uint32_t(rounding_tail-(512U-error))<=2*error) M0_POW_EXP_FIRST_CELL(cell);
  // A tie is inside the rejected enclosure (error>=3). Outside it,
  // the exact same RNE decision only needs this32-bit tail comparison.
  M0_POW_EXP_RESULT(cell+U(rounding_tail>512U));
#else
  if(uint32_t(rounding_tail-(512U-error))<=2*error) M0_POW_EXP_REJECT();
  const U rounded=(q+511+((q>>10)&1))>>10;
  M0_POW_EXP_RESULT((U(k+1022)<<52)+rounded);
#endif
