# Unit test driver.

import os
import sys
from unittest import TestLoader, TestSuite, TextTestRunner

topdir = os.path.split(os.path.abspath(__file__))[0]
os.chdir(topdir)

loader = TestLoader()

if sys.version_info < (3, 0):
    tests = loader.discover('.', 'test_*.py')
elif sys.version_info > (3, 2):
    tests = TestSuite()
    tests.addTests(loader.discover('.', 'test_marshal.py'))
    tests.addTests(loader.discover('.', 'test_message.py'))
else:
    tests = TestSuite()

runner = TextTestRunner(verbosity=2, buffer=True)
result = runner.run(tests)

sys.exit(not result.wasSuccessful())
