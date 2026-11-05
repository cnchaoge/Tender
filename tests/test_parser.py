from server.core.parser.document import parse_txt, get_file_type


def test_parse_txt_and_get_file_type(tmp_path):
    p = tmp_path / 'sample.txt'
    p.write_text("line1\n\nline2\n", encoding='utf-8')

    content, paras = parse_txt(str(p))
    assert 'line1' in content
    # two non-empty lines
    assert len(paras) == 2

    assert get_file_type('a.txt') == 'txt'
    assert get_file_type('a.unknown') == 'unknown'
