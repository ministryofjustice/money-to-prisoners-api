from functools import wraps
import threading

_lock = threading.RLock()


def synchronised(func):
    @wraps(func)
    def inner(*args, **kwargs):
        if _lock.acquire(timeout=10):
            response = func(*args, **kwargs)
            _lock.release()
            return response
        raise OSError('Cannot acquire lock')

    return inner
