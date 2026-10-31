#!/usr/bin/env python3
"""Bound one explicitly supplied subprocess; never discover hardware or retry.

This module has no physical entry point. The future accepted provider must
validate the fresh binding/Go first. HOST tests exercise these same process
and existing-lock primitives with ordinary local Python children.
"""
import errno
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

from prepare import pin


def fd_numbers():
    # Inventory this process only. No device/USB scan, port open or lsof.
    return sorted(int(x) for x in os.listdir('/dev/fd') if x.isdecimal())


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # POSIX EPERM proves no absence. A restricted process must HOLD,
        # never report a group/FD closure it could not establish.
        return True


class ExistingLease:
    """Attach to a coordinator-provided, already existing lock. Never create it."""
    def __init__(self, path, expected):
        self.path, self.expected, self.fd = Path(path), expected, None
        self.evidence = dict(path=str(self.path), created=False)

    def __enter__(self):
        if pin(self.path) != self.expected:
            raise ValueError('accepted lease pin changed')
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
        self.fd = os.open(self.path, flags)
        try:
            facts = os.fstat(self.fd)
            if not stat.S_ISREG(facts.st_mode) or facts.st_nlink != 1:
                raise ValueError('lease must be one regular non-symlink file')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if pin(self.path) != self.expected or os.stat(self.path).st_ino != facts.st_ino:
                raise ValueError('lease changed while acquiring lock')
            self.evidence.update(fd=self.fd, device=facts.st_dev, inode=facts.st_ino,
                                 owner_pid=os.getpid(), acquired=True, released=False)
        except BaseException:
            os.close(self.fd); self.fd = None
            raise
        return self

    def __exit__(self, *unused):
        del unused
        fd = self.fd
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        self.fd = None
        try:
            os.fstat(fd)
            closed = False
        except OSError as e:
            closed = e.errno == errno.EBADF
        self.evidence.update(released=True, fd_closed=closed,
                             same_inode=os.stat(self.path).st_ino == self.evidence['inode'])


def run_once(argv, output, *, cwd, env, timeout_seconds, max_log_bytes=1048576):
    """Run shell=False, capture actual PID/session/EXIT/reap/group and own FDs.

    A failure is returned as HOLD with preserved logs. Neither caller nor child
    is restarted. Only this child's process group may be terminated; an orphan
    in that group is itself a failure, even when the direct child exited zero.
    """
    if not (isinstance(argv, list) and argv and Path(argv[0]).is_absolute() and
            all(isinstance(x, str) and '\0' not in x for x in argv)):
        raise ValueError('an explicit absolute executable and argv array are required')
    if not 0 < timeout_seconds <= 3600 or not 1024 <= max_log_bytes <= 16 * 1048576:
        raise ValueError('finite process/log limits required')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    before = fd_numbers()
    start = time.monotonic()
    record = dict(argv=argv, cwd=str(Path(cwd).resolve()), shell=False, start_new_session=True,
                  close_fds=True, attempts=1, timeout_seconds=timeout_seconds,
                  log_limit_bytes=max_log_bytes, parent_pid=os.getpid(), parent_fds_before=before)
    process, reason = None, None
    stdout, stderr = output / 'stdout.bin', output / 'stderr.bin'
    try:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            process = subprocess.Popen(argv, cwd=cwd, env=env, shell=False,
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True, close_fds=True)
            record['pid'] = process.pid
            record['process_group'] = os.getpgid(process.pid)
            record['session_id'] = os.getsid(process.pid)
            if record['process_group'] != process.pid or record['session_id'] != process.pid:
                reason = 'child did not enter its own process group/session'
            while process.poll() is None and reason is None:
                if time.monotonic() - start >= timeout_seconds:
                    reason = 'timeout'
                elif max(stdout.stat().st_size, stderr.stat().st_size) > max_log_bytes:
                    reason = 'log limit'
                else:
                    time.sleep(0.02)
            if reason is None and max(stdout.stat().st_size, stderr.stat().st_size) > max_log_bytes:
                reason = 'log limit'
            if reason is None and process.returncode != 0:
                reason = 'nonzero EXIT'
            if reason is None and group_exists(process.pid):
                # A zero-exit parent must not leave children holding a port.
                reason = 'process group survived direct-child EXIT'
    except BaseException as e:
        reason = reason or type(e).__name__ + ': ' + str(e)
    finally:
        if process is not None:
            if reason is not None:
                (output / 'FIRST_FAULT.json').write_text(json.dumps(dict(reason=reason, pid=process.pid, retries=0)) + '\n')
            def signal_own_group(sig):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                except PermissionError as e:
                    record.setdefault('signal_errors', []).append(str(e))
                    # Reap the direct child even if the sandbox forbids a
                    # group signal. This does not prove descendant closure.
                    if process.poll() is None:
                        process.send_signal(sig)
            if reason is not None and group_exists(process.pid):
                record['TERM_sent_to_own_group'] = True
                signal_own_group(signal.SIGTERM)
                deadline = time.monotonic() + 0.25
                while group_exists(process.pid) and time.monotonic() < deadline:
                    process.poll()
                    time.sleep(0.01)
                if group_exists(process.pid):
                    record['KILL_sent_to_own_group'] = True
                    signal_own_group(signal.SIGKILL)
            try:
                record['EXIT'] = process.wait(timeout=2)
                record['reaped'] = True
            except subprocess.TimeoutExpired:
                record['reaped'] = False
                reason = reason or 'direct child not reaped'
            deadline = time.monotonic() + 2
            while group_exists(process.pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            record['group_gone'] = not group_exists(process.pid)
            if not record['group_gone']:
                reason = reason or 'owned process group remains'
        record.update(status='HOLD_FIRST_FAULT' if reason else 'PASS_PROCESS_EXIT', first_fault=reason,
                      elapsed_HOST_seconds=time.monotonic() - start,
                      parent_fds_after=fd_numbers(), logs=[pin(x) for x in (stdout, stderr) if x.exists()],
                      physical_timing_claim=False)
        (output / 'PROCESS.json').write_text(json.dumps(record, indent=2) + '\n')
    return record
