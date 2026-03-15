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
# dependencies = ["py-rattler ==0.22.0"]
# requires-python = ">=3.14"
# ///

"""Install Pixi.

For details, see https://hingebase.github.io/mahoraga/tutorial.html#pixi
"""

import argparse
import asyncio
import ctypes.wintypes
import json
import os
import shutil
import subprocess  # noqa: S404
import sys
import tempfile
import warnings
from pathlib import Path

import rattler.networking

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


async def _install_pixi(
    target_prefix: os.PathLike[str],
    cache_dir: os.PathLike[str] | None,
    mahoraga_base_url: str,
    version: rattler.VersionSpec,
) -> dict[str, list[str]]:
    specs = [rattler.MatchSpec(f"pixi {version}", strict=True)]
    mahoraga_base_url = mahoraga_base_url.rstrip("/")
    mirrors = {
        "https://conda.anaconda.org/": [f"{mahoraga_base_url}/conda/"],
        "https://pypi.org/simple/": [f"{mahoraga_base_url}/pypi/simple/"],
    }
    client = rattler.Client([rattler.networking.MirrorMiddleware(mirrors)])
    records = await rattler.solve(
        sources=["conda-forge"],
        specs=specs,
        gateway=rattler.Gateway(cache_dir, client=client),
        virtual_packages=rattler.VirtualPackage.detect(),
    )
    await rattler.install(
        records,
        target_prefix,
        cache_dir,
        show_progress=False,
        client=client,
        requested_specs=[
            spec._match_spec  # noqa: SLF001  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
            for spec in specs
        ],
    )
    return mirrors


def _main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "mahoraga_base_url",
        nargs="?",
        default="http://127.0.0.1:3450/",
        help="\b",
    )
    parser.add_argument(
        "-v", "--version",
        default="*",
        type=rattler.VersionSpec,
        help="Pixi version",
    )
    args = parser.parse_args()

    # https://pixi.prefix.dev/latest/reference/environment_variables/#configurable-environment-variables
    pixi_home = _pixi_home()
    cache_dir = _pixi_cache_dir()

    mirrors = asyncio.run(
        _install_pixi(
            pixi_home,
            cache_dir,
            args.mahoraga_base_url,
            args.version,
        ),
    )
    pixi_home = pixi_home.resolve(strict=True)
    pixi_bin_dir = pixi_home / "bin"
    if pixi := shutil.which("pixi", path=pixi_bin_dir):
        os.environ["PIXI_HOME"] = str(pixi_home)
        if cache_dir:
            os.environ["PIXI_CACHE_DIR"] = str(cache_dir.resolve(strict=True))
        mirrors = _pixi_config_global_mirrors(pixi) | mirrors
        subprocess.run(  # noqa: S603
            [
                pixi, "config", "set", "-g",
                "mirrors", json.dumps(mirrors, separators=(",", ":")),
            ],
            check=True,
        )
        # Hide workspace information
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            subprocess.run([pixi, "info"], cwd=tmp, check=True)  # noqa: S603
        if not os.getenv("PIXI_NO_PATH_UPDATE") and _update_path(pixi_bin_dir):
            message = "Please restart your shell to use Pixi"
            sep = "=" * len(message)
            print(sep, message, sep, sep="\n")  # noqa: T201
        return
    # Most likely a permisson error if reaching here
    # For conciseness, error handling is omitted
    raise OSError


def _pixi_cache_dir() -> Path | None:
    env = os.environ
    if cache_dir := env.get("PIXI_CACHE_DIR") or env.get("RATTLER_CACHE_DIR"):
        return Path(cache_dir)
    if cache_dir := env.get("XDG_CACHE_HOME"):
        try:
            last_resort = Path(cache_dir, "pixi").resolve(strict=True)
            if last_resort.is_dir():
                return last_resort
        except OSError:
            pass
    return None


def _pixi_config_global_mirrors(pixi: str) -> dict[str, list[str]]:
    try:
        cfg = subprocess.check_output(  # noqa: S603
            [pixi, "config", "list", "-g", "--json", "mirrors"],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        return {}
    try:
        return json.loads(cfg)["mirrors"]
    except (KeyError, ValueError):
        return {}


def _pixi_home() -> Path:
    if pixi_home := os.getenv("PIXI_HOME"):
        return Path(pixi_home)
    return Path.home() / ".pixi"


if __name__ == "__main__":
    _main()
