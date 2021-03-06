"""Tests for matching against protocols.

Based on PEP 544 https://www.python.org/dev/peps/pep-0544/.
"""

from pytype import file_utils
from pytype.tests import test_base


class ProtocolTest(test_base.TargetPython3BasicTest):
  """Tests for protocol implementation."""

  def test_check_protocol(self):
    self.Check("""
      import protocols
      from typing import Sized
      def f(x: protocols.Sized):
        return None
      def g(x: Sized):
        return None
      class Foo:
        def __len__(self):
          return 5
      f([])
      foo = Foo()
      f(foo)
      g([])
      g(foo)
    """)

  def test_check_protocol_error(self):
    _, errors = self.InferWithErrors("""\
      import protocols

      def f(x: protocols.SupportsAbs):
        return x.__abs__()
      f(["foo"])
    """)
    self.assertErrorLogIs(errors, [(5, "wrong-arg-types",
                                    r"\(x: SupportsAbs\).*\(x: List\[str\]\)")])

  def test_check_iterator_error(self):
    _, errors = self.InferWithErrors("""\
      from typing import Iterator
      def f(x: Iterator[int]):
        return None
      class Foo:
        def next(self) -> str:
          return ''
        def __iter__(self):
          return self
      f(Foo())  # line 9
    """)
    self.assertErrorLogIs(
        errors, [(9, "wrong-arg-types", r"Iterator\[int\].*Foo")])

  def test_check_protocol_match_unknown(self):
    self.Check("""\
      from typing import Sized
      def f(x: Sized):
        pass
      class Foo(object):
        pass
      def g(x):
        foo = Foo()
        foo.__class__ = x
        f(foo)
    """)

  def test_check_protocol_against_garbage(self):
    _, errors = self.InferWithErrors("""\
      from typing import Sized
      def f(x: Sized):
        pass
      class Foo(object):
        pass
      def g(x):
        foo = Foo()
        foo.__class__ = 42
        f(foo)
    """)
    self.assertErrorLogIs(errors, [(9, "wrong-arg-types", r"\(x: Sized\)")])

  def test_check_parameterized_protocol(self):
    self.Check("""\
      from typing import Iterator, Iterable

      class Foo(object):
        def __iter__(self) -> Iterator[int]:
          return iter([])

      def f(x: Iterable[int]):
        pass

      foo = Foo()
      f(foo)
      f(iter([3]))
    """)

  def test_check_parameterized_protocol_error(self):
    _, errors = self.InferWithErrors("""\
      from typing import Iterator, Iterable

      class Foo(object):
        def __iter__(self) -> Iterator[str]:
          return iter([])

      def f(x: Iterable[int]):
        pass

      foo = Foo()
      f(foo)
    """)
    self.assertErrorLogIs(errors, [(11, "wrong-arg-types",
                                    r"\(x: Iterable\[int\]\).*\(x: Foo\)")])

  def test_check_parameterized_protocol_multi_signature(self):
    self.Check("""\
      from typing import Sequence, Union

      class Foo(object):
        def __len__(self):
          return 0
        def __getitem__(self, x: Union[int, slice]) -> Union[int, Sequence[int]]:
          return 0

      def f(x: Sequence[int]):
        pass

      foo = Foo()
      f(foo)
    """)

  def test_check_parameterized_protocol_error_multi_signature(self):
    _, errors = self.InferWithErrors("""\
      from typing import Sequence, Union

      class Foo(object):
        def __len__(self):
          return 0
        def __getitem__(self, x: int) -> int:
          return 0

      def f(x: Sequence[int]):
        pass

      foo = Foo()
      f(foo)
    """)
    self.assertErrorLogIs(errors, [(13, "wrong-arg-types",
                                    r"\(x: Sequence\[int\]\).*\(x: Foo\)")])

  def test_construct_dict_with_protocol(self):
    self.Check("""
      class Foo(object):
        def __iter__(self):
          pass
      def f(x: Foo):
        return dict(x)
    """)

  def test_method_on_superclass(self):
    self.Check("""
      class Foo(object):
        def __iter__(self):
          pass
      class Bar(Foo):
        pass
      def f(x: Bar):
        return iter(x)
    """)

  def test_method_on_parameterized_superclass(self):
    self.Check("""
      from typing import List
      class Bar(List[int]):
        pass
      def f(x: Bar):
        return iter(x)
    """)

  def test_any_superclass(self):
    self.Check("""
      class Bar(__any_object__):
        pass
      def f(x: Bar):
        return iter(x)
    """)

  def test_multiple_options(self):
    self.Check("""
      class Bar(object):
        if __random__:
          def __iter__(self): return 1
        else:
          def __iter__(self): return 2
      def f(x: Bar):
        return iter(x)
    """)

  def test_iterable_getitem(self):
    ty = self.Infer("""
      from typing import Iterable, Iterator, TypeVar
      T = TypeVar("T")
      class Bar(object):
        def __getitem__(self, i: T) -> T:
          if i > 10:
            raise IndexError()
          return i
      T2 = TypeVar("T2")
      def f(s: Iterable[T2]) -> Iterator[T2]:
        return iter(s)
      next(f(Bar()))
    """, deep=False)
    self.assertTypesMatchPytd(ty, """
      from typing import Iterable, Iterator, TypeVar
      T = TypeVar("T")
      class Bar(object):
        def __getitem__(self, i: T) -> T: ...
      T2 = TypeVar("T2")
      def f(s: Iterable[T2]) -> Iterator[T2]
    """)

  def test_iterable_iter(self):
    ty = self.Infer("""
      from typing import Iterable, Iterator, TypeVar
      class Bar(object):
        def __iter__(self) -> Iterator:
          return iter([])
      T = TypeVar("T")
      def f(s: Iterable[T]) -> Iterator[T]:
        return iter(s)
      next(f(Bar()))
    """, deep=False)
    self.assertTypesMatchPytd(ty, """
      from typing import Iterable, Iterator, TypeVar
      class Bar(object):
        def __iter__(self) -> Iterator: ...
      T = TypeVar("T")
      def f(s: Iterable[T]) -> Iterator[T]
    """)

  def test_pyi_iterable_getitem(self):
    with file_utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        T = TypeVar("T")
        class Foo(object):
          def __getitem__(self, i: T) -> T: ...
      """)
      self.Check("""
        from typing import Iterable, TypeVar
        import foo
        T = TypeVar("T")
        def f(s: Iterable[T]) -> T: ...
        f(foo.Foo())
      """, pythonpath=[d.path])

  def test_pyi_iterable_iter(self):
    with file_utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        class Foo(object):
          def __iter__(self) -> ?: ...
      """)
      self.Check("""
        from typing import Iterable, TypeVar
        import foo
        T = TypeVar("T")
        def f(s: Iterable[T]) -> T: ...
        f(foo.Foo())
      """, pythonpath=[d.path])

  def test_inherited_abstract_method_error(self):
    _, errors = self.InferWithErrors("""\
      from typing import Iterator
      class Foo(object):
        def __iter__(self) -> Iterator[str]:
          return __any_object__
        def next(self):
          return __any_object__
      def f(x: Iterator[int]):
        pass
      f(Foo())  # line 9
    """)
    self.assertErrorLogIs(
        errors, [(9, "wrong-arg-types", r"Iterator\[int\].*Foo")])

  def test_reversible(self):
    self.Check("""
      from typing import Reversible
      class Foo(object):
        def __reversed__(self):
          pass
      def f(x: Reversible):
        pass
      f(Foo())
    """)

  def test_collection(self):
    self.Check("""
      from typing import Collection
      class Foo(object):
        def __contains__(self, x):
          pass
        def __iter__(self):
          pass
        def __len__(self):
          pass
      def f(x: Collection):
        pass
      f(Foo())
    """)

  def test_list_against_collection(self):
    self.Check("""
      from typing import Collection
      def f() -> Collection[str]:
        return [""]
    """)

  def test_hashable(self):
    self.Check("""
      from typing import Hashable
      class Foo(object):
        def __hash__(self):
          pass
      def f(x: Hashable):
        pass
      f(Foo())
    """)

  def test_list_hash(self):
    errors = self.CheckWithErrors("""\
      from typing import Hashable
      def f(x: Hashable):
        pass
      f([])  # line 4
    """)
    self.assertErrorLogIs(
        errors, [(4, "wrong-arg-types", r"Hashable.*List.*__hash__")])

  def test_hash_constant(self):
    errors = self.CheckWithErrors("""\
      from typing import Hashable
      class Foo(object):
        __hash__ = None
      def f(x: Hashable):
        pass
      f(Foo())  # line 6
    """)
    self.assertErrorLogIs(
        errors, [(6, "wrong-arg-types", r"Hashable.*Foo.*__hash__")])

  def test_generic_callable(self):
    with file_utils.Tempdir() as d:
      d.create_file("foo.pyi", """
        from typing import Generic, TypeVar
        T = TypeVar("T")
        class Foo(Generic[T]):
          def __init__(self, x: T):
            self = Foo[T]
          def __call__(self) -> T: ...
      """)
      self.Check("""
        from typing import Callable
        import foo
        def f() -> Callable:
          return foo.Foo("")
        def g() -> Callable[[], str]:
          return foo.Foo("")
      """, pythonpath=[d.path])


class ProtocolsTestPython3Feature(test_base.TargetPython3FeatureTest):
  """Tests for protocol implementation on a target using a Python 3 feature."""

  def test_check_iterator(self):
    self.Check("""
      from typing import Iterator
      def f(x: Iterator):
        return None
      class Foo:
        def __next__(self):
          return None
        def __iter__(self):
          return None
      foo = Foo()
      f(foo)
    """)

  def test_check_parameterized_iterator(self):
    self.Check("""
      from typing import Iterator
      def f(x: Iterator[int]):
        return None
      class Foo:
        def __next__(self):
          return 42
        def __iter__(self):
          return self
      f(Foo())
    """)

  def test_inherited_abstract_method(self):
    self.Check("""
      from typing import Iterator
      class Foo(object):
        def __iter__(self) -> Iterator[int]:
          return __any_object__
        def __next__(self):
          return __any_object__
      def f(x: Iterator[int]):
        pass
      f(Foo())
    """)

  def test_check_supports_bytes_protocol(self):
    self.Check("""
      import protocols
      from typing import SupportsBytes
      def f(x: protocols.SupportsBytes):
        return None
      def g(x: SupportsBytes):
        return None
      class Foo:
        def __bytes__(self):
          return b"foo"
      foo = Foo()
      f(foo)
      g(foo)
    """)


test_base.main(globals(), __name__ == "__main__")
