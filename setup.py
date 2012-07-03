#!/usr/bin/env python

VERSION     = '1.0.0'
DESCRIPTION = 'Tx DBus'

try:
    import twisted
except ImportError:
    raise SystemExit('Missing requried dependency: Twisted')

from distutils.core import setup


setup(
    name             = 'txdbus',
    version          = VERSION,
    description      = DESCRIPTION,
    license          = "MIT",
    long_description ="""\
A native Python implementation of the DBus protocol for the Twisted
networking framework""",
    url              = 'https://github.com/cocagne/txdbus',
    author           = "Tom Cocagne",
    author_email     = 'tom.cocagne@gmail.com',
    packages         = ['tx',
                        'tx.dbus',
                        'tx.dbus.test'],
    keywords         = ['dbus', 'twisted'],
    classifiers      = ['Development Status :: 4 - Beta',
                        'Framework :: Twisted',
                        'Intended Audience :: Developers',
                        'License :: OSI Approved :: MIT License',
                        'Operating System :: POSIX',
                        'Programming Language :: Python',
                        'Topic :: Software Development :: Libraries',
                        'Topic :: System :: Networking'],
    )

