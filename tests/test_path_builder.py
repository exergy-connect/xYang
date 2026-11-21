"""Path builder preserves display paths and escaped JSON Pointers (#263)."""

from xyang.validator.path_builder import PathBuilder


def test_nested_index_and_escaped_pointer():
    path = PathBuilder(['root'])
    path.push('entry', "id='a'", index=2, pointer_name='a~/b')
    assert path.current() == "/root/entry[id='a']"
    assert path.pointer() == '/root/a~0~1b/2'
    assert path.child('x/y') == "/root/entry[id='a']/x/y"
    assert path.child_pointer('x/y', 1) == '/root/a~0~1b/2/x~1y/1'
    path.pop()
    assert path.current() == '/root'
    assert path.pointer() == '/root'


def test_child_path_preserves_trailing_slash_behavior():
    path = PathBuilder()
    path.push('a/')
    assert path.current() == '/a/'
    assert path.child('b') == '/a/b'
    assert path.child_pointer('b') == '/a~1/b'
    path.pop()
    assert path.child('b') == '/b'
