from gcs.gui.command_line import tokenize_command


def test_tokenize_command_numeric_and_path():
    assert tokenize_command("POINT 1 2 3") == ["POINT", "1", "2", "3"]
    assert tokenize_command('MESH IMPORT "C:\\work dir\\model.msh"') == [
        "MESH", "IMPORT", '"C:\\work dir\\model.msh"'
    ]


def test_tokenize_command_preserves_quoted_macro_name():
    assert tokenize_command('MACRO "Marca per area"') == [
        "MACRO", '"Marca per area"'
    ]
