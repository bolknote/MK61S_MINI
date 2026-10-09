// These assertions describe the previous product contracts, with IF replacing
// the deliberately removed full spelling BRANCH. Tests exercise the real
// adapter/editor/storage functions; only filesystem and UART are fixtures.
#include "focal_host_fixture.hpp"
#include "../code/focal.cpp"
#include <type_traits>
#include <string>

static int failures=0,checks=0;
#define CHECK(x) do{++checks;if(!(x)){++failures;fprintf(stderr,"FAIL %s:%d: %s\n",__func__,__LINE__,#x);}}while(0)
static void reset(){FocalNextReset();focal_host_fixture::reset();focal_host_fixture::serial.clear();}
static void edit(const char* before,const int* keys,unsigned count,const char* expected,int start=-1,int expected_cursor=-1) {
 char text[256];strcpy(text,before);
 text_editor::Buffer b={text,sizeof(text),(u16)strlen(text),(u16)(start<0?strlen(text):start),0,text_editor::Shift::NONE,{false,-1,0,0}};
 for(unsigned i=0;i<count;++i)(void)focal_editor::handle(b,"\n",keys[i],i*100);
 CHECK(!strcmp(text,expected));if(expected_cursor>=0)CHECK(b.cursor==expected_cursor);
}
static void keyboard_contract(){reset();const auto& k=keyboard_layout::active();
 struct Case{int key;const char* text;};
 const Case cases[]={{k.dot,"ASK "},{k.neg,"IF "},{k.power,"COMMENT "},{k.bx,"EXIT"},
  {k.mul,"FOR "},{k.degree,"GOTO "},{k.radian,"PRINT "},{k.x_to_p,"SET "},{k.ret,"RETURN"}};
 for(const auto& c:cases){int key[]={c.key};std::string result=std::string("1.10 ")+c.text;edit("1.10 ",key,1,result.c_str());}
 int forced[]={k.k,k.x_to_p};edit("1.10 SET X=",forced,2,"1.10 SET X=SET ");
 int after_number[]={k.degree};edit("1.10",after_number,1,"1.10 GOTO ");
 int old_integer_goto[]={k.degree};edit("10",old_integer_goto,1,"10 GOTO ");
 int integer_then_dot[]={k.dot};edit("1",integer_then_dot,1,"1.");
}
static void source_storage_contract(){reset();char source[256]="1.10 COMMENT ASK PRINT\n1.20 PRINT \"SET; IF\"\n1.30 FOR I=1,2; PRINT I\n1.40 IF(I) 1.50,,; EXIT\n1.50 EXIT";
 CHECK(store_edited_program(0,source,"SHORT"));
 CHECK(!strcmp(focal_host_fixture::last_write,"1.10 C ASK PRINT\n1.20 P \"SET; IF\"\n1.30 F I=1,2; P I\n1.40 B(I) 1.50,,; E\n1.50 E"));
 CHECK(!strcmp(programs[0].source,focal_host_fixture::last_write));
 // The editor must expand B to IF and must leave literals/comments intact.
 auto expand=&FocalTestExpandOperators;
 if(expand) {
  char restored[256];CHECK(expand(focal_host_fixture::last_write,restored,sizeof(restored)));
  CHECK(!strcmp(restored,source));
  char too_small[16]="unchanged";CHECK(!expand("1.10 C comment",too_small,sizeof(too_small)));
  CHECK(!strcmp(too_small,"unchanged"));
 }
 CHECK(!strncmp(FocalNextScreen(0),"FOCAL saved",11));
}
template<class Run>static FocalRunStatus status(Run run,int index) {
 if constexpr(std::is_void_v<decltype(run(index))>){run(index);return FocalRunStatus::UNAVAILABLE;}
 else return run(index);
}
static void public_api_contract(){reset();
 CHECK((std::is_same_v<decltype(&CompileFocal),bool(*)(const char*)>));
 CHECK((std::is_same_v<decltype(&RunFocal),FocalRunStatus(*)(int)>));
 char source[]="1.10 SET A=7\n1.20 EXIT";
 CHECK(CompileFocal(source));CHECK(FocalIsReady());CHECK(!strcmp(programs[0].name,"FOCAL0"));
 CHECK(!strcmp(focal_host_fixture::last_write,"1.10 S A=7\n1.20 E"));
 CHECK(status(&RunFocal,0)==FocalRunStatus::COMPLETED);CHECK(FocalNextVar(0)==7);
 CHECK(status(&RunFocal,-1)==FocalRunStatus::NOT_FOUND);
 reset();char bad[32]="BROKEN";CHECK(store_edited_program(0,bad,"DRAFT"));
 CHECK(status(&RunFocal,0)==FocalRunStatus::COMPILE_ERROR);
 reset();char math[64]="1.10 SET A=1/0\n1.20 EXIT";CHECK(CompileFocal(math));
 CHECK(status(&RunFocal,0)==FocalRunStatus::RUNTIME_ERROR);
}
static void control_contract(){reset();CHECK(FocalNextRun("1.10 D 2\n1.20 S A=99\n1.30 E\n2.10 G 3.10\n3.10 S A=5\n3.20 E")==0);CHECK(FocalNextVar(0)==5);
 reset();CHECK(FocalNextRun("1.10 D 2.10\n1.20 S A=5\n1.30 E\n2.10 G 3.10\n3.10 S A=99")==0);CHECK(FocalNextVar(0)==5);
 reset();CHECK(FocalNextRun("1.10 D 2,7\n1.20 S A=99\n1.30 E\n2.10 IF(ARG(1)) ,,3.10\n3.10 S A=5\n3.20 E")==0);CHECK(FocalNextVar(0)==5);
 // New functions retain their expression/argument frame across an internal jump.
 reset();CHECK(FocalNextRun("1.10 S A=3+CALL(2,7); E\n2.10 G 2.30\n2.20 R 99\n2.30 R ARG(1)*2")==0);CHECK(FocalNextVar(0)==17);
}
static void print_contract(){reset();CHECK(FocalNextRun("1.10 P 1,2\n1.20 E")==0);CHECK(!strncmp(FocalNextScreen(0),"1 2",3));
 reset();CHECK(FocalNextRun("1.10 P \"ONE\"\n1.20 P \"TWO\"\n1.30 E")==0);CHECK(!strncmp(FocalNextScreen(0),"TWO",3));
 reset();CHECK(FocalNextRun("1.10 P \"  A  \"\n1.20 E")==0);CHECK(!strncmp(FocalNextScreen(0),"  A  ",5));
}
static void editor_contract(){reset();const auto& k=keyboard_layout::active();
 int sine[]={k.alpha,k.digit[7]},root[]={k.alpha,k.sub},inverse[]={k.alpha,k.div};
 edit("1.10 SET A=X ",sine,2,"1.10 SET A=SIN(X) ");
 edit("1.10 SET A=AB",root,2,"1.10 SET A=AB");
 edit("A+B",inverse,2,"1/(A+B)");edit("X",sine,2,"SIN(X)");
 edit("1.10 PRINT X",root,2,"1.10 PRINT SQRT(X)");
 int left[]={k.left},right[]={k.right},erase[]={k.cx};
 edit("1.10 ASK X",left,1,"1.10 ASK X",9,5);edit("1.10 ASK X",right,1,"1.10 ASK X",5,9);
 edit("1.10 ASK X",erase,1,"1.10 X",7,5);
 edit("1.10 IF X",erase,1,"1.10 X",6,5);
}
static void transactional_storage_contract(){reset();char source[64]="1.10 S A=1";
 CHECK(!store_edited_program(0,source,""));CHECK(!strcmp(tb_last_error,"NAME?"));
 CHECK(!store_edited_program(-1,source,"OLD"));CHECK(!strcmp(tb_last_error,"SLOT?"));
 reset();CHECK(store_edited_program(0,source,"OLD"));
 const auto previous=programs[0];focal_host_fixture::write_ok=false;char changed[64]="1.10 S A=2";
 CHECK(!store_edited_program(0,changed,"NEW"));CHECK(!memcmp(&previous,&programs[0],sizeof(previous)));
 CHECK(focal_host_fixture::exists("OLD"));CHECK(!focal_host_fixture::exists("NEW"));
 CHECK(!strcmp(changed,"1.10 SET A=2"));
 // Legacy RAM selection has no stable inode; failure removing OLD must roll
 // the newly-created destination back without publishing new slot metadata.
 focal_host_fixture::write_ok=true;programs[0].store_id=0xFFFF;const auto legacy=programs[0];
 focal_host_fixture::refused_remove="OLD";CHECK(!store_edited_program(0,changed,"NEW"));
 CHECK(!memcmp(&legacy,&programs[0],sizeof(legacy)));CHECK(focal_host_fixture::exists("OLD"));CHECK(!focal_host_fixture::exists("NEW"));
}
static void diagnostics_contract(){reset();char name[32];tb_program_default_name(0,name,sizeof(name));CHECK(!strcmp(name,"FOCAL0"));
 focal_host_fixture::russian=true;char invalid[64]="1.10 S A=1";
 CHECK(!store_edited_program(0,invalid,""));CHECK(!strncmp(FocalNextScreen(0),M8("ИМЯ?"),strlen(M8("ИМЯ?"))));
 CHECK(CompileFocal(invalid));CHECK(!strncmp(FocalNextScreen(1),M8("ФОКАЛ0"),strlen(M8("ФОКАЛ0"))));
 reset();CHECK(FocalNextRun("1.10 S .X=1E100\n1.20 E")==3);CHECK(!strcmp(tb_last_error,"MK?"));
#ifdef MK61_FOCAL_TRACE
 reset();CHECK(FocalNextRun("1.10 S A=7\n1.20 P A\n1.30 E")==0);
 CHECK(strstr(focal_host_fixture::serial.output,"FOCAL")!=nullptr);
 CHECK(strstr(focal_host_fixture::serial.output,"EXEC")!=nullptr);
#endif
}
int main(){keyboard_contract();source_storage_contract();public_api_contract();control_contract();print_contract();editor_contract();transactional_storage_contract();diagnostics_contract();
 printf("focal compatibility: %d checks, %d failures\n",checks,failures);return failures?1:0;}
