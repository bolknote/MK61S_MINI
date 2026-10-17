static void test_language_flash_compiler_on_c9() {
  using namespace language_vm;
  for(auto language:{Language::BASIC,Language::FOCAL}) for(bool wide:{false,true}) {
    const unsigned rows=wide?550:600;
    fresh(512U*1024U);std::string text=language==Language::BASIC?"1 GOTO 30000\n":"1.0 G 9.0\n";
    for(unsigned i=0;i<rows;++i) {
      char line[32];if(language==Language::BASIC)snprintf(line,sizeof(line),"%u ",i+2);
      else snprintf(line,sizeof(line),"%u.%u ",2+i/100,i%100);
      text+=line;
      const char* statement=language==Language::BASIC?"A=A+A+A+A+A+A+A":"S A=A+A+A+A+A+A+A";
      if(wide)for(unsigned j=0;j<5;++j) {if(j)text+=';';text+=statement;}
      else text+=language==Language::BASIC?"A=1":"S A=1";
      text+='\n';
    }
    text+=language==Language::BASIC?"30000 .RA=42;END\n":"9.0 S .RA=42;E\n";
    u16 id=program_store::INVALID_ID;
    const program_store::ProgramType type=language==Language::BASIC?ProgramType::TINYBASIC:ProgramType::FOCAL;
    assert(program_store::write_file(program_store::ROOT_ID,id,type,"large",(const u8*)text.data(),u16(text.size()),&id));
    struct Source {u16 id;u32 stamp;u16 maximum=0;} backing={id,0};assert(program_store::content_stamp(id,backing.stamp));
    alignas(8) uint8_t workspace[8192];memset(workspace,0xA5,sizeof(workspace));
    source::Reader input({&backing,[](void* raw,u16 at,u8* out,u16 n){
      auto& source=*(Source*)raw;u16 read=0;u32 current;
      if(n>source.maximum)source.maximum=n;
      return program_store::content_stamp(source.id,current) && current==source.stamp &&
        program_store::read_source_range_id(source.id,at,out,n,&read) && read==n &&
        program_store::content_stamp(source.id,current) && current==source.stamp;
    },u16(text.size())},workspace+flash::SOURCE_WINDOW_OFFSET,flash::SOURCE_WINDOW_BYTES);
    flash::Store store(&id,9876,nullptr,workspace+FLASH_COMPILER_WORKSPACE_SIZE);auto io=store.io();
    const auto compiled=compile_flash_source(language,input,io,true,workspace+FLASH_FRONTEND_BYTES);
    assert(backing.maximum==flash::SOURCE_WINDOW_BYTES);
    for(unsigned i=0;i<FLASH_FRONTEND_BYTES;++i)assert(workspace[i]==0xA5);
    for(unsigned i=COMPILER_WORKSPACE_SIZE;i<sizeof(workspace);++i)assert(workspace[i]==0xA5);
    // Acquiring WORKSPACE for the VM clears the old compiler prefix. The
    // borrowed page must be invalidated; retained values remain untouched.
    memset(workspace,0,COMPILER_WORKSPACE_SIZE);store.invalidate();
    if(compiled.error!=Error::NONE)fprintf(stderr,"C9 compile %u wide=%d: %s at %u/%u; write=%u\n",unsigned(language),wide,error_name(compiled.error),compiled.line,compiled.source_offset,unsigned(program_store::last_write_failure()));
    assert(compiled.error==Error::NONE && compiled.size>(wide?65536U:6144U));
    flash::Reader image(store.input(compiled.size));View view;
    assert(inspect_flash(image,io,view)==Error::NONE && view.lines==rows+2);
    State state={};Value variables[26]{},array[385]{},stack[MAX_STACK]{};double result=0;
    state.variables=variables;state.array=array;state.array_count=385;state.stack=stack;state.stack_capacity=MAX_STACK;
    Services services={};services.context=&result;
    services.reference=[](void* raw,bool write,u8,double& value){if(write)*(double*)raw=value;else value=*(double*)raw;return true;};
    services.event=[](void*,Event,const char*,u16,double&){return true;};
    assert(run(view,state,services,100).error==Error::NONE && result==42);
    const ValidatedImage certificate={VALIDATED_MAGIC,view.size,view.code,view.source_size,view.end,view.lines,view.stack,0,language,true};
    assert(store.publish(certificate));
    for(unsigned i=COMPILER_WORKSPACE_SIZE;i<sizeof(workspace);++i)assert(workspace[i]==0xA5);
  }
  puts("C9 compiler + VM: BASIC/FOCAL, 602 lines and >64-KB images, streamed source stamp survives index/image/verification writes PASS");
}
