"""Pruebas del smoke test de la demo (RF-16). No usan AWS: prueban el manejo de errores."""

import smoke_test


def test_wrong_url_fails_with_a_clear_message(monkeypatch, capsys):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    code = smoke_test.main(["--api-url", "http://127.0.0.1:9", "--timeout", "5"])

    assert code == 1
    assert "No se pudo conectar" in capsys.readouterr().err


def test_multipart_puts_the_file_last_as_s3_expects():
    body, content_type = smoke_test._multipart({"key": "incoming/x.csv"}, "fecha.csv", b"data")

    assert content_type.startswith("multipart/form-data; boundary=")
    assert body.index(b'name="key"') < body.index(b'name="file"')
    assert body.rstrip().endswith(b"--")
