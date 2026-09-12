# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

# /// script
# dependencies = ["py-rattler >=0.26.0"]
# requires-python = ">=3.14"
# ///

"""Install Pixi.

For details, see https://hingebase.github.io/mahoraga/tutorial.html#pixi
"""

import argparse
import asyncio
import ctypes.wintypes
import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
import warnings
from pathlib import Path

import rattler.exceptions

if sys.platform == "win32":
    import winreg

    def _update_path(pixi_bin_dir: Path) -> bool:
        # https://github.com/prefix-dev/pixi/blob/main/install/install.ps1
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            access=winreg.KEY_ALL_ACCESS,
        ) as key:
            try:
                value, type_ = winreg.QueryValueEx(key, "PATH")
            except FileNotFoundError:
                winreg.SetValueEx(
                    key,
                    "PATH",
                    0,
                    winreg.REG_EXPAND_SZ,
                    str(pixi_bin_dir),
                )
            else:
                for entry in str(value).split(os.pathsep):
                    try:
                        skip = pixi_bin_dir.samefile(entry)
                    except FileNotFoundError:
                        continue
                    if skip:
                        return False
                winreg.SetValueEx(
                    key,
                    "PATH",
                    0,
                    type_,
                    f"{pixi_bin_dir};{value}".strip(os.pathsep),
                )
        ctypes.CFUNCTYPE(
            ctypes.wintypes.LPARAM,
            ctypes.wintypes.HWND,
            ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM,
            ctypes.c_wchar_p,
            ctypes.wintypes.UINT,
            ctypes.wintypes.UINT,
            ctypes.c_void_p,
        )(("SendMessageTimeoutW", ctypes.windll.user32))(
            0xffff,  # HWND_BROADCAST
            0x1a,  # WM_SETTINGCHANGE
            0,
            "Environment",
            0x0002,  # SMTO_ABORTIFHUNG
            5000,
            None,
        )
        return True
else:
    def _update_path(pixi_bin_dir: Path) -> bool:
        # https://github.com/prefix-dev/pixi/blob/main/install/install.sh
        match Path(os.getenv("SHELL", "sh")).name:
            case "bash":
                file = "~/.bashrc"
                line = f'export PATH="{pixi_bin_dir}:$PATH"\n'
            case "fish":
                file = "~/.config/fish/config.fish"
                line = f'set -gx PATH "{pixi_bin_dir}" $PATH\n'
            case "tcsh":
                file = "~/.tcshrc"
                line = f"set path = ( {pixi_bin_dir} $path )\n"
            case "zsh":
                file = "~/.zshrc"
                line = f'export PATH="{pixi_bin_dir}:$PATH"\n'
            case _:
                warnings.warn(
                    "Could not detect shell type. Please permanently "
                    f"add '{pixi_bin_dir}' to your $PATH to enable the"
                    " 'pixi' command.",
                    stacklevel=2,
                )
                return False
        cfg = Path(file).expanduser()
        cfg.parent.mkdir(parents=True, exist_ok=True)
        try:
            f = cfg.open("x", encoding="utf-8")
        except FileExistsError:
            with cfg.open("r+", encoding="utf-8") as f:
                if line in f:
                    return False
                f.writelines(("\n", line))
        else:
            with f:
                f.writelines(("\n", line))
        return True


async def _find_pixi(
    specs: list[rattler.MatchSpec],
    gateway: rattler.Gateway,
) -> list[rattler.RepoDataRecord]:
    virtual_packages = rattler.VirtualPackage.detect()
    try:
        return await rattler.solve(
            sources=["conda-forge"],
            specs=specs,
            gateway=gateway,
            virtual_packages=virtual_packages,
        )
    except rattler.exceptions.SolverError:
        if sys.platform.startswith("darwin"):
            for vp in virtual_packages:
                gvp = vp.into_generic()
                if gvp.name.normalized == "__osx":
                    if gvp.version < rattler.Version("11.0"):
                        # Pixi >=0.74 are broken on macOS <11 due to
                        # https://github.com/conda/rattler/pull/2591
                        specs.append(rattler.MatchSpec("pixi <=0.73.0"))
                        return await rattler.solve(
                            sources=["https://prefix.dev/github-releases"],
                            specs=specs,
                            gateway=gateway,
                            virtual_packages=virtual_packages,
                        )
                    break
        raise


async def _install_pixi(
    target_prefix: os.PathLike[str],
    client: rattler.Client,
    specs: list[rattler.MatchSpec],
) -> None:
    await rattler.install(
        await _find_pixi(specs, rattler.Gateway(client=client)),
        target_prefix,
        show_progress=False,
        client=client,
        requested_specs=[
            spec._match_spec  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
            for spec in specs
        ],
    )


def _main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "version",
        nargs="?",
        default="*",
        type=rattler.VersionSpec,
        help="Pixi version",
    )
    version = parser.parse_args().version

    paths = rattler.Config.config_search_paths("pixi")
    config = rattler.Config.load_from_locations(
        [p for p in paths if p[0].is_file()],
    )
    if not config.mirrors:
        message = (
            "Mirrors not configured. Please follow the instructions at "
            "https://hingebase.github.io/mahoraga/tutorial.html#uv"
        )
        raise RuntimeError(message)
    client = rattler.Client.from_config(config)
    specs = [rattler.MatchSpec(f"pixi {version}", strict=True)]
    pixi_home = paths[-1][0].parent
    asyncio.run(_install_pixi(pixi_home, client, specs))
    pixi_bin_dir = pixi_home / "bin"
    if pixi := shutil.which("pixi", path=pixi_bin_dir):
        # Hide workspace information
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            subprocess.run([pixi, "info"], cwd=tmp, check=True)  # ruff: ignore[subprocess-without-shell-equals-true]
        if not os.getenv("PIXI_NO_PATH_UPDATE") and _update_path(pixi_bin_dir):
            message = "Please restart your shell to use Pixi"
            sep = "=" * len(message)
            print(sep, message, sep, sep="\n")  # ruff: ignore[print]
        return
    # Most likely a permisson error if reaching here
    # For conciseness, error handling is omitted
    raise OSError


if __name__ == "__main__":
    _main()
