import os
from twisted.trial import unittest
from twisted.internet import reactor

from txdbus import error, objects

class ObjectsTester(unittest.TestCase):

    def test_signature_validity(self):
        self.assertTrue( objects.isSignatureValid('foo', 'foo') )
        self.assertTrue( not objects.isSignatureValid('foo', None) )
        self.assertTrue( not objects.isSignatureValid('foo', 'bar') )
        self.assertTrue( not objects.isSignatureValid(None,  'foo') )
        self.assertTrue( objects.isSignatureValid(None, None) )

    def test_property_deletion(self):
        class Foo(object):

            p = objects.DBusProperty('foo')

        def d():
            f = Foo()
            del f.p

        self.assertRaises(AttributeError, d)
