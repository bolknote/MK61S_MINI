static void test_catalog_only_child_lookup() {
  fresh(512U*1024U);
  u16 folder,other;
  assert(program_store::create_directory(program_store::ROOT_ID,"MixedCase",program_store::INVALID_ID,&folder));
  assert(program_store::create_directory(program_store::ROOT_ID,"Other",program_store::INVALID_ID,&other));
  const u8 text[]="10 END\n";u16 text_id,basic_id,collision_a,collision_b;
  auto put=[&](u16 parent,ProgramType type,const char* name,u16& id,u16 preferred=program_store::INVALID_ID) {
    id=program_store::INVALID_ID;
    assert(program_store::write_file(parent,preferred,type,name,text,sizeof(text)-1,&id));
  };
  put(folder,ProgramType::TEXT,"Manifest",text_id);
  put(folder,ProgramType::TINYBASIC,"Manifest",basic_id);
  // These different full names have the same 16-bit folded C9 hash.
  put(folder,ProgramType::TEXT,"P0042",collision_a);
  put(folder,ProgramType::TEXT,"P0200",collision_b);
  char upper[32],lower[32];usize up=0,lo=0;
  const char* utf_upper="СЛОН";const char* utf_lower="слон";
  assert(mk8::from_utf8((const u8*)utf_upper,strlen(utf_upper),(u8*)upper,sizeof(upper)-1,up));upper[up]=0;
  assert(mk8::from_utf8((const u8*)utf_lower,strlen(utf_lower),(u8*)lower,sizeof(lower)-1,lo));lower[lo]=0;
  u16 cyrillic;put(folder,ProgramType::TEXT,upper,cyrillic);
  auto lookup=[&](u16 parent,bool directory,ProgramType type,const char* name,u16 expected) {
    const auto erased=SPIFlash::eraseCount();SPIFlash::resetOperationCounts();
    u16 id=123;assert(program_store::find_child(parent,directory,type,name,id) && id==expected);
    assert(SPIFlash::mutationOperations()==0 && SPIFlash::eraseCount()==erased);
  };
  lookup(program_store::ROOT_ID,true,ProgramType::TEXT,"mixedcase",folder);
  lookup(folder,false,ProgramType::TEXT,"mANIFEST",text_id);
  lookup(folder,false,ProgramType::TINYBASIC,"MANIFEST",basic_id);
  lookup(folder,false,ProgramType::TEXT,"p0042",collision_a);
  lookup(folder,false,ProgramType::TEXT,"P0200",collision_b);
  lookup(folder,false,ProgramType::TEXT,lower,cyrillic);
  lookup(other,false,ProgramType::TEXT,"Manifest",program_store::INVALID_ID);
  lookup(folder,true,ProgramType::TEXT,"Manifest",program_store::INVALID_ID);
  lookup(folder,false,ProgramType::FOCAL,"Manifest",program_store::INVALID_ID);
  lookup(folder,false,ProgramType::TEXT,"absent",program_store::INVALID_ID);
  for(const auto* invalid:{"","bad/name","0123456789012345678901234567890123"}) {
    u16 id=123;assert(!program_store::find_child(folder,false,ProgramType::TEXT,invalid,id) && id==program_store::INVALID_ID);
  }
  u16 id=123;assert(!program_store::find_child(folder,false,ProgramType::TEXT,nullptr,id) && id==program_store::INVALID_ID);
  id=123;assert(!program_store::find_child(text_id,false,ProgramType::TEXT,"Manifest",id) && id==program_store::INVALID_ID);
  id=123;assert(!program_store::find_child(program_store::max_nodes(),false,ProgramType::TEXT,"Manifest",id) && id==program_store::INVALID_ID);
  // Unlike the catalog-only path, the pre-existing USB lookup materializes
  // its stale NOR projection. Keep that API and result unchanged.
  const auto erased=SPIFlash::eraseCount();
  assert(program_store::fat_find_child(folder,false,ProgramType::TEXT,"manifest",id) && id==text_id);
  assert(SPIFlash::eraseCount()>erased);
  assert(program_store::move_rename(text_id,other,"Moved"));
  lookup(folder,false,ProgramType::TEXT,"Manifest",program_store::INVALID_ID);
  lookup(other,false,ProgramType::TEXT,"moved",text_id);
  assert(program_store::remove_id(text_id));
  lookup(other,false,ProgramType::TEXT,"Moved",program_store::INVALID_ID);
  put(folder,ProgramType::TEXT,"Reused",id,text_id);assert(id==text_id);
  lookup(folder,false,ProgramType::TEXT,"reused",text_id);
  lookup(other,false,ProgramType::TEXT,"Moved",program_store::INVALID_ID);
  // A failed physical read is not a successful missing-file result.
  SPIFlash::failReadsAfterOperations(0);id=123;
  assert(!program_store::find_child(folder,false,ProgramType::TEXT,"reused",id) && id==program_store::INVALID_ID);
  SPIFlash::clearFailure();lookup(folder,false,ProgramType::TEXT,"reused",text_id);
  program_store::init();assert(program_store::ready());
  lookup(folder,false,ProgramType::TEXT,"reused",text_id);
  puts("C9 catalog lookup: zero NOR mutations; casefold/M8/hash collisions/types/parents/move/inode reuse/I-O/reboot PASS");
}
