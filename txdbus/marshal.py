"""
Provides data marshalling to and from the DBus wire format

@author: Tom Cocagne
"""

import codecs
import re
import struct

import six

from txdbus.error import MarshallingError


invalid_obj_path_re = re.compile(r'[^a-zA-Z0-9_/]')
if_re = re.compile(r'[^A-Za-z0-9_.]')
bus_re = re.compile(r'[^A-Za-z0-9_.\-:]')
mbr_re = re.compile(r'[^A-Za-z0-9_]')
dot_digit_re = re.compile(r'\.\d')


#                Name      Type code   Alignment
dbus_types = [('BYTE', 'y', 1),
              ('BOOLEAN', 'b', 4),
              ('INT16', 'n', 2),
              ('UINT16', 'q', 2),
              ('INT32', 'i', 4),
              ('UINT32', 'u', 4),
              ('INT64', 'x', 8),
              ('UINT64', 't', 8),
              ('DOUBLE', 'd', 8),
              ('STRING', 's', 4),  # (4-byte align for length)
              ('OBJECT_PATH', 'o', 4),  # (4-byte align for length)
              ('SIGNATURE', 'g', 1),
              ('ARRAY', 'a', 4),  # (4-byte align for length)
              ('STRUCT', '(', 8),
              ('VARIANT', 'v', 1),  # (1-byte align for signature)
              ('DICT_ENTRY', '{', 8),
              ('UNIX_FD', 'h', 4)
              ]


class Byte(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'y'


class Boolean(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'b'


class Int16(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'n'


class UInt16(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'q'


class Int32(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'i'


class UInt32(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'u'


class Int64(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'x'


class UInt64(int):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 't'


class Signature (str):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'g'


class ObjectPath (str):
    """
    Used during Variant serialization to ensure that this type is
    encoded rather than the generic Python type
    """
    dbusSignature = 'o'


variantClassMap = {
    'y': Byte,
    'b': Boolean,
    'n': Int16,
    'q': UInt16,
    'i': Int32,
    'u': UInt32,
    'x': Int64,
    't': UInt64,
    'g': Signature,
    'o': ObjectPath,
}


def validateObjectPath(p):
    """
    Ensures that the provided object path conforms to the DBus standard.
    Throws a L{error.MarshallingError} if non-conformant

    @type p: C{string}
    @param p: A DBus object path
    """
    if not p.startswith('/'):
        raise MarshallingError('Object paths must begin with a "/"')
    if len(p) > 1 and p[-1] == '/':
        raise MarshallingError('Object paths may not end with "/"')
    if '//' in p:
        raise MarshallingError('"//" is not allowed in object paths"')
    if invalid_obj_path_re.search(p):
        raise MarshallingError('Invalid characters contained in object path')


def validateInterfaceName(n):
    """
    Verifies that the supplied name is a valid DBus Interface name. Throws
    an L{error.MarshallingError} if the format is invalid

    @type n: C{string}
    @param n: A DBus interface name
    """
    try:
        if '.' not in n:
            raise Exception('At least two components required')
        if '..' in n:
            raise Exception('".." not allowed in interface names')
        if len(n) > 255:
            raise Exception('Name exceeds maximum length of 255')
        if n[0] == '.':
            raise Exception('Names may not begin with a "."')
        if n[0].isdigit():
            raise Exception('Names may not begin with a digit')
        if if_re.search(n):
            raise Exception(
                'Names contains a character outside the set [A-Za-z0-9_.]')
        if dot_digit_re.search(n):
            raise Exception(
                'No components of an interface name may begin with a digit')
    except Exception as e:
        raise MarshallingError('Invalid interface name "%s": %s' % (n, str(e)))


def validateErrorName(n):
    try:
        validateInterfaceName(n)
    except MarshallingError as e:
        raise MarshallingError(str(e).replace('interface', 'error', 1))


def validateBusName(n):
    """
    Verifies that the supplied name is a valid DBus Bus name. Throws
    an L{error.MarshallingError} if the format is invalid

    @type n: C{string}
    @param n: A DBus bus name
    """
    try:
        if '.' not in n:
            raise Exception('At least two components required')
        if '..' in n:
            raise Exception('".." not allowed in bus names')
        if len(n) > 255:
            raise Exception('Name exceeds maximum length of 255')
        if n[0] == '.':
            raise Exception('Names may not begin with a "."')
        if n[0].isdigit():
            raise Exception('Names may not begin with a digit')
        if bus_re.search(n):
            raise Exception(
                'Names contains a character outside the set [A-Za-z0-9_.\\-:]')
        if not n[0] == ':' and dot_digit_re.search(n):
            raise Exception(
                'No coponents of an interface name may begin with a digit')
    except Exception as e:
        raise MarshallingError('Invalid bus name "%s": %s' % (n, str(e)))


def validateMemberName(n):
    """
    Verifies that the supplied name is a valid DBus member name. Throws
    an L{error.MarshallingError} if the format is invalid

    @type n: C{string}
    @param n: A DBus member name
    """
    try:
        if len(n) < 1:
            raise Exception('Name must be at least one byte in length')
        if len(n) > 255:
            raise Exception('Name exceeds maximum length of 255')
        if n[0].isdigit():
            raise Exception('Names may not begin with a digit')
        if mbr_re.search(n):
            raise Exception(
                'Names contains a character outside the set [A-Za-z0-9_]')
    except Exception as e:
        raise MarshallingError('Invalid member name "%s": %s' % (n, str(e)))


# XXX: This could be made *much* smarter (handle objects and recursive
# structures)
def sigFromPy(pobj):
    """
    Returns the DBus signature type for the argument. If the argument is an
    instance of one of the type wrapper classes, the exact type signature
    corresponding to the wrapper class will be used. If the object has a
    variable named 'dbusSignature', the value of that variable will be
    used. Otherwise, a generic type will be used (i.e "i" for a Python int)

    @rtype: C{string}
    @returns: The DBus signature for the supplied Python object
    """
    sig = getattr(pobj, 'dbusSignature', None)

    if sig is not None:
        return sig

    elif isinstance(pobj, bool):
        return 'b'
    elif isinstance(pobj, int):
        return 'i'
    elif isinstance(pobj, six.integer_types):
        return 'x'
    elif isinstance(pobj, float):
        return 'd'
    elif isinstance(pobj, six.string_types):
        return 's'
    elif isinstance(pobj, bytearray):
        return 'ay'

    elif isinstance(pobj, list):
        vtype = type(pobj[0])
        same = True
        for v in pobj[1:]:
            if not isinstance(v, vtype):
                same = False
        if same:
            return 'a' + sigFromPy(pobj[0])
        else:
            return 'av'

    elif isinstance(pobj, tuple):
        return '(' + ''.join(sigFromPy(e) for e in pobj) + ')'

    elif isinstance(pobj, dict):
        same = True
        vtype = None
        for k, v in six.iteritems(pobj):
            if vtype is None:
                vtype = type(v)
            elif not isinstance(v, vtype):
                same = False
        if same:
            return 'a{' + sigFromPy(k) + sigFromPy(v) + '}'
        else:
            return 'a{' + sigFromPy(k) + 'v}'

    else:
        raise MarshallingError(
            'Invalid Python type for variant: ' +
            repr(pobj))


# ------------------------------------------------------------------------
#                          Marshalling Functions
# Padding:
#    - All data types must be padded to the correct alignment
#    - All padding bytes must be nul
#
padding = {
    0: b'\0' * 0,
    1: b'\0' * 1,
    2: b'\0' * 2,
    3: b'\0' * 3,
    4: b'\0' * 4,
    5: b'\0' * 5,
    6: b'\0' * 6,
    7: b'\0' * 7,
}


def genpad(align):
    return lambda x: padding[x % align and (align - x % align) or 0]


pad = {}

for name, tcode, align in dbus_types:
    pad[tcode] = genpad(align)

pad['header'] = genpad(8)


# ------------------------------------------------------------------------
#                    Signature Generator/Iterator
#
def genCompleteTypes(compoundSig):
    """
    Generator function used to iterate over each complete,
    top-level type contained in in a signature. Ex::
      "iii"       => [ 'i', 'i',       'i' ]
      "i(ii)i"    => [ 'i', '(ii)',    'i' ]
      "i(i(ii))i" => [ 'i', '(i(ii))', 'i' ]
    """
    i = 0
    end = len(compoundSig)

    def find_end(idx, b, e):
        depth = 1
        while idx < end:
            subc = compoundSig[idx]
            if subc == b:
                depth += 1
            elif subc == e:
                depth -= 1
                if depth == 0:
                    return idx
            idx += 1

    while i < end:
        c = compoundSig[i]

        if c == '(':
            x = find_end(i + 1, '(', ')')
            yield compoundSig[i:x + 1]
            i = x

        elif c == '{':
            x = find_end(i + 1, '{', '}')
            yield compoundSig[i:x + 1]
            i = x

        elif c == 'a':
            g = genCompleteTypes(compoundSig[i + 1:])
            ct = six.next(g)
            i += len(ct)
            yield 'a' + ct

        else:
            yield c
        i += 1


# ------------------------------------------------------------------------
#                          Marshalling Functions
# General:
#    - All values must be padded to proper alignment
#    - Pad bytes must be zero
#
# BOOLEAN:
#    - Only 1 & 0 are valid
#
# DICT_ENTRY:
#    - Identical to STRUCT
#
# Message:
#    - Max length of header, body and all padding is 2^27
#
# Message Header:
#    - Must be padded to a multiple of 8 bytes
#    - Fixed signature: "yyyyuua(yv)"
#        *  1 BYTE:   Endian flag. 'l' for little, 'B' for big
#        *  2 BYTE:   Message type enum
#        *  3 BYTE:   Bit Flags
#        *  4 BYTE:   Major protocol version (1 currently)
#        *  5 UINT32: Body Length (begins after header padding)
#        *  6 UINT32: Message serial number (must not be zero)
#        *  7 Array:  zero or more header fields. Msg type determines
#                     which entries are required
#
# Message Body:
#    - Begins on 8-byte boundary
#    - Not padded to a required byte alignment
#
#

def marshal_byte(ct, var, start_byte, lendian, oobFDs):
    return 1, [struct.pack(lendian and '<B' or '>B', var)]


def marshal_boolean(ct, var, start_byte, lendian, oobFDs):
    return 4, [struct.pack(lendian and '<I' or '>I', 1 if var else 0)]


def marshal_int16(ct, var, start_byte, lendian, oobFDs):
    return 2, [struct.pack(lendian and '<h' or '>h', var)]


def marshal_uint16(ct, var, start_byte, lendian, oobFDs):
    return 2, [struct.pack(lendian and '<H' or '>H', var)]


def marshal_int32(ct, var, start_byte, lendian, oobFDs):
    return 4, [struct.pack(lendian and '<i' or '>i', var)]


def marshal_uint32(ct, var, start_byte, lendian, oobFDs):
    return 4, [struct.pack(lendian and '<I' or '>I', var)]


def marshal_int64(ct, var, start_byte, lendian, oobFDs):
    return 8, [struct.pack(lendian and '<q' or '>q', var)]


def marshal_uint64(ct, var, start_byte, lendian, oobFDs):
    return 8, [struct.pack(lendian and '<Q' or '>Q', var)]


def marshal_double(ct, var, start_byte, lendian, oobFDs):
    return 8, [struct.pack(lendian and '<d' or '>d', var)]


def marshal_unix_fd(ct, var, start_byte, lendian, oobFDs):
    index = len(oobFDs)
    oobFDs.append(var)
    return 4, [struct.pack(lendian and '<I' or '>I', index)]


# STRING:
#    - *must* be valid UTF-8, nul terminated with no embedded nuls
#    format:
#       1 - UINT32 length in bytes (excluding terminating nul)
#       2 - string data (no embedded nuls)
#       3 - terminating nul byte
#
def marshal_string(ct, var, start_byte, lendian, oobFDs):
    if not isinstance(var, six.string_types):
        raise MarshallingError('Required string. Received: ' + repr(var))
    if var.find('\0') != -1:
        raise MarshallingError(
            'Embedded nul characters are not allowed within DBus strings')
    var = codecs.encode(var, 'utf-8')
    return 4 + \
        len(var) + \
        1, [struct.pack(lendian and '<I' or '>I', len(var)), var, b'\0']


# OBJECT_PATH:
#    - Identical to string
#
def marshal_object_path(ct, var, start_byte, lendian, oobFDs):
    validateObjectPath(var)
    return marshal_string(ct, var, start_byte, lendian, oobFDs)


# SIGNATURE:
#    - Ends with nul byte
#    - List of complete types. No partial types permitted
#    - Max signature length is 255
#    format:
#       1 - Single byte length
#       2 - Valid signature string
#       3 - terminating nul byte
def marshal_signature(ct, var, start_byte, lendian, oobFDs):
    # XXX validate signature
    var = codecs.encode(var, 'ascii')
    return 2 + \
        len(var), [struct.pack(lendian and '<B' or '>B', len(var)), var, b'\0']


# ARRAY:
#    - Max length is 2^26
#    format:
#       1 - UINT32 length of array data (does not include alignment padding)
#       2 - Padding to required alignment of contained data type
#       3 - each array element
def marshal_array(ct, var, start_byte, lendian, oobFDs):
    chunks = []
    data_len = 0
    tsig = ct[1:]   # strip of leading 'a'
    tcode = tsig[0]  # type of array element

    start_byte += 4  # for array size

    initial_padding = pad[tcode](start_byte)

    if initial_padding:
        start_byte += len(initial_padding)
        chunks.append(initial_padding)

    if isinstance(var, (list, tuple, bytearray)):
        arr_list = var
    elif isinstance(var, dict):
        arr_list = [tpl for tpl in six.iteritems(var)]
    else:
        raise MarshallingError(
            'List, Tuple, Bytearray, or Dictionary required for DBus array. '
            ' Received: ' + repr(var)
        )

    for item in arr_list:

        padding = pad[tcode](start_byte)

        if padding:
            start_byte += len(padding)
            data_len += len(padding)
            chunks.append(padding)

        nbytes, vchunks = marshallers[tcode](
            tsig, item, start_byte, lendian, oobFDs)

        start_byte += nbytes
        data_len += nbytes

        chunks.extend(vchunks)

    chunks.insert(0, struct.pack(lendian and '<I' or '>I', data_len))

    return 4 + len(initial_padding) + data_len, chunks


# STRUCT:
#    - Must start on 8 byte boundary
#    - Content consists of each field marshaled in sequence
#
def marshal_struct(ct, var, start_byte, lendian, oobFDs):
    return marshal(ct[1:-1], var, start_byte, lendian, oobFDs)


marshal_dictionary = marshal_struct


# VARIANT:
#    - Signature must contain only a single, complete type
#    format:
#       1 - Marshaled SIGNATURE
#       2 - Any required padding to align the type specified in the signature
#       3 - Marshaled value
def marshal_variant(ct, var, start_byte, lendian, oobFDs):
    # XXX: ensure only a single, complete type is in the siguature
    bstart = start_byte

    vsig = sigFromPy(var)

    nbytes, chunks = marshal_signature(
        ct, sigFromPy(var), start_byte, lendian, oobFDs)

    start_byte += nbytes

    padding = pad[vsig[0]](start_byte)

    if padding:
        start_byte += len(padding)
        chunks.append(padding)

    rnbytes, rchunks = marshal(vsig, [var], start_byte, lendian)

    start_byte += rnbytes
    chunks.extend(rchunks)

    return start_byte - bstart, chunks


marshallers = {
    'y': marshal_byte,
    'b': marshal_boolean,
    'n': marshal_int16,
    'q': marshal_uint16,
    'i': marshal_int32,
    'u': marshal_uint32,
    'x': marshal_int64,
    't': marshal_uint64,
    'd': marshal_double,
    's': marshal_string,
    'o': marshal_object_path,
    'g': marshal_signature,
    'a': marshal_array,
    '(': marshal_struct,
    'v': marshal_variant,
    '{': marshal_dictionary,
    'h': marshal_unix_fd,
}


def marshal(compoundSignature, variableList,
            startByte=0, lendian=True, oobFDs=None):
    """
    Encodes the Python objects in variableList into the DBus wire-format
    matching the supplied compoundSignature. This function retuns a list of
    binary strings is rather than a single string to simplify the recursive
    marshalling algorithm. A single string may be easily obtained from the
    result via: ''.join(list_of_binary_strings)

    Any UNIX_FD 'h' type is encoded per spec and the respective FD appended
    to oobFDs which should be supplied as an empty list.

    @type compoundSignature: C{string}
    @param compoundSignature: DBus signature specifying the types of the
                              variables to encode

    @type variableList: C{list}
    @param variableList: List of variables to encode (length of the list
                         must exactly match the number of variables specified
                         in compoundSignature


    @type startByte: C{int}
    @param startByte: Used during recursive marshalling to ensure data
                      alignment requirements are met

    @type lendian: C{bool}
    @param lendian: True if the data should be serialized in
                    little-endian format


    @returns: (number_of_encoded_bytes, list_of_binary_strings)
    """
    chunks = []
    bstart = startByte

    if hasattr(variableList, 'dbusOrder'):
        order = getattr(variableList, 'dbusOrder')
        variableList = [getattr(variableList, attr_name)
                        for attr_name in order]

    for ct, var in zip(genCompleteTypes(compoundSignature), variableList):
        tcode = ct[0]
        padding = pad[tcode](startByte)

        if padding:
            startByte += len(padding)
            chunks.append(padding)

        nbytes, vchunks = marshallers[tcode](
            ct, var, startByte, lendian, oobFDs)

        startByte += nbytes

        chunks.extend(vchunks)

    return startByte - bstart, chunks


# ------------------------------------------------------------------------
# ------------------------------------------------------------------------
#                         Unmarshalling Functions
# ------------------------------------------------------------------------
# ------------------------------------------------------------------------


def unmarshal_byte(ct, data, offset, lendian, oobFDs):
    return 1, struct.unpack_from(lendian and '<B' or '>B', data, offset)[0]


def unmarshal_boolean(ct, data, offset, lendian, oobFDs):
    return 4, struct.unpack_from(
        lendian and '<I' or '>I', data, offset)[0] != 0


def unmarshal_int16(ct, data, offset, lendian, oobFDs):
    return 2, struct.unpack_from(lendian and '<h' or '>h', data, offset)[0]


def unmarshal_uint16(ct, data, offset, lendian, oobFDs):
    return 2, struct.unpack_from(lendian and '<H' or '>H', data, offset)[0]


def unmarshal_int32(ct, data, offset, lendian, oobFDs):
    return 4, struct.unpack_from(lendian and '<i' or '>i', data, offset)[0]


def unmarshal_uint32(ct, data, offset, lendian, oobFDs):
    return 4, struct.unpack_from(lendian and '<I' or '>I', data, offset)[0]


def unmarshal_int64(ct, data, offset, lendian, oobFDs):
    return 8, struct.unpack_from(lendian and '<q' or '>q', data, offset)[0]


def unmarshal_uint64(ct, data, offset, lendian, oobFDs):
    return 8, struct.unpack_from(lendian and '<Q' or '>Q', data, offset)[0]


def unmarshal_double(ct, data, offset, lendian, oobFDs):
    return 8, struct.unpack_from(lendian and '<d' or '>d', data, offset)[0]


def unmarshal_unix_fd(ct, data, offset, lendian, oobFDs):
    index = struct.unpack_from(lendian and '<I' or '>I', data, offset)[0]
    try:
        fd = oobFDs[index]
    except IndexError:
        fd = None
    return 4, fd


# STRING:
#    - *must* be valid UTF-8, nul terminated with no embedded nuls
#    format:
#       1 - UINT32 length in bytes (excluding terminating nul)
#       2 - string data (no embedded nuls)
#       3 - terminating nul byte
#
def unmarshal_string(ct, data, offset, lendian, oobFDs):
    slen = struct.unpack_from(lendian and '<I' or '>I', data, offset)[0]
    s = codecs.decode(data[offset + 4: offset + 4 + slen], 'utf-8')
    return 4 + slen + 1, s


# OBJECT_PATH:
#    - Identical to string
#
unmarshal_object_path = unmarshal_string


# SIGNATURE:
#    - Ends with nul byte
#    - List of complete types. No partial types permitted
#    - Max signature length is 255
#    format:
#       1 - Single byte length
#       2 - Valid signature string
#       3 - terminating nul byte
def unmarshal_signature(ct, data, offset, lendian, oobFDs):
    slen = struct.unpack_from(lendian and '<B' or '>B', data, offset)[0]
    s = codecs.decode(data[offset + 1: offset + 1 + slen], 'ascii')
    return 1 + slen + 1, s


# ARRAY:
#    - Max length is 2^26
#    format:
#       1 - UINT32 length of array data (does not include alignment padding)
#       2 - Padding to required alignment of contained data type
#       3 - each array element
def unmarshal_array(ct, data, offset, lendian, oobFDs):
    start_offset = offset
    values = []
    data_len = struct.unpack_from(lendian and '<I' or '>I', data, offset)[0]
    tsig = ct[1:]  # strip of leading 'a'
    tcode = tsig[0]  # type of array element

    offset += 4                         # 4-byte data length
    offset += len(pad[tcode](offset))  # padding length

    end_offset = offset + data_len

    while offset < end_offset:

        offset += len(pad[tcode](offset))

        nbytes, value = unmarshallers[tcode](
            tsig, data, offset, lendian, oobFDs)

        offset += nbytes
        values.append(value)

    if not offset == end_offset:
        raise MarshallingError('Invalid array encoding')

    if tcode == '{':
        d = {}
        for item in values:
            d[item[0]] = item[1]
        values = d

    return offset - start_offset, values


# STRUCT:
#    - Must start on 8 byte boundary
#    - Content consists of each field marshaled in sequence
#
def unmarshal_struct(ct, data, offset, lendian, oobFDs):
    return unmarshal(ct[1:-1], data, offset, lendian, oobFDs)


unmarshal_dictionary = unmarshal_struct


# VARIANT:
#    - Signature must contain only a single, complete type
#    format:
#       1 - Marshaled SIGNATURE
#       2 - Any required padding to align the type specified in the signature
#       3 - Marshaled value
def unmarshal_variant(ct, data, offset, lendian, oobFDs):
    # XXX: ensure only a single, complete type is in the siguature
    start_offset = offset
    nsig, vsig = unmarshal_signature(ct, data, offset, lendian, oobFDs)

    offset += nsig

    offset += len(pad[vsig[0]](offset))

    nvar, value = unmarshal(vsig, data, offset, lendian, oobFDs)

    offset += nvar

    return offset - start_offset, value[0]


unmarshallers = {
    'y': unmarshal_byte,
    'b': unmarshal_boolean,
    'n': unmarshal_int16,
    'q': unmarshal_uint16,
    'i': unmarshal_int32,
    'u': unmarshal_uint32,
    'x': unmarshal_int64,
    't': unmarshal_uint64,
    'd': unmarshal_double,
    's': unmarshal_string,
    'o': unmarshal_object_path,
    'g': unmarshal_signature,
    'a': unmarshal_array,
    '(': unmarshal_struct,
    'v': unmarshal_variant,
    '{': unmarshal_dictionary,
    'h': unmarshal_unix_fd,
}


def unmarshal(compoundSignature, data, offset=0, lendian=True, oobFDs=None):
    """
    Unmarshals DBus encoded data.

    @type compoundSignature: C{string}
    @param compoundSignature: DBus signature specifying the encoded value types

    @type data: C{string}
    @param data: Binary data

    @type offset: C{int}
    @param offset: Offset within data at which data for compoundSignature
                   starts (used during recursion)

    @type lendian: C{bool}
    @param lendian: True if data is encoded in little-endian format

    @returns: (number_of_bytes_decoded, list_of_values)
    """
    values = []
    start_offset = offset

    for ct in genCompleteTypes(compoundSignature):
        tcode = ct[0]
        offset += len(pad[tcode](offset))

        nbytes, value = unmarshallers[tcode](ct, data, offset, lendian, oobFDs)

        offset += nbytes
        values.append(value)

    return offset - start_offset, values
