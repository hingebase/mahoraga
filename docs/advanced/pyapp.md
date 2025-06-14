# Build standalone executable with PyApp
[PyApp][1] is a tool for distributing Python applications to end users who have
no Python experience. In this topic, we are going to build a standalone
executable of Mahoraga with PyApp, utilizing a running Mahoraga instance.
The Mahoraga executable can be copied to another machine, and will help you set
up Python development environment efficiently.
!!! note

    Mahoraga serves on `http://127.0.0.1:3450` by default. Replace it with the
    actual URL exposed to your clients.
## Prerequisites
- A running Mahoraga server which we have set up in the previous [tutorial][2].
- [uv][3] and [Pixi][4] should be available in your `PATH` and should have been
  configured according to the [tutorial][2]. If you have only one of them, fetch
  the other from Mahoraga now:

    === "Fetch Pixi with uv"

        ``` sh
        uv run get_pixi.py
        ```
        ??? note "get_pixi.py"

            ``` py
            # /// script
            # dependencies = [
            #   "py-rattler >=0.9.0",
            # ]
            # requires-python = ">=3.8"
            # ///

            import asyncio
            import shutil
            import os

            import rattler.networking


            async def main():
                client = rattler.Client([
                    rattler.networking.MirrorMiddleware({
                        "https://conda.anaconda.org/": ["http://127.0.0.1:3450/conda/"],
                    }),
                ])
                records = await rattler.solve(
                    channels=["conda-forge"],
                    specs=["pixi >=0.43.1"],
                    gateway=rattler.Gateway(
                        default_config=rattler.SourceConfig(sharded_enabled=True),
                        client=client,
                    ),
                )
                target_prefix = os.path.expanduser("~/.pixi")
                await rattler.install(records, target_prefix, client=client)
                if pixi := shutil.which("pixi", path=os.path.join(target_prefix, "bin")):
                    print(os.path.normcase(pixi))
                else:
                    raise FileNotFoundError("pixi")


            if __name__ == "__main__":
                asyncio.run(main())
            ```

    === "Fetch uv with Pixi"

        ``` sh
        pixi global install uv
        ```
        !!! note

            Pixi exposes `uv` as a [trampoline][5]. Use `uv run which uv` to
            retrieve the actual path.

- Xcode/MSVC toolchain if you are using macOS/Windows. If you don't need the
  Xcode/VS IDE, just install [Xcode Command Line Tools][6] or
  [Microsoft C++ Build Tools][7].
- Other dependencies (for example Rust) are managed by Pixi, so they don't
  require explicit installation here.
## Build steps
PyApp doesn't recognize uv packages from PyPI or Anaconda, as a result we have
to manually link the uv executable to PyApp cache directory:

=== "Linux (x64 glibc)"

    ``` sh
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    mkdir -p ~/".cache/pyapp/uv/$PYAPP_UV_VERSION"
    ln -fnsT "$(uv run which uv)" ~/".cache/pyapp/uv/$PYAPP_UV_VERSION/uv"
    ```

=== "macOS (Apple Silicon)"

    ``` sh
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    mkdir -p ~/"Library/Caches/pyapp/uv/$PYAPP_UV_VERSION"
    ln -fns "$(uv run which uv)" ~/"Library/Caches/pyapp/uv/$PYAPP_UV_VERSION/uv"
    ```

=== "macOS (Intel)"

    ``` sh
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    mkdir -p ~/"Library/Caches/pyapp/uv/$PYAPP_UV_VERSION"
    ln -fns "$(uv run which uv)" ~/"Library/Caches/pyapp/uv/$PYAPP_UV_VERSION/uv"
    ```

=== "Windows (x64)"

    ``` powershell title="PowerShell (Run as Administrator)"
    $Env:PYAPP_UV_VERSION = $(uv -V).Substring(3)
    mkdir -ErrorAction Ignore `
        -Path $Env:LOCALAPPDATA\pyapp\cache\uv\$Env:PYAPP_UV_VERSION
    New-Item -Type SymbolicLink `
        -Value $("import shutil; print(shutil.which('uv'))" | uv.exe run -) `
        -Path $Env:LOCALAPPDATA\pyapp\cache\uv\$Env:PYAPP_UV_VERSION\uv.exe
    ```

PyApp itself cannot pack a Python environment, but we can create a Python
environment by executing an online bootstrapper.  
Make an empty directory, `cd` to it, and then build the online version of PyApp:

=== "Linux (x64 glibc)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    export PYAPP_DISTRIBUTION_SOURCE=http://127.0.0.1:3450/python-build-standalone/{{ python_build_standalone_tag }}/cpython-{{ python_version }}+{{ python_build_standalone_tag }}-x86_64_v3-unknown-linux-gnu-install_only_stripped.tar.gz
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_UV_ENABLED=1
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    pixi exec -s gcc_linux-64 -s rust cargo install --no-track --root . pyapp
    PYAPP_INSTALL_DIR_MAHORAGA=temp UV_PYTHON=temp/python/bin/python3 bin/pyapp
    ```

=== "macOS (Apple Silicon)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    export PYAPP_DISTRIBUTION_SOURCE=http://127.0.0.1:3450/python-build-standalone/{{ python_build_standalone_tag }}/cpython-{{ python_version }}+{{ python_build_standalone_tag }}-aarch64-apple-darwin-install_only_stripped.tar.gz
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_UV_ENABLED=1
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    pixi exec -s rust cargo install --no-track --root . pyapp
    PYAPP_INSTALL_DIR_MAHORAGA=temp UV_PYTHON=temp/python/bin/python3 bin/pyapp
    ```

=== "macOS (Intel)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    export PYAPP_DISTRIBUTION_SOURCE=http://127.0.0.1:3450/python-build-standalone/{{ python_build_standalone_tag }}/cpython-{{ python_version }}+{{ python_build_standalone_tag }}-x86_64-apple-darwin-install_only_stripped.tar.gz
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_UV_ENABLED=1
    export PYAPP_UV_VERSION="$(uv -V | awk '{ print $2 }')"
    pixi exec -s rust cargo install --no-track --root . pyapp
    PYAPP_INSTALL_DIR_MAHORAGA=temp UV_PYTHON=temp/python/bin/python3 bin/pyapp
    ```

=== "Windows (x64)"

    ``` powershell title="PowerShell"
    $Env:PYAPP_PROJECT_NAME = "mahoraga"
    $Env:PYAPP_PROJECT_VERSION = "{{ mahoraga_version }}"
    $Env:PYAPP_DISTRIBUTION_SOURCE = "http://127.0.0.1:3450/python/{{ python_version }}/python-{{ python_version }}-embed-amd64.zip"
    $Env:PYAPP_FULL_ISOLATION = "1"
    $Env:PYAPP_UV_ENABLED = "1"
    $Env:PYAPP_UV_VERSION = $(uv -V).Substring(3)
    pixi exec -s rust cargo install --no-track --root . pyapp
    $Env:PYAPP_INSTALL_DIR_MAHORAGA = "temp"
    bin/pyapp
    ```

`pyapp` will fail to run since we didn't set `PYAPP_DISTRIBUTION_PATH_PREFIX`
on Unix and didn't remove `python{{ python_version_short }}._pth` on Windows.
That doesn't matter since we have already get the Python environment. Pack it
with maximum compression rate:

=== "Linux (x64 glibc)"

    ``` sh
    pixi exec -s tar -s zstd tar -cf temp.tar.zst -C temp/python \
        --use-compress-program "zstd --ultra -22" .
    ```

=== "macOS (Apple Silicon)"

    ``` sh
    pixi exec -s zstd tar -cf temp.tar.zst -C temp/python \
        --use-compress-program "zstd --ultra -22" .
    ```

=== "macOS (Intel)"

    ``` sh
    pixi exec -s zstd tar -cf temp.tar.zst -C temp/python \
        --use-compress-program "zstd --ultra -22" .
    ```

=== "Windows (x64)"

    ``` powershell title="PowerShell"
    rm temp/python{{ python_version_short }}._pth
    pixi exec -s zstd tar -cf temp.tar.zst -C temp -I "zstd --ultra -22" .
    ```

Pass the tarball to PyApp again, and we will finally get the desired offline
executable:

=== "Linux (x64 glibc)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    export -n PYAPP_DISTRIBUTION_SOURCE
    export PYAPP_DISTRIBUTION_PYTHON_PATH=bin/python3
    export PYAPP_DISTRIBUTION_PATH=~+/temp.tar.zst
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_SKIP_INSTALL=1
    pixi exec -s gcc_linux-64 -s rust cargo install --no-track --root offline pyapp
    mv offline/bin/pyapp mahoraga
    ```

=== "macOS (Apple Silicon)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    unset PYAPP_DISTRIBUTION_SOURCE
    export PYAPP_DISTRIBUTION_PYTHON_PATH=bin/python3
    export PYAPP_DISTRIBUTION_PATH=~+/temp.tar.zst
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_SKIP_INSTALL=1
    pixi exec -s rust cargo install --no-track --root offline pyapp
    mv offline/bin/pyapp mahoraga
    ```

=== "macOS (Intel)"

    ``` sh
    export PYAPP_PROJECT_NAME=mahoraga
    export PYAPP_PROJECT_VERSION={{ mahoraga_version }}
    unset PYAPP_DISTRIBUTION_SOURCE
    export PYAPP_DISTRIBUTION_PYTHON_PATH=bin/python3
    export PYAPP_DISTRIBUTION_PATH=~+/temp.tar.zst
    export PYAPP_FULL_ISOLATION=1
    export PYAPP_SKIP_INSTALL=1
    pixi exec -s rust cargo install --no-track --root offline pyapp
    mv offline/bin/pyapp mahoraga
    ```

=== "Windows (x64)"

    ``` powershell title="PowerShell"
    $Env:PYAPP_PROJECT_NAME = "mahoraga"
    $Env:PYAPP_PROJECT_VERSION = "{{ mahoraga_version }}"
    $Env:PYAPP_DISTRIBUTION_SOURCE = ""
    $Env:PYAPP_DISTRIBUTION_PYTHON_PATH = "python.exe"
    $Env:PYAPP_DISTRIBUTION_PATH = Convert-Path temp.tar.zst
    $Env:PYAPP_FULL_ISOLATION = "1"
    $Env:PYAPP_SKIP_INSTALL = "1"
    pixi exec -s rust cargo install --no-track --root offline pyapp
    mv offline/bin/pyapp.exe mahoraga.exe
    ```

That's it. You can run this `mahoraga` on either the same machine or another
one, and it will work as expected.

[1]: https://ofek.dev/pyapp/latest/
[2]: ../tutorial.md
[3]: https://docs.astral.sh/uv/
[4]: https://pixi.sh/latest/
[5]: https://pixi.sh/latest/global_tools/introduction/#trampolines
[6]: https://developer.apple.com/library/archive/technotes/tn2339/_index.html
[7]: https://visualstudio.microsoft.com/visual-cpp-build-tools/
