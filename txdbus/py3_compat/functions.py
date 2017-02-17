"""Compatibility layer for functions.
"""

def name(function):
    if hasattr(function, 'func_name'):
        return function.func_name
    return function.__name__
