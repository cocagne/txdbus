import os
import sys

from twisted.trial import unittest

import client_tests


# Only test against the native bus if it's available

if 'DBUS_SESSION_BUS_ADDRESS' in os.environ:
    orig_env = os.environ['DBUS_SESSION_BUS_ADDRESS']

    class NativeBusMixin (object):

        def _setup(self):
            os.environ['DBUS_SESSION_BUS_ADDRESS'] = orig_env

        def _teardown(self):
            pass
            
    
    # "Copy" the objects unit tests into this module
    m = sys.modules[ __name__ ]

    for k,v in client_tests.__dict__.iteritems():
        if isinstance(v, type) and issubclass(v, client_tests.ServerObjectTester) \
                    and v is not client_tests.ServerObjectTester:
            setattr(m, k, type(k, (NativeBusMixin, v, unittest.TestCase), dict()))


