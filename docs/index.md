{{ readme }}
## What we support
<div class="grid cards" markdown>

- [![uv](https://astral.sh/static/SVG/UV.svg){ .middle width="32" }][1]　__uv__

    ---

    *The answer to Python package and project management.* Set up Python itself
    and PyPI packages, all in one place.
    [:octicons-arrow-right-24: Docs](tutorial.md#uv)

- [![Pixi](https://pixi.sh/latest/assets/pixi.png){ .middle width="36" }][2]　__Pixi__

    ---

    *Not only Python.* Install toolchains for [various programming languages][3]
    and take full control of your workflow.
    [:octicons-arrow-right-24: Docs](tutorial.md#pixi)

- [![Pyodide](https://cdn.jsdelivr.net/gh/pyodide/pyodide@{{ pyodide_py_version }}/docs/_static/img/pyodide-logo-readme.png){ .middle width="70" }][4] __Pyodide__

    ---

    *From the backend to the frontend.* Share your masterpiece with your
    fellows via our CORS-ready mirror.
    [:octicons-arrow-right-24: Docs](tutorial.md#pyodide)

    *[CORS]: Cross-origin resource sharing

- __And more ...__

    ---

    All legacy package managers such as [pip][5], [PDM][6], [Poetry][7],
    [Conda][8] and [Mamba][9] can also benefit from Mahoraga. To configure them,
    please refer to their own docs.

</div>

## Features
<div class="grid cards" markdown>

- :material-scale-balance:{ .lg .middle }　__Proxy load balancing__

    ---

    Client requests are passed to the upstream server with the least total
    response time and least number of active connections.

- :octicons-cache-16:{ .lg .middle }　__Lazy local cache__

    ---

    Files with known SHA-256 checksums are validated and cached upon the first
    request. No configuration required.

    *[SHA-256]: Secure Hash Algorithm 256-bit

- :simple-condaforge:{ .lg .middle }　__[CEP 16][10] sharded conda repodata__

    ---

    Receive latest Conda package updates with minimal network traffic.
    Automatically updated every hour.
    [:octicons-arrow-right-24: Configuration][11]

> :simple-anaconda:{ .lg .middle }　__Conda-PyPI mapping__
>
> ---
>
> Coming soon ...

</div>

[1]: https://docs.astral.sh/uv/
[2]: https://pixi.sh/latest/
[3]: https://pixi.sh/latest/#available-software
[4]: https://pyodide.org/en/stable/
[5]: https://pip.pypa.io/en/stable/
[6]: https://pdm-project.org/en/latest/
[7]: https://python-poetry.org/
[8]: https://docs.conda.io/projects/conda/en/stable/
[9]: https://mamba.readthedocs.io/en/latest/
[10]: https://conda.org/learn/ceps/cep-0016/
[11]: https://github.com/hingebase/mahoraga/blob/v{{ mahoraga_version }}/src/mahoraga/_cli/mahoraga.toml.jinja#L48-L58
