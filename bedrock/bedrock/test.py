"""Test cmd."""

import cmd


@cmd.bind(cmd.Input('build'))
def dep_a(build):
  print build
  return '%s-build' % build


@cmd.bind(priority=2)
def dep_b():
  print 'dep_b'
  return 'dep_b'


@cmd.bind(dep_a, dep_b, priority=1)
def do_b(result_a, result_b):
  return 'YESSS %s %s' % (result_a, result_b)


@cmd.bind(do_b)
def do_c(result):
  print 'HELLLO %s' % result
  return 'YOYO'


class Test(object):
  """Test class."""

  @cmd.bind()
  def internal_dep(self):
    print 'internal'
    return 'internal'

  @cmd.bind(do_c, do_b, 'internal_dep')
  def test(self, result_c, result_b, result_internal):
    print 'This is inside test(): %s %s %s' % (
        result_c, result_b, result_internal)
    return 'From Test.test'


class Another(object):
  """Another."""

  def __init__(self, test):
    self.test_instance = test

  @cmd.bind('test_instance.test')
  def test(self, result_test):
    print 'another %s' % result_test


def main():
  t = Test()
  a = Another(t)
  print cmd.execute(a.test, [cmd.Input('build', 'pdfium')])
  print
  print cmd.execute(do_c, [cmd.Input('build', 'pdfium')])


if __name__ == '__main__':
  main()

