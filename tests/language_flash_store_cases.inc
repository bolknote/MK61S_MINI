// Runs against the real C9 implementation and its NOR fault-injection model.
static void test_language_flash_store() {
  namespace lf=language_vm::flash;
  using namespace language_vm;
  fresh(512U*1024U);
  const u8 text[]="10 END\n";u16 source_id=program_store::INVALID_ID;
  assert(program_store::write_file(program_store::ROOT_ID,source_id,ProgramType::TINYBASIC,
      "source",text,sizeof(text)-1,&source_id));
  u32 original_stamp;assert(program_store::content_stamp(source_id,original_stamp));
  static_assert(sizeof(lf::Store)<1280,"C9 adapter must not retain a file-sized buffer");
  auto create=[&](lf::Store& store,u8 seed,u32 size) {
    auto io=store.io();assert(io.truncate(io.context,lf::IMAGE,0));
    lf::Writer output(io,lf::IMAGE);
    u8 page[lf::WRITE_BYTES];
    for(u32 at=0;at<size;at+=sizeof(page)) {
      for(unsigned i=0;i<sizeof(page);++i)page[i]=u8(seed+(at+i)*37U);
      if(!at) {
        memset(page,0,32);memcpy(page,"LBV2",4);page[4]=14;page[5]=1;page[6]=1;
        lf::dword(page+8,size);lf::dword(page+12,40);lf::word(page+16,sizeof(text)-1);lf::word(page+18,1);
        lf::dword(page+20,seed);lf::dword(page+28,size);
      }
      const unsigned n=size-at<sizeof(page)?size-at:sizeof(page);
      assert(output.write(at,page,n));
    }
    assert(output.flush());(void)store.input(size);
    return ValidatedImage{VALIDATED_MAGIC,size,40,sizeof(text)-1,size,1,1,0,Language::BASIC,true};
  };
  {
    lf::Store store(&source_id,12345);
    const auto certificate=create(store,11,200000);
    assert(store.publish(certificate));
    u32 current;assert(program_store::content_stamp(source_id,current) && current==original_stamp);
  }
  program_store::init();assert(program_store::ready());
  auto verify=[&](u8 expected) {
    lf::Store store(&source_id,12345);ValidatedImage certificate;
    assert(store.load(certificate) && certificate.size==200000);
    lf::Reader image(store.input(certificate.size));u8 bytes[257];
    for(u32 at:{255U,1021U,65533U,170000U,199743U}) {
      assert(image.read(at,bytes,sizeof(bytes)));
      for(unsigned i=0;i<sizeof(bytes);++i)assert(bytes[i]==u8(expected+(at+i)*37U));
    }
  };
  verify(11);
  // A private replacement interrupted by a power loss cannot replace the
  // current manifest. Faults also cover its metadata/GC writes.
  for(auto tear:{SPIFlash::Tear::Before,SPIFlash::Tear::Prefix,SPIFlash::Tear::Bits}) {
    {
      lf::Store store(&source_id,12345);auto io=store.io();
      assert(io.truncate(io.context,lf::IMAGE,0));
      u8 page[lf::WRITE_BYTES]={};SPIFlash::resetOperationCounts();
      SPIFlash::tearAfterOperations(0,tear);
      assert(!io.write(io.context,lf::IMAGE,0,page,sizeof(page)));
    }
    SPIFlash::clearFailure();program_store::init();assert(program_store::ready());verify(11);
  }
  // Actual capacity exhaustion, without a synthetic language quota.
  {
    lf::Store store(&source_id,12345);auto io=store.io();
    assert(io.truncate(io.context,lf::IMAGE,0));u8 page[lf::WRITE_BYTES]={};
    u32 count=0;while(count<1024 && io.write(io.context,lf::IMAGE,count*lf::WRITE_BYTES,page,sizeof(page)))++count;
    // The remaining capacity depends on C9 metadata. Check the physical
    // allocation failure and remaining inode capacity, rather than assuming
    // a particular count of free chunks.
    assert(count>0 && count<1024);
    assert(program_store::last_write_failure()==program_store::WriteFailure::RECORD);
    assert(program_store::used_nodes()<program_store::max_nodes());
  }
  program_store::init();assert(program_store::ready());verify(11);
  {
    lf::Store wrong(&source_id,12346);ValidatedImage certificate;assert(!wrong.load(certificate));
  }
  const u8 replacement[]="10 A=9\n";
  assert(program_store::write_file(program_store::ROOT_ID,source_id,ProgramType::TINYBASIC,
      "source",replacement,sizeof(replacement)-1));
  {
    lf::Store changed(&source_id,12345);ValidatedImage certificate;assert(!changed.load(certificate));
  }
  // Derived caches yield to another program when physical data space fills.
  // The active source and ordinary files must remain intact.
  fresh(512U*1024U);source_id=program_store::INVALID_ID;
  assert(program_store::write_file(program_store::ROOT_ID,source_id,ProgramType::TINYBASIC,
      "source",text,sizeof(text)-1,&source_id));
  {lf::Store first(&source_id,12345);const auto c=create(first,11,200000);assert(first.publish(c));}
  u16 second_id=program_store::INVALID_ID;
  assert(program_store::write_file(program_store::ROOT_ID,second_id,ProgramType::TINYBASIC,
      "second",text,sizeof(text)-1,&second_id));
  {lf::Store second(&second_id,12345);const auto c=create(second,22,100000);assert(second.publish(c));}
  {lf::Store first(&source_id,12345);ValidatedImage c;assert(!first.load(c));}
  {lf::Store second(&second_id,12345);ValidatedImage c;assert(second.load(c) && c.size==100000);}
  expect_text(source_id,text,sizeof(text)-1);expect_text(second_id,text,sizeof(text)-1);
  // Simulate loss of power before publication: automatic destructors never
  // ran, but the owner marker lets a later program reclaim orphaned pages.
  for(bool draft:{false,true}) {
    fresh(512U*1024U);source_id=program_store::INVALID_ID;
    assert(program_store::write_file(program_store::ROOT_ID,source_id,ProgramType::TINYBASIC,
        "source",text,sizeof(text)-1,&source_id));
    u16 abandoned_source=draft?program_store::INVALID_ID:source_id;
    alignas(lf::Store) u8 abandoned_memory[sizeof(lf::Store)];
    auto* abandoned=new(abandoned_memory) lf::Store(&abandoned_source,12345);
    (void)create(*abandoned,11,200000); // deliberately no publish/destructor
    program_store::init();assert(program_store::ready());second_id=program_store::INVALID_ID;
    assert(program_store::write_file(program_store::ROOT_ID,second_id,ProgramType::TINYBASIC,
        "second",text,sizeof(text)-1,&second_id));
    {lf::Store second(&second_id,12345);const auto c=create(second,22,100000);assert(second.publish(c));}
    expect_text(source_id,text,sizeof(text)-1);expect_text(second_id,text,sizeof(text)-1);
  }
  puts("C9 language pages: 200 KB, page/64-KB boundaries, reboot, torn writes, physical full, source/compiler cache identity and derived-cache eviction PASS");
}
