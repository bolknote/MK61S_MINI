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

static void test_language_flash_repeated_run_io() {
  namespace lf=language_vm::flash;
  using namespace language_vm;
  fresh(512U*1024U);
  const u8 source[]="10 END\n";u16 id=program_store::INVALID_ID;
  assert(program_store::write_file(program_store::ROOT_ID,id,ProgramType::TINYBASIC,
      "RUN",source,sizeof(source)-1,&id));
  {
    lf::Store store(&id,789);auto io=store.io();assert(io.truncate(io.context,lf::IMAGE,0));
    lf::Writer writer(io,lf::IMAGE);u8 page[lf::WRITE_BYTES];
    for(unsigned at=0;at<8192;at+=sizeof(page)) {
      for(unsigned i=0;i<sizeof(page);++i)page[i]=u8((at+i)*37U);
      if(!at) {
        memset(page,0,32);memcpy(page,"LBV2",4);page[4]=14;page[5]=1;page[6]=1;
        lf::dword(page+8,8192);lf::dword(page+12,40);lf::word(page+16,sizeof(source)-1);
        lf::word(page+18,1);lf::dword(page+28,8192);
      }
      assert(writer.write(at,page,sizeof(page)));
    }
    assert(writer.flush());(void)store.input(8192);
    assert(store.publish({VALIDATED_MAGIC,8192,40,sizeof(source)-1,8192,1,1,0,Language::BASIC,true}));
  }
  lf::PageCache<8192> cache;
  auto measure=[&](lf::ReadCache* shared) {
    // Materialize C9's lazily rebuilt FAT directory chains outside the
    // read-only RUN interval, including after the unrelated write below.
    {lf::Store warm(&id,789,nullptr,nullptr,shared);ValidatedImage image;assert(warm.load(image));}
    SPIFlash::resetOperationCounts();
    for(unsigned run=0;run<20;++run) {
      lf::Store store(&id,789,nullptr,nullptr,shared);ValidatedImage image;assert(store.load(image));
      auto io=store.io();u8 byte=0;
      for(unsigned jump=0;jump<16;++jump) {
        assert(io.read(io.context,lf::IMAGE,300,&byte,1) && byte==u8(300U*37));
        assert(io.read(io.context,lf::IMAGE,7400,&byte,1) && byte==u8(7400U*37));
      }
    }
    assert(SPIFlash::mutationOperations()==0);
    return SPIFlash::readOperations();
  };
  const unsigned uncached=measure(nullptr),cached=measure(&cache);
  fprintf(stderr,"Flash RUN page reuse: %u -> %u physical NOR reads\n",uncached,cached);
  assert(cached*4U<uncached);
  assert(measure(&cache)==0); // Ready RUN needs no NOR metadata/payload reads.
  // C9 writes invalidate shared frames, including metadata and inode reuse.
  const u8 other[]={'a','b','c'};
  assert(program_store::write(ProgramType::TEXT,"OTHER",other,sizeof(other)));
  assert(measure(&cache)<uncached/4U);
  // A mutation also invalidates the live Store's local copy, not just a
  // newly constructed Store. Direct updates here model an external C9 write.
  lf::Store live(&id,789,nullptr,nullptr,&cache);ValidatedImage image;assert(live.load(image));
  auto io=live.io();u8 value=0;
  assert(io.read(io.context,lf::IMAGE,7400,&value,1) && value==u8(7400U*37));
  char path[100];snprintf(path,sizeof(path),"/System/VMCache/Pages/%04X/Image0/00000007.bin",unsigned(id));
  program_store::Entry entry;
  assert(storage_path::resolve_file(program_store::ROOT_ID,path,ProgramType::MK61_BINARY,entry)==storage_path::Status::OK);
  u8 page[lf::WRITE_BYTES];u16 copied=0;
  assert(program_store::read_source_range_id(entry.id,0,page,sizeof(page),&copied) && copied==sizeof(page));
  page[7400%sizeof(page)]=0xA7;
  assert(program_store::write_file(entry.parent_id,entry.id,ProgramType::MK61_BINARY,entry.name,page,sizeof(page)));
  assert(io.read(io.context,lf::IMAGE,7400,&value,1) && value==0xA7);
  // An epoch-valid descriptor may skip metadata reads. Source edits and a
  // different compiler identity must therefore reject that descriptor too.
  {lf::Store changed_compiler(&id,790,nullptr,nullptr,&cache);
   ValidatedImage stale;assert(!changed_compiler.load(stale));}
  const u8 replacement[]="10 A=9\n";
  assert(program_store::write_file(program_store::ROOT_ID,id,ProgramType::TINYBASIC,
      "RUN",replacement,sizeof(replacement)-1));
  {lf::Store changed_source(&id,789,nullptr,nullptr,&cache);
   ValidatedImage stale;assert(!changed_source.load(stale));}
  puts("C9 Flash RUN: bounded pages survive Store replacement; source/compiler/epoch invalidation, exact bytes, no writes PASS");
}
