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
