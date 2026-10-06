#include "text_screen.hpp"
#include <assert.h>
#include <initializer_list>
#include <stdio.h>

using namespace text_screen;
int main() {
  for(u8 old_cols : {1, 2, 16, 47, 64})
    for(u8 old_rows : {1, 4, 10})
      for(u8 new_cols : {1, 2, 16, 47, 64})
        for(u8 new_rows : {1, 4, 10}) {
          Grid grid; grid.reset(old_rows,old_cols);
          for(u8 row=0;row<grid.rows();++row) {
            grid.setCursor(0,row);
            for(u8 col=0;col<grid.cols();++col) {
              const unsigned index=row*grid.cols()+col;
              if(index%3==0) grid.writeByte((u8)(index%8));
              else grid.writeCodepoint((u16)(0x400+index));
            }
          }
          grid.setCursor(grid.cols()-1,grid.rows()-1);
          const Grid saved=grid;
          grid.reshape(new_rows,new_cols);
          for(u8 row=0;row<grid.rows();++row)
            for(u8 col=0;col<grid.cols();++col) {
              const bool overlap=row<saved.rows() && col<saved.cols();
              assert(grid.cell(col,row)==(overlap?saved.cell(col,row):(u16)' '));
              assert(grid.cellIsCustom(col,row)==(overlap && saved.cellIsCustom(col,row)));
            }
          assert(grid.cursorX()==(saved.cursorX()<grid.cols()?saved.cursorX():grid.cols()-1));
          assert(grid.cursorY()==(saved.cursorY()<grid.rows()?saved.cursorY():grid.rows()-1));
          assert(grid.anyDirty());
        }
  Grid grid; grid.reset(10,64);
  grid.writeByte(3); grid.writeCodepoint(0x410);
  grid.reshape(1,2); grid.reshape(10,64);
  assert(grid.cell(0,0)==3 && grid.cellIsCustom(0,0) && grid.cell(1,0)==0x410);
  assert(grid.cell(0,1)==' ' && !grid.cellIsCustom(0,1));
  printf("text grid: in-place geometry/cursor/custom flags PASS, bytes=%zu\n",sizeof(Grid));
}
