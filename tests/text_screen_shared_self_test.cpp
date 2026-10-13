#include "text_screen.hpp"
#include <assert.h>
#include <initializer_list>
#include <stdio.h>

using namespace text_screen;
static void check_dirty(const Grid& grid) {
  bool dirty=false;
  for(u8 row=0;row<grid.rows();++row)dirty=dirty || grid.dirtyMask(row)!=0;
  assert(grid.anyDirty()==dirty);
}
static void dirty_geometry_cases() {
  for(u8 rows=1;rows<=MAX_ROWS;++rows)
    for(u8 cols=1;cols<=MAX_COLS;++cols) {
      Grid grid;grid.reset(rows,cols);check_dirty(grid);assert(!grid.anyDirty());
      grid.markAll();check_dirty(grid);
      for(u8 row=0;row<grid.rows();++row){grid.clearDirty(row);check_dirty(grid);}
      assert(!grid.anyDirty());
      for(u8 row=0;row<grid.rows();++row)
        for(u8 col=0;col<grid.cols();++col) {
          grid.markCell(col,row);check_dirty(grid);assert(grid.anyDirty());
          grid.clearDirty(row);check_dirty(grid);assert(!grid.anyDirty());
        }
      grid.markAll();grid.clearColumns(0xFFFF);check_dirty(grid);assert(!grid.anyDirty());
      // A previously wider/taller dirty surface must not leave hidden bits
      // outside the new visible range, including non-byte-aligned geometry.
      grid.markAll();grid.reshape(1,1);check_dirty(grid);grid.clearDirty(0);
      check_dirty(grid);assert(!grid.anyDirty());
      grid.reshape(rows,cols);check_dirty(grid);grid.clearColumns(0xFFFF);
      check_dirty(grid);assert(!grid.anyDirty());
    }
  Grid grid;u32 random=0x614D1U;
  for(unsigned n=0;n<20000;++n) {
    random=random*1664525U+1013904223U;
    const u8 row=(u8)((random>>8)%MAX_ROWS),col=(u8)((random>>16)%MAX_COLS);
    switch(random&7U) {
      case 0:grid.reshape((u8)(row+1),(u8)(col+1));break;
      case 1:grid.reset((u8)(row+1),(u8)(col+1));break;
      case 2:grid.clear();break;
      case 3:grid.markCell(col,row);break;
      case 4:grid.markAll();break;
      case 5:grid.clearDirty(row);break;
      case 6:grid.clearColumns((u16)(random>>12));break;
      default:grid.setCursor(col,row);grid.writeByte((u8)(random>>24));break;
    }
    check_dirty(grid);
  }
}
int main() {
  dirty_geometry_cases();
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
