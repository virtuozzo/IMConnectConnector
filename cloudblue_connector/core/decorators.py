# ******************************************************************************
# Copyright (c) 2020-2021, Virtuozzo International GmbH.
# This source code is distributed under MIT software license.
# ******************************************************************************
import functools
import logging

LOG = logging.getLogger("decorators")

MISSING = type('MissingValue', tuple(), dict())()


def once(f):
    """Cache result of a function first call"""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        rv = getattr(f, 'rv', MISSING)
        if rv is MISSING:
            f.rv = f(*args, **kwargs)
        return f.rv

    return wrapper


def memoize(f):
    """Cache result of a function call with parameters"""
    f.memory = {}

    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        x = None
        try:
            x = tuple(list(args) + [])
        except TypeError:
            LOG.exception('XXX')
        rv = f.memory.get(x, MISSING)
        if rv is MISSING:
            rv = f(self, *args, **kwargs)
            f.memory[x] = rv
        return rv

    return wrapper


def log_exception(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            LOG.exception('XXX')

    return wrapper
