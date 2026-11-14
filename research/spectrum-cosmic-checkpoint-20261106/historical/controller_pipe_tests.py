"""HOST only: real C trace, fixed windows, scope, cleanup and no state backup."""
import copy,importlib.util,json,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
ART=HERE.parent/'metrology-v2'
BUILD=HERE.parent/'optimization'
spec=importlib.util.spec_from_file_location('paced_controller',HERE/'run_pipe.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
STATUS=json.loads((HERE.parent.parent/'root-complete-main-merge-20261106/pico-production-validation/RUN/receipt.json').read_text())['status_after']
def plan():
    original={e['file'][:-4]:e for e in json.loads((HERE.parent/'fixtures.json').read_text())}
    files={'SPPIPE.APP':HERE/'profile-accepted-paced/SPPIPE.APP',
        'SP2C.Z80':HERE.parent/'COSMIC.Z80','SP2C.ULP':HERE.parent/'COSMIC.ULP'}
    games=[]
    for id,stem in [('SP2C','COSMIC')]:
        e=original[stem];games.append({k:e[k] for k in ('title','ulaplus','hud_roi_bytes','hud_signature')});games[-1]['id']=id
    h=HERE/'native-handoff-pipe-2483.json'
    platform=HERE/'platform-2483-equivalence.json';equivalence=json.loads(platform.read_text())
    evidence={'receipt':HERE.parent/'cosmic-ay-ab/AY-AB-HIL-r4/receipt.json','record':HERE.parent/'cosmic-ay-ab/AY-AB-HIL-r4/game-BASE.txt','app':HERE.parent/'cosmic-profile/audio-base/SPABASE.APP'}
    prior={'receipt':HERE.parent/'cosmic-ay-single/AY-SINGLE-HIL-r1/receipt.json','record':HERE.parent/'cosmic-ay-single/AY-SINGLE-HIL-r1/game-AY.txt'}
    matched={'receipt':HERE/'WAIT-V2-2483-HIL-r1/receipt.json','record':HERE/'WAIT-V2-2483-HIL-r1/game-WAIT.txt','app':HERE/'control/build/SPWAIT.APP'}
    return {'readiness':'fresh_handoff_verified','role':'spectrum-pipe-v2','folder':c.FOLDER,'uid':c.b.UID,'indexes':[0],'variants':[{'label':'PIPE','app':'SPPIPE.APP'}],
        'baseline':{'comparison':'sequential clean-start old717 BASE/AY descriptive;2483 PIPEv2',**{k:{'local':str(p),'sha256':c.sha(p)} for k,p in evidence.items()}},
        'prior_ay':{k:{'local':str(p),'sha256':c.sha(p)} for k,p in prior.items()},
        'matched_control':{k:{'local':str(p),'sha256':c.sha(p)} for k,p in matched.items()},
        'expected':{'build':'2483E8A7','crc':'22F8ED32','bytes':1537040},
        'measurement':{'warmup_frames':100,'window_frames':300,'windows':10,'timer_interval_uncertainty_us':1},
        'files':{n:{'local':str(p),'sha256':c.sha(p)} for n,p in files.items()},'games':games,
        'handoff':{'local':str(h),'sha256':c.sha(h)},'platform':{'local':str(platform),'sha256':c.sha(platform)},
        'pins':{str(p):c.sha(p) for p in [*files.values(),h,platform,*evidence.values(),*prior.values(),*matched.values(),
            *(Path(equivalence[k])/row['file'] for k in ('old_source','new_source') for row in equivalence['files'])]}}
def record(game):
    raw=(HERE/'presentation-wire.txt').read_bytes()
    stem='MANIC' if game['id']=='SP2M' else 'COSMIC';data=(HERE.parent/(stem+'-fixture.bin')).read_bytes()
    frame=b'SPBEGIN GAME\n'+b''.join(f'SPDATA {i:04X} '.encode()+data[i:i+32].hex().upper().encode()+b'\n' for i in range(0,7808,32))+b'SPEND\n'
    return re.sub(rb'SPBEGIN GAME\n.*?SPEND\n',lambda m:frame,raw,flags=re.S)

class Checks(unittest.TestCase):
    def test_real_c_trace_and_quantization_are_not_rounded_to_goal(self):
        r=c.measurements((ART/'host-paced-wire.txt').read_bytes())
        self.assertEqual(len(r['windows']),10);self.assertEqual(r['steady']['frames'],3000)
        self.assertLess(r['steady']['mhz'],3.5)
        self.assertLess(r['steady']['timer_lower_mhz'],3.5);self.assertGreater(r['steady']['timer_upper_mhz'],3.5)
        self.assertFalse(r['strict_3_5_lower_bound_reached'])
    def test_no_window_can_be_omitted_reordered_or_rewritten(self):
        raw=(ART/'host-paced-wire.txt').read_bytes();rows=re.findall(rb'SPWIN [^\n]*\n',raw)
        for bad in [raw.replace(rows[0],b'',1),raw.replace(rows[1],rows[0],1),raw+rows[0],
                    raw.replace(b'frames=300 ',b'frames=299 ',1),raw.replace(b'done=1',b'done=0')]:
            with self.assertRaises(c.Hold):c.measurements(bad)
        altered=re.sub(rb'(SPWIN n=0[^\n]* wall=)(\d+)',lambda m:m[1]+str(int(m[2])+100).encode(),raw,count=1)
        with self.assertRaises(c.Hold):c.measurements(altered)
    def test_scope_files_firmware_and_fixed_duration_before_io(self):
        good=plan();c.validate_plan(good)
        for kind in ('folder','files','expected','measurement','hash'):
            bad=copy.deepcopy(good)
            if kind=='folder':bad['folder']='/foreign'
            elif kind=='files':bad['files']['foreign.APP']=bad['files']['SPPIPE.APP']
            elif kind=='expected':bad['expected']['crc']='00000000'
            elif kind=='measurement':bad['measurement']['windows']=9
            else:bad['files']['SP2C.Z80']['sha256']='0'*64
            with patch.object(c.b.SpectrumGate,'native',side_effect=AssertionError('Device I/O forbidden')):
                with self.assertRaises(c.Hold):c.validate_plan(bad)
    def test_cleanup_only_owned_temporary_targets_without_backups(self):
        commands=[]
        class Port:
            def command(self,line):
                commands.append(line)
                return 'f\t16384\t48.rom\r\nf\t12345\tSPECTRUM.APP\r\nmk61> ' if line.startswith('ls ') else 'OK'
        self.assertEqual(set(c.cleanup_files(Port(),c.TEMP)),c.TEMP)
        self.assertEqual(len(commands),len(c.TEMP)+1)
        with self.assertRaises(c.Hold):c.cleanup_files(Port(),{'SPECTRUM.APP'})
        self.assertFalse(any('backup' in command or 'restore' in command for command in commands))
    def test_cleanup_rejects_plain_error_and_remaining_owned_file(self):
        for listing in ('ERROR\r\nmk61> ','f\t10\t48.rom\r\nf\t10\tSPECTRUM.APP\r\nf\t10\tSPPIPE.APP\r\nmk61> '):
            class P:
                def command(self,line):return listing if line.startswith('ls ') else 'OK'
            with self.assertRaises(c.Hold):c.cleanup_files(P(),{'SPPIPE.APP'})
    def test_foreign_or_unopened_normal_app_gets_no_escape(self):
        for path in ('/foreign.APP',c.FOLDER+'/SPECTRUM.APP'):
            class P:
                def status(self):return re.sub(r'(?m)^SERVICE=[^\r\n]*','SERVICE=VIEWER SOURCE=0 DIRTY=0 PATH=['+path+'] RESULT=[APP finished; Enter]',STATUS)
                def send(self,x):self.sent.append(x)
                def wire(self,x):self.sent.append(x)
                def pump(self,x):pass
            p=P();p.sent=[]
            with self.assertRaises(c.Hold):c.Port.native_return(p,0)
            self.assertEqual(p.sent,[])
    def test_actual_game_huds_still_match(self):
        for game in plan()['games']:
            data=c.previous.framebuffer(record(game));self.assertEqual(c.previous.scene_signature(data,game),game['hud_signature'])
    def test_full_profile_never_writes_ordinary_or_old_state(self):
        files={'unrelated.trd':b'untouched','48.rom':b'rom','SPECTRUM.APP':b'old'};commands=[];order=[];prepared=[False];j=plan()
        handoff=json.loads(Path(j['handoff']['local']).read_text())
        class Port:
            def __init__(self,g):self.g=g;self.text=bytearray();self.binding=handoff['native_binding'];self.active=False
            def __enter__(self):self.g.final['native_binding']=self.binding;return self
            def __exit__(self,*args):self.g.final.update(cdc_descriptor_closed=True,port_close_errors=[])
            def status(self):
                return STATUS.replace('RUNTIME=NONE','RUNTIME=APP').replace('APP_EXTERNAL_BYTES=0','APP_EXTERNAL_BYTES=1892352') if self.active else STATUS
            def commands(self):pass
            def command(self,line):
                commands.append(line)
                if line=='identity':return 'UID='+c.b.UID
                if line=='prof heap':return 'HEAP_FREE=104368 HEAP_FREE_BLOCKS=1 HEAP_TOP=104368'
                if line=='fsput cancel':return 'OK'
                if line.startswith('ls '):return ''.join('f\t10\t'+name+'\r\n' for name in files)+'mk61> '
                name=line.rsplit('/',1)[-1][:-1]
                if line.startswith('rm '):files.pop(name,None);return 'OK'
                if line.startswith('fsget '):assert name not in files;return '@MKC:ERROR GET_NOT_FOUND\r\n'
                raise AssertionError('Unexpected state/inventory command: '+line)
            def open_app(self,name):
                order.append(('open',name))
                if not prepared[0] and 'SP2C.Z80' in files:raise c.Hold('HOST allocation-order model: fixture before native APP preflight')
                prepared[0]=True;self.active=True;self.text.extend(b'SPMENU Spectrum 0/10 xip=1 [Start machine]\n')
            def native_return(self,physical):self.active=False;return STATUS
            def open_fixture(self,game):self.text.extend(record(game))
            def menu(self,start):pass
            def pump(self,seconds):pass
            def wire(self,code):pass
            def match(self,*args,**kwargs):pass
            def pause(self):pass
            def save(self,name):self.text.clear()
        class Gate:
            def cleanup(self):pass
            def noholders(self,binding):self.checked=True
        with tempfile.TemporaryDirectory() as out:
            g=Gate();g.j=j;g.final={};g.out=Path(out)
            def write(p,path,data):
                name=path.rsplit('/',1)[-1];order.append(('write',name));files[name]=data
            with patch.object(c,'Port',Port),patch.object(c.b,'write_file',side_effect=write):c.run(g)
        self.assertLess(order.index(('open','SPPIPE.APP')),order.index(('write','SP2C.Z80')))
        self.assertEqual(set(files),{'48.rom','unrelated.trd','SPECTRUM.APP'});self.assertEqual(files['unrelated.trd'],b'untouched')
        self.assertEqual(files['SPECTRUM.APP'],b'old');self.assertTrue(g.final['profiling_overhead_present']);self.assertFalse(g.final['previous_state_backup'])
        self.assertFalse(g.final['previous_state_restoration']);self.assertEqual(g.final['lease'],'released');self.assertEqual([v['variant'] for v in g.final['variants']],['PIPE'])
        self.assertFalse(any(x.split(' ')[0] in {'reg','stk','hout','pwd','alarm','clock'} for x in commands))
        self.assertEqual([x for x in commands if x.startswith('ls ')],[f'ls "{c.FOLDER}"'])
    def test_hold_still_proves_close_and_noholders(self):
        g=type('Gate',(),{'final':{'cdc_descriptor_closed':True,'port_close_errors':[],'native_binding':{},'cleanup_native_verified':True},'noholders':lambda self,x:None})()
        with patch.object(c,'run_port',side_effect=c.Hold('fixture failure')):
            with self.assertRaises(c.Hold):c.run(g)
        self.assertEqual(g.final['lease'],'released')
    def test_audio_details_and_duplicate_rejection(self):
        raw=(HERE.parent/'cosmic-profile/host-audio-stages.txt').read_bytes()
        d=c.details(raw);self.assertEqual(d['audio']['samples'],1)
        self.assertEqual(d['audio']['min_lead_tstates'],-136)
        for bad in (raw+raw,raw.replace(b'SPAUDIO ',b'OTHER ',1),raw.replace(b'maxlead=-136',b'maxlead=-300')):
            with self.assertRaises(c.Hold):c.details(bad)
    def test_variants_cannot_be_omitted_or_reordered(self):
        j=plan()
        for variants in [[],j['variants']+[j['variants'][0]],[{'label':'BASE','app':'SPPIPE.APP'}]]:
            bad=copy.deepcopy(j);bad['variants']=variants
            with self.assertRaises(c.Hold):c.validate_plan(bad)
    def test_draft_rejected_before_device_io(self):
        j=plan();j["readiness"]="stale_handoff_no_GO"
        with patch.object(c.b.SpectrumGate,"native",side_effect=AssertionError("No device I/O")):
            with self.assertRaises(c.Hold):c.validate_plan(j)
    def test_exact_event_counter_report_is_required(self):
        raw=b'SPSOUND late=2 wholemaxlate=280 wholemaxdeficit=500\n'
        self.assertEqual(c.sound_details(raw)['sound']['late_events'],2)
        for bad in [b'',raw+raw,raw.replace(b'280',b'2147483648')]:
            with self.assertRaises(c.Hold):c.sound_details(bad)
    def test_real_c_presentation_and_work_windows(self):
        raw=(HERE/'presentation-wire.txt').read_bytes();r=c.pipeline_details(raw)
        self.assertEqual(r['display']['accepted'],3001);self.assertEqual(r['display']['accepted_wall_us'],61440068)
        self.assertEqual(r['display']['windows'][0]['min_interval_us'],20378)
        self.assertEqual(r['display']['windows'][9]['max_late_us'],202)
        self.assertEqual(r['executed']['cycles'],215040000);self.assertEqual(r['executed']['max_ahead_tstates'],13977)
        for token in (b'SPWORK ',b'SPEXEC ',b'SPPRES ',b'SPDISPLAY '):
            row=re.search(token+rb'[^\n]*\n',raw)[0]
            for bad in (raw+row,raw.replace(row,b'',1)):
                with self.assertRaises(c.Hold):c.pipeline_details(bad)
    def test_invalid_actual_phase_or_missing_accepted_attempt_rejected(self):
        raw=(HERE/'presentation-wire.txt').read_bytes()
        for bad in (raw.replace(b'phase=14000/14000',b'phase=14000/14045',1),raw.replace(b'SPPRES 0 300 0',b'SPPRES 0 299 0',1),
                    raw.replace(b'SPDISPLAY 3001 3001',b'SPDISPLAY 3001 3000',1)):
            with self.assertRaises(c.Hold):c.pipeline_details(bad)
    def test_unclean_heap_holds_before_any_upload(self):
        class Gate:
            def cleanup(self):pass
            def noholders(self,b):pass
        class Port:
            def __init__(self,g):self.g=g;self.binding=json.loads(Path(g.j['handoff']['local']).read_text())['native_binding']
            def __enter__(self):self.g.final['native_binding']=self.binding;return self
            def __exit__(self,*a):self.g.final.update(cdc_descriptor_closed=True,port_close_errors=[])
            def status(self):return STATUS
            def commands(self):pass
            def native_return(self,p):return STATUS
            def command(self,line):
                if line=='identity':return 'UID='+c.b.UID
                if line=='prof heap':return 'HEAP_FREE=104368 HEAP_FREE_BLOCKS=2 HEAP_TOP=4840'
                if line=='fsput cancel':return 'OK'
                assert line==f'ls "{c.FOLDER}"';return 'f\t16384\t48.rom\nf\t33471\tSPECTRUM.APP\nmk61> '
        with tempfile.TemporaryDirectory() as out:
            g=Gate();g.j=plan();g.final={};g.out=Path(out)
            with patch.object(c,'Port',Port),patch.object(c.b,'write_file',side_effect=AssertionError('Upload before heap guard')):
                with self.assertRaises(c.Hold):c.run(g)
            self.assertEqual(g.final['lease'],'released');self.assertEqual(g.final['changed_sd_files'],{})
    def test_changed_platform_evidence_denied(self):
        j=plan();j['platform']['sha256']='0'*64
        with self.assertRaises(c.Hold):c.validate_plan(j)
if __name__=='__main__':unittest.main()
