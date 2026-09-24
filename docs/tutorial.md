# Tutorial
## Installation
It's recommended to install Mahoraga with [uv][1] >=0.9.0:
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
!!! info "Note"

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

For better performance, you can set up a non-Python server in front of Mahoraga.
Packages cached on disk can be served within that server, so that subsequent
requests won't go to Mahoraga again.
We provide configuration files for [Nginx][11] and [Caddy][6] out-of-the-box.
=== "Nginx"

    You can find the following Nginx configuration files in `~/.mahoraga/nginx`:

    - `nginx.conf`: Top-level configuration file for direct use.
    - `mahoraga.conf`: A snippet intended to be included in the `http`
      ^[:octicons-link-external-16:][12]^ block of another file.

    !!! info "Note"

        For Linux and macOS, Nginx is available in conda-forge and can be
        installed by [Pixi][5]:
        ``` sh
        pixi global install nginx
        ```
    To start the Nginx server, run `nginx -c ~/.mahoraga/nginx/nginx.conf`.

=== "Caddy"

    You can find the Caddy configuration file at `~/.mahoraga/Caddyfile`. As the
    name suggests, it can be used as the top-level configuration file directly.
    In addition, it's also a valid snippet when imported to the root of another
    `Caddyfile`, since it doesn't contain a [global options block][13].

    !!! info "Note"

        Caddy is available in conda-forge and can be installed by [Pixi][5]:
        ``` sh
        pixi global install caddy
        ```
    To start the Caddy server, run `cd ~/.mahoraga && caddy run`.

When configuring the clients, make sure they don't communicate with Mahoraga
directly, but through Nginx or Caddy.
## Client Configuration
!!! info "Note"

    Mahoraga serves on `{{ mahoraga_base_url }}` by default. Replace it with the
    actual URL exposed to your clients.
### uv
To get started on your client machine, install [uv][1] >=0.9.10 if you haven't
got it elsewhere:
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

When upgrading uv installed in this way, run the same command again. We don't
support `uv self update` at this moment.  
Run the following script to let Mahoraga take over the requests from uv, Pixi
and other [Rattler][7]-based tools. You can also download, view and edit the
script before executing it.
=== "Linux/macOS"

    ```sh
    UV_PYTHON_INSTALL_MIRROR={{ mahoraga_base_url }}/python-build-standalone \
        uv run --default-index {{ mahoraga_base_url }}/pypi/simple \
        {{ mahoraga_base_url }}/static/client_config.py \
        {{ mahoraga_base_url }}
    ```

=== "Windows"

    ``` powershell title="PowerShell"
    $Env:UV_PYTHON_INSTALL_MIRROR = "{{ mahoraga_base_url }}/python-build-standalone"
    uv run --default-index {{ mahoraga_base_url }}/pypi/simple `
        {{ mahoraga_base_url }}/static/client_config.py `
        {{ mahoraga_base_url }}
    ```

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
!!! info "Note"

    This section is about [Pixi][5] installation. If you already have
    Pixi >=0.43.1 installed, you can skip it since Pixi configuration was done
    in the previous section.
There is no mirror for the standalone installer of Pixi as of now.
Instead, run the following script to install Pixi when you have uv installed
and configured:
``` sh
uv run {{ mahoraga_base_url }}/static/get_pixi.py
```
By default, the script installs the latest version of Pixi to `PIXI_HOME`
^[:octicons-link-external-16:][8]^, replacing any existed version, and prepend
`$PIXI_HOME/bin` to your `PATH`. To specify a version, pass it as CLI
argument:
``` sh
get_pixi.py '0.43.1'  # Exact version
get_pixi.py '0.43.*'  # Latest revision of a specific minor version
get_pixi.py '>=0.43.1,<1'  # Version range
```
The script respects the environment variable `PIXI_NO_PATH_UPDATE`
^[:octicons-link-external-16:][9]^ if present.  
### Pyodide
!!! info "Note"

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
Additionally, if you are using Nginx or Caddy, uncomment all blocks in your
`mahoraga.conf` or `Caddyfile` like this:
=== "Nginx"

    ``` nginx title="mahoraga.conf"
    # if ($http_origin) {
    #     add_header Access-Control-Allow-Origin *;
    # }
    ```

=== "Caddy"

    ``` title="Caddyfile"
    # header @mahoraga-has-origin Access-Control-Allow-Origin *
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

    ``` html hl_lines="6 11 14 16-18"
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, shrink-to-fit=no">
        <link rel="stylesheet" href="{{ mahoraga_base_url }}/npm/@stlite/browser@1/build/stlite.css">
      </head>
      <body>
        <div id="root"></div>
        <script type="module">
          import { mount } from "{{ mahoraga_base_url }}/npm/@stlite/browser@1/build/stlite.js";
          mount(
            {
              pyodideUrl: "{{ mahoraga_base_url }}/pyodide/v{{ pyodide_py_version }}/full/pyodide.js",
              requirements: [
                "{{ mahoraga_base_url }}/pypi/packages/py3/b/blinker/blinker-{{ blinker_version }}-py3-none-any.whl",
                "{{ mahoraga_base_url }}/pypi/packages/py3/i/itsdangerous/itsdangerous-{{ itsdangerous_version }}-py3-none-any.whl",
                "{{ mahoraga_base_url }}/pypi/packages/py3/p/python-multipart/python_multipart-{{ python_multipart_version }}-py3-none-any.whl",
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

!!! info "Note"

    Support for the command `pymanager install` hasn't been implemented in
    Mahoraga yet.

[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/guides/tools/
[3]: #client-configuration
[4]: https://docs.python.org/dev/using/windows.html#python-install-manager
[5]: https://pixi.prefix.dev/latest/
[6]: https://caddyserver.com/
[7]: https://github.com/conda/rattler
[8]: https://pixi.prefix.dev/latest/reference/environment_variables/#configurable-environment-variables
[9]: https://pixi.prefix.dev/latest/installation/#installer-script-options
[10]: https://pyodide.org/en/stable/
[11]: https://nginx.org/
[12]: https://nginx.org/en/docs/http/ngx_http_core_module.html#http
[13]: https://caddyserver.com/docs/caddyfile/concepts#global-options
