"""The command-line tool framework."""

import Queue

from functools import wraps


MAX_EXECUTION = 100000
_FUNC_TO_ENTITY_MAP = {}


class Node(object):
  """Represent function and its dependencies."""

  def __init__(self, func, deps, priority=100):
    self.func = func
    self.deps = deps
    self.priority = priority


class Invoke(object):
  """Represent an Invoke."""

  def __init__(self, node, im_self):
    self.node = node
    self.priority = node.priority
    self.im_self = im_self
    self.deps = []

  def execute(self, *args):
    """Execute the function."""
    updated_args = list(args)[:]
    if self.im_self is not None:
      updated_args.insert(0, self.im_self)

    return self.node.func(*updated_args)

  def __eq__(self, other):
    return (isinstance(other, Invoke) and self.node == other.node and
            self.im_self == other.im_self)

  def __hash__(self):
    return hash(self.node)


class InputInvoke(Invoke):
  """Represents an input."""

  def __init__(self, name, value):
    self.name = name
    self.value = value
    self.priority = -1
    self.deps = []

  def execute(self):
    """Return value."""
    return self.value

  def __eq__(self, other):
    result = isinstance(other, InputInvoke) and self.name == other.name
    return result

  def __hash__(self):
    return hash(self.name)


class Input(Node):
  """Represent an input from command-line arg."""

  def __init__(self, name, value=None):
    self.name = name
    self.value = value
    super(Input, self).__init__(name, [], priority=-1)

  def __eq__(self, other):
    return self.name == other.name

  def __hash__(self):
    return hash(self.name)


def bind(*deps, **configs):
  """A decorator for defining dependencies."""

  def wrap(func):
    """Decorator."""
    _FUNC_TO_ENTITY_MAP[func] = Node(func, deps, **configs)

    return func
  return wrap


def build(func, im_self, inputs):
  """Return all dependencies."""
  if isinstance(func, Input):
    return InputInvoke(func.name, inputs[func].value)

  if isinstance(func, basestring):
    tokens = func.split('.')
    ref = im_self
    for token in tokens:
      ref = getattr(ref, token)
    func = ref.im_func
    im_self = ref.im_self
  else:
    im_self = None

  entity = _FUNC_TO_ENTITY_MAP[func]
  invoke = Invoke(entity, im_self)

  for dep in entity.deps:
    invoke.deps.append(build(dep, im_self, inputs))

  return invoke


def get_all_invokes(invoke):
  """Get all nodes."""
  invokes = set([invoke])

  for child in invoke.deps:
    invokes.update(get_all_invokes(child))

  return invokes


def get_dep_results(invoke, results):
  """Check if it's ready."""
  args = []
  for dep in invoke.deps:
    if dep not in results:
      return False

    args.append(results[dep])

  return args


def execute(func, inputs):
  """Resolve all dependencies and execute func."""
  im_self = None
  wrapped_func = func
  if hasattr(func, 'im_func'):
    im_self = func.im_self
    wrapped_func = func.__name__
    func = func.im_func

  root = build(wrapped_func, im_self, {i: i for i in inputs})

  queue = Queue.PriorityQueue()
  for invoke in get_all_invokes(root):
    queue.put((0, invoke.priority, invoke))

  results = {}

  i = 0
  while i < MAX_EXECUTION:
    i += 1

    step, _, invoke = queue.get()
    dep_results = get_dep_results(invoke, results)

    if dep_results is False:
      # The deps are not fulfilled.
      queue.put((step + 1, invoke.priority, invoke))
    else:
      result = invoke.execute(*dep_results)

      if invoke == root:
        return result
      else:
        results[invoke] = result

  raise Exception('This should never happen.')

