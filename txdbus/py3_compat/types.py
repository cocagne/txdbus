"""Type adapters for python 3 compatibility.
"""

import sys

anystring = str
if sys.version[0] != '3':
    anystring = basestring
