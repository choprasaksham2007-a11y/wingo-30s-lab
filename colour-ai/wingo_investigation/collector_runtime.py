"""Process-scoped idle-sleep prevention and a single collector writer on Windows."""
import ctypes
import os
from contextlib import contextmanager


@contextmanager
def collector_session(lock_path, set_execution_state=None):
    import msvcrt
    with lock_path.open('a+b') as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Collector already running; use View-Live-Collector.cmd.') from exc
        active = False
        try:
            if set_execution_state is None:
                set_execution_state = ctypes.windll.kernel32.SetThreadExecutionState
                set_execution_state.argtypes = [ctypes.c_uint]
                set_execution_state.restype = ctypes.c_uint
            active = bool(set_execution_state(0x80000001))
            if not active:
                raise OSError('Windows refused the idle-sleep prevention request.')
            print(f'Collector PID {os.getpid()}: idle sleep prevention active; screen may turn off. '
                  'Keep plugged in and lid open. Manual Sleep still suspends collection.', flush=True)
            yield
        finally:
            if active:
                set_execution_state(0x80000000)
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
