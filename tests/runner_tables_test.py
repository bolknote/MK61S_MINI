#!/usr/bin/env python3
"""Read actual loaded game tables and compare independent board/BFS rules."""
import sys
from runner_game_test import Game,BOARDS,MAPS,move,distance

def main():
 binary=sys.argv[1];count=0
 for number,board in enumerate(BOARDS,1):
  g=Game(binary,number)
  try:
   tables=MAPS[number-1]['tables']
   def check(name,index,expected,row=None,stride=None):
    nonlocal count
    command=f'eval 0 @RF {tables[name]} {index}'
    if row is not None:command+=f' {row} {stride}'
    s=g.send(command)
    assert not s['eval_failed'] and s['regs'][15]==expected,(number,name,index,row,expected,s['regs'])
    count+=1
   for hero in range(36):
    for direction,key in [('left',4),('right',6),('up',8),('down',2)]:check(direction,hero,move(board,hero,key))
    check('fall',hero,hero-12 if hero>=12 else hero)
    d=distance(board,hero)
    for enemy in range(37):
     expected=36 if enemy==36 else min([enemy,*[move(board,enemy,k) for k in (8,2,4,6)]],key=d.__getitem__)
     check('chase',enemy,expected,hero,37)
    for mask in range(8):
     collected=mask|sum(1<<n for n,tile in enumerate(board['gold']) if tile==hero)
     check('collect',hero,collected*36,mask*36,1)
     check('background_index',hero,2*(hero//12)+bool(mask&(1<<(hero//12))),mask*36,1)
  finally:g.close()
 print(f'Runner actual loaded tables: {count} independent movement, fall, shortest-path, gold and background entries PASS')
if __name__=='__main__':main()
