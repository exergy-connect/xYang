"""Token positions and character classification remain stable (#264)."""

import pytest

from xyang import parse_yang_string
from xyang.errors import YangSyntaxError
from xyang.parser.tokenizer import YangTokenizer


def test_comments_strings_and_positions():
    source = 'module t {\n /* a\n b */ leaf foo-bar { // tail\n description "a\\n" + \'b\'; type string; }\n}'
    stream = YangTokenizer().tokenize(source)
    assert stream.tokens == [
        'module', 't', '{', 'leaf', 'foo-bar', '{', 'description', 'a\nb',
        ';', 'type', 'string', ';', '}', '}',
    ]
    assert stream.positions == [
        (1, 0), (1, 7), (1, 9), (3, 6), (3, 11), (3, 19), (4, 1),
        (4, 13), (4, 24), (4, 26), (4, 31), (4, 37), (4, 39), (5, 0),
    ]


def test_unicode_identifier_and_digits():
    stream = YangTokenizer().tokenize('a²_é -12²3 1.2²3')
    assert stream.tokens == ['a²_é', '-12²3', '1.2²3']


def test_illegal_leaf_identifier_reports_line():
    with pytest.raises(YangSyntaxError, match="2: leaf argument must be an identifier, got '@'"):
        parse_yang_string('module t {\n  leaf @;\n}')
