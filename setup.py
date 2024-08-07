#!/usr/bin/env python3

VERSION = '1.1.1'
DESCRIPTION = (
    'A native Python implementation of the DBus protocol for Twisted '
    'applications.'
)

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(
    name='txdbus',
    version=VERSION,
    description=DESCRIPTION,
    license='MIT',
    long_description=open('README.rst').read(),
    url='https://github.com/cocagne/txdbus',
    author='Tom Cocagne',
    author_email='tom.cocagne@gmail.com',
    install_requires=['twisted>=10.1'],
    provides=['txdbus'],
    packages=['txdbus'],
    keywords=['dbus', 'twisted'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Framework :: Twisted',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Networking',
    ],
)
