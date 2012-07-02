#!/usr/bin/env python

VERSION     = '1.0.0'
DESCRIPTION = 'Twisted DBus'

try:
    import twisted
except ImportError:
    raise SystemExit('Missing requried dependency: Twisted')

from distutils.core import setup


setup(
    name             = 'twisted_dbus',
    version          = VERSION,
    description      = DESCRIPTION,
    license          = "MIT",
    long_description ="""\
A native Python implementation of the DBus protocol for the Twisted
networking framework""",
    url              = 'https://github.com/cocagne/twisted_dbus',
    author           = "Tom Cocagne",
    author_email     = 'tom.cocagne@gmail.com',
    packages         = ['tx',
                        'tx.dbus',
                        'tx.dbus.test'],
    )

