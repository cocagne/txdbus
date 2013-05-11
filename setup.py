#!/usr/bin/env python

VERSION     = '1.0.3'
DESCRIPTION = 'txdbus'


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
    requires         = ['twisted'],
    requirements     = ['twisted'],
    packages         = ['txdbus',
                        'txdbus.test'],
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

