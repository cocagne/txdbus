# Unit test driver.

import os
import sys

if sys.version_info[:2] >= (2,7):
    from unittest import TestLoader, TextTestRunner, TestSuite
else:
    from unittest2 import TestLoader, TextTestRunner, TestSuite

topdir = os.path.split(os.path.abspath(__file__))[0]
os.chdir(topdir)

loader = TestLoader()

if sys.version_info[:2] < (3, 0):
    tests = loader.discover('.', 'test_*.py')
elif sys.version_info[:2] > (3, 2):
    tests = TestSuite()
    tests.addTests(loader.discover('.', 'test_marshal.py'))
    tests.addTests(loader.discover('.', 'test_message.py'))
else:
    tests = TestSuite()

runner = TextTestRunner(verbosity=1, buffer=True)
runner.run(tests)
