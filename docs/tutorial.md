# Tutorial
## Installation
It's recommended to install Mahoraga with [uv][1]:
``` sh
uv tool install -U mahoraga
```
## Server Configuration
Before starting Mahoraga, you need to initialize a directory (for example
`~/.mahoraga`) to hold its configuration and data:
``` sh
uvx mahoraga new ~/.mahoraga
```
The default configuration may not be suitable for you. View and edit it with
any text editor you like:
``` sh
uvx pyvim ~/.mahoraga/mahoraga.toml
```
Inline documentations can be found inside the file.
!!! note

    Running `uvx` without `uv tool install` will result in a full installation
    every time you run the tool. See [uv tool][2] documentation for details.
## Server Deployment
Start the server directly to check if your configuration is correct:
``` sh
cd ~/.mahoraga
uvx mahoraga run
```
Logs will appear in the console as well as `~/.mahoraga/log/mahoraga.log`.
If the server started successfully, you can [configure your clients][3] and try
fetching some packages from Mahoraga. Then if everything goes well, press
++ctrl+c++ to stop the server, and start it again in the background:
=== "Linux/macOS"

    ``` sh
    uvx mahoraga run &>/dev/null &
    ```

=== "Windows"

    ```
    uvw tool run mahoraga run
    ```
    !!! note

        Command `uvw` requires uv version 0.7.9 or later.

For better performance, you can set up another server (for example Nginx) in
front of Mahoraga. Packages cached on disk can be served within that server,
so that subsequent requests won't go to Mahoraga again. In a future version,
`mahoraga new` will generate Nginx configuration files out of the box.
## Client Configuration
!!! note

    Mahoraga serves on `http://127.0.0.1:3450` by default. Replace it with the
    actual URL exposed to your clients.
### uv
!!! note

    Mirror configuration requires uv version 0.8.5 or later.
[uv][1] can be configured to grab PyPI packages and Python itself from Mahoraga,
via either environment variables or a config file:
=== ".profile"

    ``` sh
    export UV_PYTHON_INSTALL_MIRROR=http://127.0.0.1:3450/python-build-standalone
    export UV_DEFAULT_INDEX=http://127.0.0.1:3450/pypi/simple
    export UV_HTTP_TIMEOUT=60
    ```
    !!! note

        Cache-Control override can only be set via config file.

=== "profile.ps1"

    ``` powershell
    $Env:UV_PYTHON_INSTALL_MIRROR = "http://127.0.0.1:3450/python-build-standalone"
    $Env:UV_DEFAULT_INDEX = "http://127.0.0.1:3450/pypi/simple"
    $Env:UV_HTTP_TIMEOUT = "60"
    ```
    !!! note

        Cache-Control override can only be set via config file.

=== "uv.toml"

    ``` toml
    python-install-mirror = "http://127.0.0.1:3450/python-build-standalone"

    [[index]]
    url = "http://127.0.0.1:3450/pypi/simple"
    default = true

    # Mahoraga inherits upstream response headers.
    # Override them in case an upstream mirror doesn't implement cache control.
    cache-control = { api = "max-age=600", files = "max-age=365000000, immutable" }
    ```
    !!! note

        Timeout can only be set via environment variable.

=== "pyproject.toml"

    ``` toml
    [tool.uv]
    python-install-mirror = "http://127.0.0.1:3450/python-build-standalone"

    [[tool.uv.index]]
    url = "http://127.0.0.1:3450/pypi/simple"
    default = true

    # Mahoraga inherits upstream response headers.
    # Override them in case an upstream mirror doesn't implement cache control.
    cache-control = { api = "max-age=600", files = "max-age=365000000, immutable" }
    ```
    !!! note

        Timeout can only be set via environment variable.

To receive latest Python updates, you should always update uv to latest version.
However, `uv self update` cannot make use of Mahoraga. You can update uv by
either `uv tool install -U uv` or [Pixi][5].
### Pixi
!!! note

    Mirror configuration requires Pixi version 0.43.1 or later.
Pixi mirror configuration can be done in a single command:
=== "Packages only"

    ``` sh
    pixi config set -g mirrors '{
        "https://conda.anaconda.org/": ["http://127.0.0.1:3450/conda/"],
        "https://pypi.org/simple/": ["http://127.0.0.1:3450/pypi/simple/"]
    }'
    ```

=== "Packages and PyPI mappings (Experimental)"

    ``` sh
    pixi config set -g mirrors '{
        "https://conda.anaconda.org/": ["http://127.0.0.1:3450/conda/"],
        "https://pypi.org/simple/": ["http://127.0.0.1:3450/pypi/simple/"],
        "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files/": ["http://127.0.0.1:3450/parselmouth/"],
        "https://conda-mapping.prefix.dev/": ["http://127.0.0.1:3450/parselmouth/"]
    }'
    ```

It's recommended to enable [sharded repodata][6] in [Mahoraga configuration][7]
if you use Pixi or [rattler-build][8].  
Similar to uv, `pixi self-update` cannot utilize Mahoraga. Furthermore,
`pixi global` prevents any tool to be exposed as `pixi`, so you'll need to give
it an alias if you update Pixi in this way. Alternatively,
`pixi exec --force-reinstall pixi` works as of now.
### rattler-build
!!! note

    Mirror configuration requires rattler-build version 0.41.0 or later.
rattler-build accepts the same config file format as Pixi. Pass the Pixi config
file [modified above][9] to rattler-build, unless there are options you would
not like to share between Pixi and rattler-build.
=== "Linux/macOS"

    ``` sh
    rattler-build build \
        --config-file "${PIXI_HOME:-"$HOME/.pixi"}/config.toml" \
        ...
    ```

=== "Windows"

    ``` powershell title="PowerShell 7"
    rattler-build build `
        --config-file "$($Env:PIXI_HOME ?? "$HOME/.pixi")/config.toml" `
        ...
    ```

### Pyodide
!!! note

    Mirror configuration requires Pyodide version 0.28.0 or later.
[Pyodide][10] Python distribution, wheels and JavaScript/WebAssembly runtime are
all available in Mahoraga. To enable them, add the following line to your
`mahoraga.toml`:
``` toml title="mahoraga.toml" hl_lines="3"
[cors]
allow-origins = [
    "*",
]
```
The frontend configuration depends on the library you directly use:
=== "Pyodide"

    ``` html hl_lines="6 13-22 24"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <script type="text/javascript" src="http://127.0.0.1:3450/pyodide/v0.28.0/full/pyodide.js"></script>
      </head>
      <body>
        <script type="text/javascript">
          async function main() {
            let pyodide = await loadPyodide();
            await pyodide.loadPackage("micropip");
            // Prefer Pyodide-maintained wheels over PyPI ones
            // If this is not desired, remove the following lines
            pyodide.runPython(`
                import micropip
                class _Transaction(micropip.transaction.Transaction):
                    def __post_init__(self):
                        super().__post_init__()
                        self.search_pyodide_lock_first = True
                micropip.package_manager.Transaction = _Transaction
            `);
            const micropip = pyodide.pyimport("micropip");
            micropip.set_index_urls("http://127.0.0.1:3450/pypi/simple/{package_name}/?micropip=1");
            await micropip.install(["your_package"]);
            pyodide.runPython(`# Your Python code here`);
          }
          main();
        </script>
      </body>
    </html>
    ```

=== "PyScript"

    ``` html hl_lines="6 7 11 12"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script type="module" src="http://127.0.0.1:3450/npm/@pyscript/core@0/dist/core.js"></script>
        <link rel="stylesheet" href="http://127.0.0.1:3450/npm/@pyscript/core@0/dist/core.css">
      </head>
      <body>
        <script type="py" config='{
          "index_urls": ["http://127.0.0.1:3450/pypi/simple/{package_name}/?micropip=1"],
          "interpreter": "http://127.0.0.1:3450/pyodide/v0.28.0/full/pyodide.mjs",
          "packages": ["your_package"]
        }'># Your Python code here</script>
      </body>
    </html>
    ```

=== "Stlite"

    ``` html hl_lines="6 11 14 16-19"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
        <link rel="stylesheet" href="http://127.0.0.1:3450/npm/@stlite/browser@0/build/stlite.css">
      </head>
      <body>
        <div id="root"></div>
        <script type="module">
          import { mount } from "http://127.0.0.1:3450/npm/@stlite/browser@0/build/stlite.js";
          mount(
            {
              pyodideUrl: "http://127.0.0.1:3450/pyodide/v{{ pyodide_py_version }}/full/pyodide.js",
              requirements: [
                // Stlite doesn't expose the `index_urls` option,
                // hence the absolute wheel urls here
                "http://127.0.0.1:3450/pypi/packages/py3/b/blinker/blinker-{{ blinker_version }}-py3-none-any.whl",
                "http://127.0.0.1:3450/pypi/packages/py3/t/tenacity/tenacity-{{ tenacity_version }}-py3-none-any.whl",
              ],
              entrypoint: "your_app.py",
              files: {
                "your_app.py": `# Your Python code here`,
              },
            },
            document.getElementById("root"),
          );
        </script>
      </body>
    </html>
    ```

### pymanager
The next generation of the official Python installer for Windows,
[pymanager][4], can be downloaded from Mahoraga:
=== "Windows 10 21H2 (Windows Server 2022) or later"

    ``` powershell
    curl -O http://127.0.0.1:3450/python/pymanager/python-manager-{{ pymanager_version }}.msix
    ```

=== "Legacy versions"

    ``` powershell
    curl -O http://127.0.0.1:3450/python/pymanager/python-manager-{{ pymanager_version }}.msi
    ```

!!! note

    Support for the command `pymanager install` hasn't been implemented in
    Mahoraga yet.

[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/guides/tools/
[3]: #client-configuration
[4]: https://docs.python.org/dev/using/windows.html#python-install-manager
[5]: https://pixi.sh/latest/
[6]: https://conda.org/learn/ceps/cep-0016/
[7]: #server-configuration
[8]: https://rattler.build/latest/
[9]: #pixi
[10]: https://pyodide.org/en/stable/
