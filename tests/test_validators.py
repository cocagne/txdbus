from twisted.trial import unittest

from txdbus import marshal, error

class InterfaceNameValidationTester(unittest.TestCase):

    def t(self, s):
        self.assertRaises(error.MarshallingError,
                          marshal.validateInterfaceName,
                          s)
    def test_1(self):
        self.t( 'oops' )

    def test_2(self):
        self.t('foo..bar')

    def test_3(self):
        self.t('.'.join([ 'a' + str(i) for i in range(0,200) ]))

    def test_4(self):
        self.t('.foo.bar')

    def test_5(self):
        self.t('1foo.bar')

    def test_6(self):
        self.t('foo.bar!')

    def test_7(self):
        self.t('foo.2bar')


class ObjectNameValidationTester (InterfaceNameValidationTester):

    def t(self, s):
        self.assertRaises(error.MarshallingError,
                          marshal.validateObjectPath,
                          s)

    def test_1(self):
        self.t('foo')

    def test_2(self):
        self.t('/foo/')

    def test_3(self):
        self.t('/foo//bar')

    def test_4(self):
        self.t('/foo~bar')

    def test_5(self):
        self.assertEquals(marshal.validateObjectPath('/foo/bar'), None)



class ErrorNameValidationTester (InterfaceNameValidationTester):

    def t(self, s):
        self.assertRaises(error.MarshallingError,
                          marshal.validateErrorName,
                          s)


class BusNameValidationTester(unittest.TestCase):

    def t(self, s):
        self.assertRaises(error.MarshallingError,
                          marshal.validateBusName,
                          s)
    def test_1(self):
        self.t( 'oops' )

    def test_2(self):
        self.t('foo..bar')

    def test_3(self):
        self.t('.'.join([ 'a' + str(i) for i in range(0,200) ]))

    def test_4(self):
        self.t('.foo.bar')

    def test_5(self):
        self.t('1foo.bar')

    def test_6(self):
        self.t('foo.bar!')

    def test_7(self):
        self.t('foo.2bar')


class MemberNameValidationTester(unittest.TestCase):

    def t(self, s):
        self.assertRaises(error.MarshallingError,
                          marshal.validateMemberName,
                          s)
    def test_1(self):
        self.t( '' )

    def test_2(self):
        self.t('f'*256)

    def test_3(self):
        self.t('1oops')

    def test_4(self):
        self.t('foo.bar')


