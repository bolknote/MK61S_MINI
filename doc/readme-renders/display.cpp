#include "calculator_face.hpp"
#include "builtin_font.hpp"
#include <cstdio>
int main(int argc,char**argv){
 if(argc!=2)return 2;FILE*f=fopen(argv[1],"w");if(!f)return 3;
 text_screen::Grid g;g.reset(2);const char*status="AUTO  DEG  105";for(const char*p=status;*p;++p)g.writeCodepoint(*p);g.setCursor(0,1);g.writeCodepoint('0');g.writeCodepoint('.');
 u8 frame[calculator_face::FRAME_BYTES]{};calculator_face::renderFrame(g,frame);
 fprintf(f,"{\"uc1609\":[");for(unsigned y=0;y<64;++y)for(unsigned x=0;x<192;++x)fprintf(f,"%s%u",x||y?",":"",(frame[(y/8)*192+x]>>(y%8))&1);fprintf(f,"],\"lcd1602\":[");
 const char*lines[]={"AUTO  DEG    105 ","0.              "};for(unsigned y=0;y<18;++y)for(unsigned x=0;x<96;++x){u8 rows[8]{};unsigned line=y/9,row=y%9;bool ink=false;if(line<2&&row<8&&x%6<5){builtin_font::copyRows5x8(lines[line][x/6],rows);ink=rows[row]&(1u<<(4-x%6));}fprintf(f,"%s%u",x||y?",":"",ink);}
 fprintf(f,"]}\n");fclose(f);
}
