"""Transport-only recovery: serialize duplicate HTTP cache keys across threads.

    The frozen request payload, prompts, policies and model sources are unchanged.
    Raw/mechanical start with identical prompts, so duplicate requests must not
    race when committing one cache file. Completed episodes are never replaced.
"""
import argparse
import collections
import hashlib
import threading
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('protocol',choices=['ar','as']);a=p.parse_args()
    import ar_run
    if a.protocol=='as':import as_run
    Original=ar_run.Teacher

    class SafeTeacher(Original):
        def __init__(self):
            super().__init__()
            self.key_locks={}
            self.locks_guard=threading.Lock()

        def one(self,prompt,forced):
            key=(prompt,forced)
            with self.locks_guard:
                lock=self.key_locks.setdefault(key,threading.Lock())
            with lock:
                return super().one(prompt,forced)

    ar_run.Teacher=SafeTeacher
    ar_run.write(ar_run.ROOT/'teacher'/'transport-recovery.json',
                 {'unix':time.time(),'fix':'serialize identical cache keys; prevent shared .tmp rename race',
                  'wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'frozen_prompts_models_payloads_policy_unchanged':True,'completed_episodes_replaced':False})
    ar_run.run('teacher')


if __name__=='__main__':main()
