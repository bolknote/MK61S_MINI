"""Build isolated ELITE experiments; production sources are never edited."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path('/Users/bolk/Projects/MK61S_MINI')
HERE = Path(__file__).resolve().parent


def sources(name):
    folder = HERE / name
    folder.mkdir(exist_ok=True)
    for file in (ROOT / 'tools/elite').glob('*.py'):
        shutil.copyfile(file, folder / file.name)
    return folder


def replace(folder, file, old, new):
    path = folder / file
    text = path.read_text()
    assert text.count(old) == 1, (file, old, text.count(old))
    path.write_text(text.replace(old, new))


def add_tails(folder):
    replace(folder, 'assembler.py', 'self.data_helpers = set()',
            'self.data_helpers = set()\n        self.data_tails = {}')
    replace(folder, 'assembler.py',
            'return DATA_END + (13 if bank in self.data_helpers else 0)',
            'return DATA_END + (13 if bank in self.data_helpers else 0) + len(self.data_tails.get(bank,b""))')
    replace(folder, 'assembler.py',
            'banks[b][:self.data_end(b)]=data_page(values,b in self.data_helpers)',
            'banks[b][:self.data_end(b)]=data_page(values,b in self.data_helpers)+self.data_tails.get(b,b"")')


def specialized(folder):
    add_tails(folder)
    replace(folder, 'game.py', 'a.data_helpers={24,25,27}',
            'a.data_helpers={24,25,27}\n    a.data_tails[28]=bytes(8)')
    replace(folder, 'economy.py',
            "m.ld('C').n(2).op('-').st(6).jz('drones_done').set(0,18).st(1).set(5,1)",
            "m.set(7,10006351).ld('C').n(2).op('-').st(6).jz('drones_done').set(0,18).st(1).set(5,1).set(7,10006751)")
    replace(folder, 'combat.py',
            "m.open_page(27).call('enemy_tick')",
            "m.open_page(27).far(0x53,28*112+50)\n    m.jump('resolved_damage')\n    m.label('carrier_resolve').call('enemy_tick')")
    replace(folder, 'combat.py',
            "m.label('enemy_hit_done').ld(1).ld('D').op('+').st('C').ld(6).st('B')",
            "m.label('enemy_hit_done').ld(1).ld('D').op('+').st('C').ld(6).st('B').op('ret')\n    m.label('resolved_damage')")
    # Shared carrier resolution is still the original simultaneous turn.
    # Pirate resolution skips the entire absent-drone transaction.
    replace(folder, 'combat.py',
            "m.label('won').visit(24,'reward')",
            "m.label('pirate_resolve').set('E',0).call('pirate_tick').visit(24,'weapon')\n    m.ld(4).raw(4).op('-').jnz('pirate_shot').ld('C').raw(2).op('/','int').st('C')\n    m.label('pirate_shot').ld(1).ld('C').op('-').max0().st(1).st('E').st('C').ld(6).st('B').set('D',0).op('ret')\n    m.label('won').visit(24,'reward')")
    replace(folder, 'combat.py', "m.label('enemy_tick').ld('D').st(4)",
            "m.label('enemy_motion').ld('D').st(4)")
    replace(folder, 'combat.py',
            "m.label('charge_ready').set('F',0).ld(1).jz('enemy_ready')",
            "m.label('charge_ready').op('ret')\n    m.label('enemy_tick').call('enemy_motion').set('F',0).ld(1).jz('enemy_ready')")
    replace(folder, 'combat.py',
            "    m.ld(0).raw(4).op('-').jnz('enemy_ready')\n", '')
    replace(folder, 'combat.py',
            "m.label('weapon_ready').op('ret')",
            "m.label('weapon_ready').op('ret')\n    m.label('pirate_tick').call('enemy_motion').set('F',0).ld(1).jz('pirate_ready').ld(7).st('E')\n    m.label('pirate_ready').jump('enemy_ready')")


def packed_drones(folder):
    replace(folder, 'economy.py',
            ".set(0,18).st(1).set(5,1)", ".set(0,360).set(5,1)")
    replace(folder, 'combat.py', "m.n(18).raw(0xB5).add(6,1)",
            "m.add(5,1).ld(5).st('B').call('packed_get').n(18).call('packed_set').add(6,1)")
    replace(folder, 'combat.py', "m.n(1).op('-').st('B').raw(0xDB).st('E').jz('drones_ready')",
            "m.n(1).op('-').st('B').call('packed_get').st('E').jz('drones_ready')")
    replace(folder, 'combat.py', "m.ld('C').op('-').max0().raw(0xBB).st('E').jnz('drones_ready').add(6,-1)",
            "m.ld('C').op('-').max0().call('packed_set').st('E').jnz('drones_ready').add(6,-1)")
    replace(folder, 'combat.py', ".page_bytes(28,0xDB,0x4D)",
            ".open_page(28).call('packed_get').st('D').close_page(28)")
    replace(folder, 'combat.py',
            "m.label('select_done').op('ret').end_page()",
            """m.label('select_done').op('ret').end_page()
    m=a.module(31,'packed drone hulls')
    # RB=index -> RB=19**index, X/RE=old hull. RC shot is preserved.
    # RA is scratch: the input handler sets the final view after this call.
    m.label('packed_get').n(19).ld('B').op('swap','pow').raw(0x0E,0,0x0A,5).op('+','int').st('B')
    m.ld(0).ld('B').op('/','int').st('A')
    m.n(19).op('/','int').n(19).op('*').ld('A').op('swap','-').st('E').op('ret')
    # X=new hull, RE=old, RB=power -> R0 updated, X=new hull.
    # The four freed numeric words remain available as persistent data.
    m.label('packed_set').st('A').ld('E').op('-').ld('B').op('*').ld(0).op('+').st(0).ld('A').op('ret')""")


def gates(folder):
    """Two generated gates share the original turn, without a second handler."""
    add_tails(folder)
    replace(folder,'game.py','a.data_helpers={24,25,27}',
            'a.data_helpers={24,25,27}\n    a.data_tails[28]=bytes(8)')
    replace(folder,'economy.py','for i in range(9):m.st(i)',
            'for i in range(7):m.st(i)\n    m.set(7,1052).st(8)')
    replace(folder,'economy.py',".set(0,18).st(1).set(5,1)",
            ".set(0,18).st(1).set(5,1).set(7,6351).set(8,6751)")
    replace(folder,'combat.py',"m.label('shot_ready').ld(5).st('D').visit(28,'drone_tick')",
            "m.label('shot_ready').ld(5).st('D').far(0x53,28*112+52)")
    replace(folder,'combat.py',
            "m.ld(0).raw(4).op('-').jnz('enemy_ready')\n    m.branch(0x5A,'enemy_ready').set(3,3).set('F',1)",
            "m.far(0x53,28*112+59)")
    replace(folder,'combat.py',"m.label('select_done').op('ret').end_page()",
            """m.label('select_done').op('ret').end_page()
    m=a.module(31,'generated drone gates')
    m.label('swarm_update').visit(28,'drone_tick').op('ret')
    m.label('carrier_launch').branch(0x5A,'carrier_launch_done').set(3,3).set('F',1)
    m.label('carrier_launch_done').op('ret')""")


def load(folder):
    sys.path[:0] = [str(folder), str(ROOT / 'tools')]
    for name in ('assembler', 'ui', 'economy', 'combat', 'game'):
        sys.modules.pop(name, None)
    return importlib.import_module('game'), importlib.import_module('assembler')


def block(items, first, last=None):
    start = next(i for i,v in enumerate(items) if v.kind=='label' and v.value==first)
    end = next((i for i,v in enumerate(items[start+1:],start+1)
                if (last and v.kind=='label' and v.value==last) or
                   (last is None and v.kind=='end_page')),len(items))
    return start, end, deepcopy(items[start:end])


def overlay(folder, game, assembler):
    a = game.create_game()
    a.data.update({6:[0]*9,15:[0]*9,31:[0]*9})
    price = next(m for m in a.modules if m.name=='prices')
    price.bank = 20
    start,end,port = block(price.items,'price_market')
    price.items[start:end] = [assembler.Item('label','price_market'),
                             assembler.Item('bytes',[0x1F,0x53,*assembler.bcd(31*112)]) ,
                             assembler.Item('bytes',[0x52])]
    enemies=next(m for m in a.modules if m.name=='enemies')
    enemies.bank=21
    start,end,battle = block(enemies.items,'enemy_tick','charge_ready')
    # The charge-ready label is the continuation after this return.
    battle.append(assembler.Item('label','charge_ready'))
    battle.append(assembler.Item('bytes',[0x52]))
    enemies.items[start:end]=[assembler.Item('label','enemy_tick'),
                              assembler.Item('bytes',[0x1F,0x53,*assembler.bcd(31*112)])]
    templates=[]
    for body in (port,battle):
        for item in body:
            if item.kind=='branch':item.force_far=True
        temp=assembler.Assembler()
        m=temp.module(31,'overlay kernel')
        m.items=body
        banks,info=temp.link()
        assert info['occupied_bytes']<=63 and set(banks)=={31},info
        templates.append((banks[31][:63],info['occupied_bytes']))
    # Ms-only swaps preserve every numeric register and the stack.
    def swaps(*banks):return [v for b in banks for v in (0x1F,0x56,b)]
    m=a.module(30,'overlay mode switches')
    m.label('overlay_battle').raw(*swaps(31,6,15,31)).op('ret')
    m.label('overlay_port').raw(*swaps(31,15,6,31)).op('ret')
    kernel=next(m for m in a.modules if m.name=='kernel')
    kernel.items[2:2]=[assembler.Item('bytes',swaps(6,31))]
    contacts=next(m for m in a.modules if m.name=='contacts')
    index=next(i for i,v in enumerate(contacts.items) if v.kind=='label' and v.value=='start_contact')
    contacts.items[index+1:index+1]=[assembler.Item('branch',0x53,'overlay_battle')]
    combat=next(m for m in a.modules if m.name=='combat')
    for label in ('won','escaped','lost'):
        i=next(i for i,v in enumerate(combat.items) if v.kind=='label' and v.value==label)
        combat.items[i+1:i+1]=[assembler.Item('branch',0x53,'overlay_port')]
    return a,templates


def rle(folder,game,assembler):
    a=game.create_game()
    values=[v for b in range(24,30) for v in a.data[b]]
    runs=[]
    for v in values:
        if runs and runs[-1][0]==v:runs[-1][1]+=1
        else:runs.append([v,1])
    stream=[v for run in runs for v in run]
    # Store the stream towards the end of the same data pages. The decoder
    # reads every source word before its bank is overwritten by the output.
    for b in range(24,30):a.data[b]=[0]*9
    # Keep value/count pairs together. With nine source words per page,
    # the last value would remain unread when output B28 is committed.
    for i,v in enumerate(stream):a.data[26+i//8][i%8]=v
    read=bytes.fromhex('56 55 DB 4C 55 56 52')
    for b in (26,28,29):a.data_tails[b]=read
    m=a.module(31,'RLE numeric bootstrap')
    m.label('rle_init').set('E',26*112+63).set('F',0).set('C',0)
    for bank in range(24,30):
        m.set(9,0).call('rle_fill').raw(0x55,0x1F,0x56,bank,0x55)
    m.op('ret')
    m.label('rle_fill').ld('C').jnz('rle_run')
    m.call('rle_read').st('D').call('rle_read')
    m.label('rle_run').ld('D').raw(0xB9).add('C',-1).add(9,1)
    m.ld(9).n(9).op('-').jnz('rle_fill').op('ret')
    m.label('rle_read').ld('F').st('B').raw(0x1F,0xAE).add('F',1).n(8).op('-').jnz('rle_read_ready')
    m.set('F',0).add('E',112)
    m.label('rle_read_ready').ld('C').op('ret')
    kernel=next(m for m in a.modules if m.name=='kernel')
    # RA/R9 are initialized by the normal title afterwards.
    kernel.items[2:2]=[assembler.Item('branch',0x53,'rle_init')]
    return a,runs


def build(name):
    folder=sources(name)
    if name=='specialized':specialized(folder)
    if name=='packed-drones':packed_drones(folder)
    if name=='gates':gates(folder)
    if name=='rle':add_tails(folder)
    game,assembler=load(folder)
    extras={}
    if name=='overlay':
        a,templates=overlay(folder,game,assembler)
        extras['template_bytes']=[n for _,n in templates]
    elif name=='rle':
        a,runs=rle(folder,game,assembler)
        extras['runs']=runs
        extras['stream_bytes']=len(runs)*14
    else:a=game.create_game()
    banks,info=a.link()
    game.check_layout(info)
    if name=='specialized':
        banks[28][63:71]=bytes([0x1F,0x51,*assembler.bcd(info['labels']['pirate_resolve']),
                              0x1F,0x51,*assembler.bcd(info['labels']['carrier_resolve'])])
    if name=='gates':
        banks[28][63:71]=bytes([0x1F,0x51,*assembler.bcd(info['labels']['swarm_update']),
                              0x1F,0x51,*assembler.bcd(info['labels']['carrier_launch'])])
    if name=='overlay':
        for bank,(template,_) in zip((6,15),templates):banks[bank][:63]=template
    raw=b''.join(banks.get(b,bytes(112)) for b in range(32))
    from program_pack import program_binary
    binary=program_binary(raw)
    (folder/'elite.bin').write_bytes(binary)
    (folder/'initial.raw').write_bytes(raw)
    (folder/'autoexec.m61').write_text('open? manual.md\nreinit\nload 0000 elite.bin\nrun\n')
    (folder/'manual.md').write_text('Experimental ELITE; no firmware changes.\n')
    info.update(variant=name,bin_bytes=len(binary),**extras)
    (folder/'map.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({k:v for k,v in info.items() if k not in ('labels','banks')}))


if __name__=='__main__':build(sys.argv[1])
