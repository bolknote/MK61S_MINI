"""Wait for the closed audit, then package weights and run a frozen baseline."""
import fcntl
import json
import time

from run_experiment import run,BASE,SCRIPT


def main():
    root=BASE/'native-mixed-v1'
    lock=(root/'finish.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if(root/'finish.json').exists():return
    started=time.monotonic()
    while not(root/'complete.json').exists():
        status=json.loads((root/'status.json').read_text())
        if status['phase']=='failed':raise RuntimeError(status)
        if time.monotonic()-started>10800:raise TimeoutError('Main comparison did not finish')
        time.sleep(10)
    run('native-mixed-v1/export.log',SCRIPT+'native_export.py')
    run('native-mixed-v1/previous-3m.log',SCRIPT+'native_baseline.py')
    (root/'finish.json').write_text(json.dumps({'completed':True,'export_and_baseline_complete':True,
                                               'native_device_measured':False})+'\n')


if __name__=='__main__':main()
