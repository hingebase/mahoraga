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

    ``` powershell
    uvx mahoraga run >nul 2>&1
    ```
    !!! note

        `uvx` is a console application which must run with a console window.
        To hide the window completely, call the Windows API [ShowWindow][4].

For better performance, you can set up another server (for example Nginx) in
front of Mahoraga. Packages cached on disk can be served within that server,
so that subsequent requests won't go to Mahoraga again. In a future version,
`mahoraga new` will generate Nginx configuration files out of the box.
## Client Configuration
!!! note

    Mahoraga serves on `http://127.0.0.1:3450` by default. Replace it with the
    actual URL exposed to your clients.
### uv
[uv][1] can be configured to grab PyPI packages and Python itself from Mahoraga,
via either environment variables or a config file:
=== ".profile"

    ``` sh
    export UV_PYTHON_INSTALL_MIRROR=http://127.0.0.1:3450/python-build-standalone
    export UV_DEFAULT_INDEX=http://127.0.0.1:3450/pypi/simple
    export UV_HTTP_TIMEOUT=60
    ```

=== "profile.ps1"

    ``` powershell
    $Env:UV_PYTHON_INSTALL_MIRROR = "http://127.0.0.1:3450/python-build-standalone"
    $Env:UV_DEFAULT_INDEX = "http://127.0.0.1:3450/pypi/simple"
    $Env:UV_HTTP_TIMEOUT = "60"
    ```

=== "uv.toml"

    ``` toml
    python-install-mirror = "http://127.0.0.1:3450/python-build-standalone"

    [[index]]
    url = "http://127.0.0.1:3450/pypi/simple"
    default = true
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
``` sh
pixi config set -g mirrors '{
    "https://conda.anaconda.org/": ["http://127.0.0.1:3450/conda/"],
    "https://pypi.org/simple/": ["http://127.0.0.1:3450/pypi/simple/"]
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

[1]: https://docs.astral.sh/uv/
[2]: https://docs.astral.sh/uv/guides/tools/
[3]: #client-configuration
[4]: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow
[5]: https://pixi.sh/latest/
[6]: https://conda.org/learn/ceps/cep-0016/
[7]: #server-configuration
[8]: https://rattler.build/latest/
[9]: #pixi
