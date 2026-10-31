"""Real ROM adapter: clock and delayed LCD delivery, with no native-frame drain."""
import json,shutil,subprocess
from runner_screen_oracle import indicator
from hil_runner_classic import DIGITS
import runner_frame_campaign as helper

class Port:
 def __init__(self,payload,level,step,observer,out,binary):
  self.out=out;self.trace=[];self.frames=[];self.last=None;self.pending=[];self.observer=observer;self.key_edges=[];self.changes=[]
  folder=out/'payload';shutil.copytree(payload,folder)
  if level:(folder/'autoexec.m61').write_text(f'open level{level}.m61\n:done\nwait 30\nrun :done\n')
  self.native_error=(out/'native.stderr').open('w');self.child=subprocess.Popen([str(binary),str(folder)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.native_error,text=True)
  self.state=json.loads(self.child.stdout.readline());self.frames=[indicator(self.state['frame'])];self.last=list(self.state['frame']);self.sendcmd(f'step-ms {step}')
 def sendcmd(self,cmd):
  self.child.stdin.write(cmd+'\n');self.child.stdin.flush();line=self.child.stdout.readline();assert line,('native exit',self.child.poll());self.state=json.loads(line)
  self.trace.append(dict(command=cmd,state=self.state))
  masks=self.state['frame']
  if masks!=self.last:
   self.last=list(masks);self.pending.append((self.state['ms']+self.observer,list(masks)));self.changes.append(dict(ms=self.state['ms'],masks=list(masks),oracle=self.state['regs'][3:15],running=self.state['running']))
  while self.pending and self.pending[0][0]<=self.state['ms']:
   _,masks=self.pending.pop(0);self.frames.append(indicator(masks))
 def command(self,*a,**k):raise AssertionError('hidden CLI')
 def pump(self,seconds):
  target=self.state['ms']+round(seconds*1000)
  while self.state['ms']<target:self.sendcmd(f'observe {min(20,target-self.state["ms"])}')
 def send(self,kind,payload):
  assert kind==0x30;digit=DIGITS.index(payload[0]);self.key_edges.append(dict(ms=self.state['ms'],digit=digit,down=bool(payload[1]),latest=helper.decode(self.frames[-1],2)));self.sendcmd(('down' if payload[1] else 'up')+f' {digit:X}')
 def close(self):
  self.child.stdin.close();self.exit_code=self.child.wait(timeout=10);self.native_error.close()
