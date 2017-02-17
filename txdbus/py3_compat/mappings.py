"""Python 3 compatibility wrappers for mappings.
"""

def iteritems(mapping):
    """mapping.iteritems() in py2, mapping.items() in py3
    """
    if hasattr(mapping, 'iteritems'):
        return mapping.iteritems()
    return mapping.items()

def itervalues(mapping):
    """mapping.itervalues() in py2, mapping.values() in py3
    """
    if hasattr(mapping, 'itervalues'):
        return mapping.itervalues()
    return mapping.values()

def keys(mapping):
    """mapping.keys(), converted to a list in py3 so things like .sort() work
    """
    ks = mapping.keys()
    if isinstance(ks, list):
        return ks
    return list(ks)
