# Tutorial
## Installation
It's recommended to install Mahoraga with [uv][1]:
``` sh
uv tool install -U mahoraga
```
!!! note

    Installing Mahoraga requires uv version 0.9.0 or later.
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

For better performance, you can set up another server (for example [Nginx][11])
in front of Mahoraga. Packages cached on disk can be served within that server,
so that subsequent requests won't go to Mahoraga again. You can find the
following Nginx configuration files in `~/.mahoraga/nginx`:

- `nginx.conf`: Top-level configuration file for direct use.
- `mahoraga.conf`: A snippet intended to be included in the `http`
  ^[:octicons-link-external-16:][12]^ block of another file.

!!! note

    The `nginx` package from Anaconda is outdated and unmaintained.
    Please install nginx with the system-level package manager for your
    operating system, or compile it from source.
To start the Nginx server, simply run `nginx -c ~/.mahoraga/nginx/nginx.conf`.
When configuring the clients, make sure they don't communicate with Mahoraga
directly, but through Nginx.
## Client Configuration
!!! note

    Mahoraga serves on `{{ mahoraga_base_url }}` by default. Replace it with the
    actual URL exposed to your clients.
### uv
!!! note

    Mirror configuration requires uv version 0.9.10 or later.
To install or update [uv][1] on a client machine, download and run the
standalone installer:
=== "Linux/macOS"

    ``` sh
    curl -LsSf {{ mahoraga_base_url }}/uv/uv-installer.sh |
        env UV_DOWNLOAD_URL="{{ mahoraga_base_url }}/uv" sh
    ```

=== "Windows"

    ``` powershell title="PowerShell"
    $Env:UV_DOWNLOAD_URL = "{{ mahoraga_base_url }}/uv"
    irm {{ mahoraga_base_url }}/uv/uv-installer.ps1 | iex
    ```

!!! note

    `uv self update` is unsupported due to
    [this issue^:octicons-link-external-16:^][13].
uv can be configured to grab PyPI packages and Python itself from Mahoraga,
via either environment variables or a [config file][15]:
=== ".profile"

    ``` sh
    export UV_PYTHON_DOWNLOADS_JSON_URL={{ mahoraga_base_url }}/uv/python-downloads.json
    export UV_PYTHON_INSTALL_MIRROR={{ mahoraga_base_url }}/python-build-standalone
    export UV_DEFAULT_INDEX={{ mahoraga_base_url }}/pypi/simple
    export UV_HTTP_TIMEOUT=60
    ```
    !!! note

        Cache-Control override can only be set via config file.

=== "profile.ps1"

    ``` powershell
    $Env:UV_PYTHON_DOWNLOADS_JSON_URL = "{{ mahoraga_base_url }}/uv/python-downloads.json"
    $Env:UV_PYTHON_INSTALL_MIRROR = "{{ mahoraga_base_url }}/python-build-standalone"
    $Env:UV_DEFAULT_INDEX = "{{ mahoraga_base_url }}/pypi/simple"
    $Env:UV_HTTP_TIMEOUT = "60"
    ```
    !!! note

        Cache-Control override can only be set via config file.

=== "uv.toml"

    ``` toml
    python-downloads-json-url = "{{ mahoraga_base_url }}/uv/python-downloads.json"
    python-install-mirror = "{{ mahoraga_base_url }}/python-build-standalone"

    [[index]]
    url = "{{ mahoraga_base_url }}/pypi/simple"
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
    python-downloads-json-url = "{{ mahoraga_base_url }}/uv/python-downloads.json"
    python-install-mirror = "{{ mahoraga_base_url }}/python-build-standalone"

    [[tool.uv.index]]
    url = "{{ mahoraga_base_url }}/pypi/simple"
    default = true

    # Mahoraga inherits upstream response headers.
    # Override them in case an upstream mirror doesn't implement cache control.
    cache-control = { api = "max-age=600", files = "max-age=365000000, immutable" }
    ```
    !!! note

        Timeout can only be set via environment variable.

Upgrading or downgrading uv to a specific version is not directly supported,
however a small shell trick can work:
=== "Linux/macOS"

    ``` sh
    alias uv='uvx uv@0.9.10'
    ```

=== "Windows"

    ``` powershell title="PowerShell"
    function uv {
        uvx 'uv@0.9.10' @args
    }
    ```

### Pixi
!!! note

    Mirror configuration requires Pixi version 0.43.1 or later.
It's recommended to enable [sharded repodata][6] in [Mahoraga configuration][7]
if you use [Pixi][5] or any other tools for the conda ecosystem.  
There is no mirror for the standalone installer of Pixi as of now. Instead, we
provide a Python script which can be executed by uv:
``` sh
uv run {{ mahoraga_base_url }}/static/get_pixi.py {{ mahoraga_base_url }}
```
By default, the script installs the latest version of Pixi to `PIXI_HOME`
[^:octicons-link-external-16:^][14], replacing any existed version. To specify a
version, pass it via CLI arguments:
``` sh
-v '0.43.1'  # Exact version
-v '0.43.*'  # Latest revision of a specific minor version
-v '>=0.43.1,<1'  # Version range
```
The script respects environment variables `PIXI_HOME` and `PIXI_CACHE_DIR`
[^:octicons-link-external-16:^][14] if present.

Once Pixi is installed, run the following command to configure it:
=== "Stable"

    ``` sh
    pixi config set -g mirrors '{
        "https://conda.anaconda.org/": ["{{ mahoraga_base_url }}/conda/"],
        "https://pypi.org/simple/": ["{{ mahoraga_base_url }}/pypi/simple/"]
    }'
    ```

=== "Experimental PyPI mappings support"

    ``` sh
    pixi config set -g mirrors '{
        "https://conda.anaconda.org/": ["{{ mahoraga_base_url }}/conda/"],
        "https://pypi.org/simple/": ["{{ mahoraga_base_url }}/pypi/simple/"],
        "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files/": ["{{ mahoraga_base_url }}/parselmouth/"],
        "https://conda-mapping.prefix.dev/": ["{{ mahoraga_base_url }}/parselmouth/"]
    }'
    ```

After that, you can install conda packages like [rattler-build][8] with Pixi.
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
Additionally, if you are using Nginx, uncomment all blocks in your
`mahoraga.conf` like this:
``` nginx title="mahoraga.conf"
# if ($http_origin) {
#     add_header Access-Control-Allow-Origin *;
# }
```
The frontend configuration depends on the library you directly use:
=== "Pyodide"

    ``` html hl_lines="6 13-22 24"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script type="text/javascript" src="{{ mahoraga_base_url }}/pyodide/v{{ pyodide_py_version }}/full/pyodide.js"></script>
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
            micropip.set_index_urls("{{ mahoraga_base_url }}/pypi/simple/{package_name}/?micropip=1");
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
        <script type="module" src="{{ mahoraga_base_url }}/npm/@pyscript/core@0/dist/core.js"></script>
        <link rel="stylesheet" href="{{ mahoraga_base_url }}/npm/@pyscript/core@0/dist/core.css">
      </head>
      <body>
        <script type="py" config='{
          "index_urls": ["{{ mahoraga_base_url }}/pypi/simple/{package_name}/?micropip=1"],
          "interpreter": "{{ mahoraga_base_url }}/pyodide/v{{ pyodide_py_version }}/full/pyodide.mjs",
          "packages": ["your_package"]
        }'># Your Python code here</script>
      </body>
    </html>
    ```

=== "Stlite"

    ``` html hl_lines="6 11 14 16-17"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no">
        <link rel="stylesheet" href="{{ mahoraga_base_url }}/npm/@stlite/browser@0/build/stlite.css">
      </head>
      <body>
        <div id="root"></div>
        <script type="module">
          import { mount } from "{{ mahoraga_base_url }}/npm/@stlite/browser@0/build/stlite.js";
          mount(
            {
              pyodideUrl: "{{ mahoraga_base_url }}/pyodide/v{{ pyodide_py_version }}/full/pyodide.js",
              requirements: [
                "{{ mahoraga_base_url }}/pypi/packages/py3/b/blinker/blinker-{{ blinker_version }}-py3-none-any.whl",
                "{{ mahoraga_base_url }}/pypi/packages/py3/t/tenacity/tenacity-{{ tenacity_version }}-py3-none-any.whl",
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
    curl -O {{ mahoraga_base_url }}/python/pymanager/python-manager-{{ pymanager_version }}.msix
    ```

=== "Legacy versions"

    ``` powershell
    curl -O {{ mahoraga_base_url }}/python/pymanager/python-manager-{{ pymanager_version }}.msi
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
[7]: https://github.com/hingebase/mahoraga/blob/v0.3.1/src/mahoraga/_cli/mahoraga.toml.jinja#L48-L58
[8]: https://rattler.build/latest/
[9]: #pixi
[10]: https://pyodide.org/en/stable/
[11]: https://nginx.org/
[12]: https://nginx.org/en/docs/http/ngx_http_core_module.html#http
[13]: https://github.com/astral-sh/uv/issues/16519
[14]: https://pixi.sh/latest/reference/environment_variables/#configurable-environment-variables
[15]: https://docs.astral.sh/uv/reference/storage/#configuration-directories
