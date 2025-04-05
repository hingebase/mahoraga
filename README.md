# Mahoraga

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/hingebase/mahoraga/publish-pypi.yml?label=ci&logo=github)](https://github.com/hingebase/mahoraga/actions)
[![GitHub commit activity](https://img.shields.io/github/commit-activity/y/hingebase/mahoraga?logo=github)](https://github.com/hingebase/mahoraga/commits)
[![PyPI - Version](https://img.shields.io/pypi/v/mahoraga)](https://pypi.org/project/mahoraga)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mahoraga)
![basedpyright](https://img.shields.io/badge/basedpyright-checked-42b983)
![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)
![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)

Mahoraga is a reverse proxy for Python mirrors.
## Features
Once Mahoraga is deployed on a machine with Internet access,
it benefits clients within the same Intranet in several ways:

- Serve Python packages and their metadata from Anaconda and PyPI
- Serve CPython itself from [python-build-standalone][1],
  and the official [embedded distribution][2] for Windows
- Load balance among multiple upstream mirrors
- Lazy local cache (partially implemented)
- Local-generated [sharded conda repodata][3]
## Usage
See the [docs](https://hingebase.github.io/mahoraga/).
## License
Mahoraga is distributed under [Apache-2.0][4] license.

[1]: https://github.com/astral-sh/python-build-standalone/
[2]: https://docs.python.org/3/using/windows.html#the-embeddable-package
[3]: https://conda.org/learn/ceps/cep-0016/
[4]: https://spdx.org/licenses/Apache-2.0.html
