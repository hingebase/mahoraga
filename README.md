# Mahoraga
Mahoraga is a reverse proxy for Python mirrors.
## Features
Once Mahoraga is deployed on a machine with Internet access,
it benefits clients within the same Intranet in several ways:
- Serve Python packages and their metadata from Anaconda and PyPI
- Serve CPython itself from [python-build-standalone][1]
  and the official [embedded distribution][2] for Windows
- Load balance among multiple upstream mirrors
- Lazy local cache (partially implemented)
- Local-generated [sharded conda repodata][3]
## License
Mahoraga is distributed under [Apache-2.0][4] license.

[1]: https://github.com/astral-sh/python-build-standalone/
[2]: https://docs.python.org/3/using/windows.html#the-embeddable-package
[3]: https://conda.org/learn/ceps/cep-0016/
[4]: https://spdx.org/licenses/Apache-2.0.html
