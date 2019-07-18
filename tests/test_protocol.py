import struct

from twisted.trial import unittest

from txdbus import protocol


class TestTransport:
    def __init__(self):
        self.data = b''
        self.fds = []

    def sendFileDescriptor(self, fd):
        # twisted queues fds to be sent later
        self.fds.append(fd)

    def write(self, data):
        self.data += data
        return len(data)


class TestProtocol(protocol.BasicDBusProtocol):
    def __init__(self):
        self._receivedFDs = []
        self._toBeSentFDs = []
        self.transport = TestTransport()
        self.mcalls = []
        self.mrets = []
        self.merrs = []
        self.msigs = []

    def methodCallReceived(self, mcall):
        self.mcalls.append(mcall)

    def methodReturnReceived(self, mret):
        self.mrets.append(mret)

    def errorReceived(self, merr):
        self.merrs.append(merr)

    def signalReceived(self, msig):
        self.msigs.append(msig)


class Endian:
    LITTLE = ord('l')
    BIG = ord('B')


class MsgType:
    INVALID = 0
    METHOD_CALL = 1
    METHOD_RETURN = 2
    ERROR = 3
    SIGNAL = 4


class Flags:
    NONE = 0x0
    NO_REPLY_EXPECTED = 0x1
    NO_AUTO_START = 0x2
    ALLOW_INTERACTIVE_AUTHORIZATION = 0x4


class Version:
    ONE = 1


class DataType:
    INVALID = 0
    BYTE = ord('y')
    BOOLEAN = ord('b')
    INT16 = ord('n')
    UINT16 = ord('q')
    INT32 = ord('i')
    UINT32 = ord('u')
    INT64 = ord('x')
    UINT64 = ord('t')
    DOUBLE = ord('d')
    STRING = ord('s')
    OBJECT_PATH = ord('o')
    SIGNATURE = ord('g')
    ARRAY = ord('a')
    STRUCT_BEGIN = ord('(')
    STRUCT_END = ord(')')
    VARIANT = ord('v')
    DICT_ENTRY = ord('e')
    UNIX_FD = ord('h')


class HeaderField:
    INVALID = 0
    PATH = 1
    INTERFACE = 2
    MEMBER = 3
    ERROR_NAME = 4
    REPLY_SERIAL = 5
    DESTINATION = 6
    SENDER = 7
    SIGNATURE = 8
    UNIX_FDS = 9


def encode_signature(*data_types):
    data = bytearray(data_types)
    data.append(0)
    data.insert(0, len(data_types))
    return data


def align(align, offset):
    count = offset % align
    if not count:
        return b''
    return b'\x00' * (align - count)


def create_basic_method(path, member):
    """Creates raw D-Bus message` with `path` for method `member having no
    parameters
    """
    serial = 1
    path = path.encode()
    member = member.encode()

    headers = bytearray()
    headers.append(HeaderField.PATH)
    headers += encode_signature(DataType.OBJECT_PATH)
    headers += align(4, len(headers))
    headers += struct.pack('<I', len(path))
    headers += path
    headers.append(0)
    headers += align(8, len(headers))

    headers.append(HeaderField.MEMBER)
    headers += encode_signature(DataType.STRING)
    headers += align(4, len(headers))
    headers += struct.pack('<I', len(member))
    headers += member
    headers.append(0)

    body = bytearray()

    data = bytearray()
    data.append(Endian.LITTLE)
    data.append(MsgType.METHOD_CALL)
    data.append(Flags.NONE)
    data.append(Version.ONE)
    data += struct.pack('<I', len(body))
    data += struct.pack('<I', serial)
    data += struct.pack('<I', len(headers))
    data += headers
    data += align(8, len(data))
    data += body

    return bytes(data)


def create_one_unix_fd_method(path, member, fd_index):
    """Creates raw D-Bus message` with `path` for method `member having one
    UNIX file descriptor input parameter
    """

    serial = 1
    path = path.encode()
    member = member.encode()
    signature = bytearray([DataType.UNIX_FD])
    num_fds = 1

    headers = bytearray()
    headers.append(HeaderField.PATH)
    headers += encode_signature(DataType.OBJECT_PATH)
    headers += align(4, len(headers))
    headers += struct.pack('<I', len(path))
    headers += path
    headers.append(0)
    headers += align(8, len(headers))

    headers.append(HeaderField.MEMBER)
    headers += encode_signature(DataType.STRING)
    headers += align(4, len(headers))
    headers += struct.pack('<I', len(member))
    headers += member
    headers.append(0)
    headers += align(8, len(headers))

    headers.append(HeaderField.SIGNATURE)
    headers += encode_signature(DataType.SIGNATURE)
    headers += struct.pack('B', len(signature))
    headers += signature
    headers.append(0)
    headers += align(8, len(headers))

    headers.append(HeaderField.UNIX_FDS)
    headers += encode_signature(DataType.UINT32)
    headers += align(4, len(headers))
    headers += struct.pack('<I', num_fds)

    body = bytearray()
    body += struct.pack('<I', fd_index)

    data = bytearray()
    data.append(Endian.LITTLE)
    data.append(MsgType.METHOD_CALL)
    data.append(Flags.NONE)
    data.append(Version.ONE)
    data += struct.pack('<I', len(body))
    data += struct.pack('<I', serial)
    data += struct.pack('<I', len(headers))
    data += headers
    data += align(8, len(data))
    data += body

    return bytes(data)


class ProtocolTester(unittest.TestCase):
    def test_dataReceived_simple_method_call(self):
        p = TestProtocol()
        p._authenticated = True

        path = '/test/path'
        member = 'testMethod'
        data = create_basic_method(path, member)

        self.assertIsNone(p.dataReceived(data))
        self.assertEqual(len(p.mcalls), 1)
        self.assertEqual(p.mcalls[0].path, path)
        self.assertEqual(p.mcalls[0].member, member)
        self.assertIsNone(p.mcalls[0].body)
        self.assertEqual(len(p.mrets), 0)
        self.assertEqual(len(p.merrs), 0)
        self.assertEqual(len(p.msigs), 0)

    def test_dataReceived_method_call_with_unix_fd(self):
        p = TestProtocol()
        p._authenticated = True

        path = '/test/path'
        member = 'testMethod'
        fd = 99
        data = create_one_unix_fd_method(path, member, 0)

        p.fileDescriptorReceived(fd)
        self.assertIsNone(p.dataReceived(data))
        self.assertEqual(len(p.mcalls), 1)
        self.assertEqual(p.mcalls[0].path, path)
        self.assertEqual(p.mcalls[0].member, member)
        self.assertEqual(p.mcalls[0].body, [fd])
        self.assertEqual(len(p.mrets), 0)
        self.assertEqual(len(p.merrs), 0)
        self.assertEqual(len(p.msigs), 0)

    def test_dataReceived_method_call_with_unix_fd_race(self):
        p = TestProtocol()
        p._authenticated = True

        # message 1
        path1 = '/test/path1'
        member1 = 'testMethod1'
        fd1 = 99
        data1 = create_one_unix_fd_method(path1, member1, 0)

        # message 2
        path2 = '/test/path2'
        member2 = 'testMethod2'
        data2 = create_basic_method(path2, member2)

        # possible race condition, file descriptor for message 1 is received
        p.fileDescriptorReceived(fd1)
        # then unrelated message 2 is received
        self.assertIsNone(p.dataReceived(data2))
        # then message 1, which is expecting file descriptor, is received
        self.assertIsNone(p.dataReceived(data1))

        self.assertEqual(len(p.mcalls), 2)
        self.assertEqual(p.mcalls[0].path, path2)
        self.assertEqual(p.mcalls[0].member, member2)
        self.assertIsNone(p.mcalls[0].body)
        self.assertEqual(p.mcalls[1].path, path1)
        self.assertEqual(p.mcalls[1].member, member1)
        self.assertEqual(p.mcalls[1].body, [fd1])
        self.assertEqual(len(p.mrets), 0)
        self.assertEqual(len(p.merrs), 0)
        self.assertEqual(len(p.msigs), 0)
