"""Allow ``python -m cedikit ...``, which works even when the ``cedikit`` command
isn't on PATH (common on Windows after ``pip install --user``)."""

from cedikit.cli import app

app(prog_name="cedikit")
