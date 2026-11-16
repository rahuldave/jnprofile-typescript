"""Run the tests of the profile, for just test: python3 scripts/run_tests.py [FOLDER [PATTERN]].

It runs each test in FOLDER, tests by default, as unittest discover does. In CI a skipped test fails the run, so a
lab that misses a program cannot pass. CI is on when the variable CI is set to a value other than empty, false and 0.
"""
import os
import sys
import unittest


def ci():
    """True in CI."""
    return os.environ.get('CI', '').strip().lower() not in ('', 'false', '0')


def main(folder='tests', pattern='test*.py'):
    """Run the tests in FOLDER. Returns 1 when a test fails, or when one skips in CI, else 0."""
    suite = unittest.defaultTestLoader.discover(folder, pattern)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    if result.skipped and ci():
        for test, reason in result.skipped:
            print(f'run_tests: {test.id()} skipped in CI: {reason}', file=sys.stderr)
        print(f'run_tests: {len(result.skipped)} tests skipped, and in CI a skip fails the run', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
