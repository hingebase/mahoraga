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
# dependencies = [
#     "platformdirs >=4.10.1,<5.0.0",
#     "tomlkit >=0.15.0,<0.16.0",
# ]
# requires-python = ">=3.14"
# ///

"""Configure uv, Pixi and other rattler-based tools.

For details, see https://hingebase.github.io/mahoraga/tutorial.html#uv
"""

import argparse
import os
import sys
from pathlib import Path
from typing import cast

import tomlkit.items
from platformdirs import user_config_path
from platformdirs.windows import (
    _KNOWN_FOLDER_GUIDS,  # pyright: ignore[reportPrivateUsage]  # ruff: ignore[import-private-name]
    get_win_folder_via_ctypes,
)

_KNOWN_FOLDER_GUIDS["CSIDL_PROFILE"] = "{5E6C858F-0E22-4760-9AFE-EA3317B67173}"


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
    url: str = parser.parse_args().mahoraga_base_url
    mahoraga_base_url = url.rstrip("/")
    for config_file in _pixi_config_file(), _rattler_config_file():
        _update_rattler_config(config_file, mahoraga_base_url)
    _update_uv_config(mahoraga_base_url)


def _pixi_config_file() -> Path:
    # Pixi merges configurations from multiple locations.
    # We only need to touch the config file of the highest priority.
    # https://pixi.prefix.dev/latest/reference/pixi_configuration/
    if pixi_home := os.getenv("PIXI_HOME"):
        return Path(pixi_home, "config.toml")

    if sys.platform == "win32":
        # https://github.com/prefix-dev/pixi/blob/v0.80.0/crates/pixi_config/src/lib.rs#L219
        # https://docs.rs/dirs/latest/dirs/fn.home_dir.html
        home = Path(get_win_folder_via_ctypes("CSIDL_PROFILE"))
    else:
        home = Path.home()
    return home / ".pixi/config.toml"


def _rattler_config_file() -> Path:
    if rattler_home := os.getenv("RATTLER_HOME"):
        return Path(rattler_home, "config.toml")

    if sys.platform == "darwin":
        # `$XDG_CONFIG_HOME/rattler/config.toml` has lower priority than
        # `$HOME/Library/Application Support/rattler/config.toml`
        backup = os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        backup = None
    try:
        return user_config_path("rattler", roaming=True) / "config.toml"
    finally:
        if backup:
            os.environ["XDG_CONFIG_HOME"] = backup


def _update_rattler_config(config_file: Path, mahoraga_base_url: str) -> None:
    try:
        f = config_file.open("r+", encoding="utf-8")
    except OSError:
        data = {
            "mirrors": {
                "https://conda.anaconda.org/": [f"{mahoraga_base_url}/conda/"],
                "https://pypi.org/simple/": [
                    f"{mahoraga_base_url}/pypi/simple/",
                ],
                "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files/":
                    [f"{mahoraga_base_url}/parselmouth/compressed-v0/"],
                "https://conda-mapping.prefix.dev/": [
                    f"{mahoraga_base_url}/parselmouth/",
                ],
            },
        }
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("w", encoding="utf-8") as f:
            tomlkit.dump(data, f)
    else:
        with f:
            doc = tomlkit.load(f)
            try:
                mirrors = doc["mirrors"]
            except KeyError:
                doc["mirrors"] = {
                    "https://conda.anaconda.org/": [
                        f"{mahoraga_base_url}/conda/",
                    ],
                    "https://pypi.org/simple/": [
                        f"{mahoraga_base_url}/pypi/simple/",
                    ],
                    "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files/":
                        [f"{mahoraga_base_url}/parselmouth/compressed-v0/"],
                    "https://conda-mapping.prefix.dev/": [
                        f"{mahoraga_base_url}/parselmouth/",
                    ],
                }
            else:
                _update_rattler_mirrors(mirrors, mahoraga_base_url)
            f.seek(0)
            tomlkit.dump(doc, f)
            f.truncate()


def _update_rattler_mirrors(
    mirrors: tomlkit.items.Table,
    mahoraga_base_url: str,
) -> None:
    while True:
        for k in mirrors:
            if k.startswith((
                "https://conda.anaconda.org",
                "https://pypi.org",
                "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files",
                "https://conda-mapping.prefix.dev",
            )):
                del mirrors[k]
                break
        else:
            break
    mirrors["https://conda.anaconda.org/"] = [f"{mahoraga_base_url}/conda/"]
    mirrors["https://pypi.org/simple/"] = [f"{mahoraga_base_url}/pypi/simple/"]
    mirrors[
        "https://raw.githubusercontent.com/prefix-dev/parselmouth/main/files/"
    ] = [f"{mahoraga_base_url}/parselmouth/compressed-v0/"]
    mirrors["https://conda-mapping.prefix.dev/"] = [
        f"{mahoraga_base_url}/parselmouth/",
    ]


def _update_uv_config(mahoraga_base_url: str) -> None:
    uv_config = _uv_config_file()
    try:
        f = uv_config.open("r+", encoding="utf-8")
    except OSError:
        data = {
            "python-downloads-json-url":
                f"{mahoraga_base_url}/uv/python-downloads.json",
            "python-install-mirror":
                f"{mahoraga_base_url}/python-build-standalone",
            "index": [
                {
                    "url": f"{mahoraga_base_url}/pypi/simple",
                    "default": True,
                    "cache-control": {
                        "api": "max-age=600",
                        "files": "max-age=365000000, immutable",
                    },
                },
            ],
        }
        uv_config.parent.mkdir(parents=True, exist_ok=True)
        with uv_config.open("w", encoding="utf-8") as f:
            tomlkit.dump(data, f)
    else:
        with f:
            doc = tomlkit.load(f)
            doc["python-downloads-json-url"] = (
                f"{mahoraga_base_url}/uv/python-downloads.json"
            )
            doc["python-install-mirror"] = (
                f"{mahoraga_base_url}/python-build-standalone"
            )
            try:
                indexes = doc["index"]
            except KeyError:
                doc["index"] = [
                    {
                        "url": f"{mahoraga_base_url}/pypi/simple",
                        "default": True,
                        "cache-control": {
                            "api": "max-age=600",
                            "files": "max-age=365000000, immutable",
                        },
                    },
                ]
            else:
                _update_uv_index(indexes, mahoraga_base_url)
            f.seek(0)
            tomlkit.dump(doc, f)
            f.truncate()


def _update_uv_index(
    indexes: tomlkit.items.AoT,
    mahoraga_base_url: str,
) -> None:
    prefix = f"{mahoraga_base_url}/"
    while True:
        for i, index in enumerate(indexes):  # pyright: ignore[reportUnknownVariableType]
            if cast("str", index["url"]).startswith(prefix):
                indexes.pop(i)
                break
        else:
            break
    for index in indexes:  # pyright: ignore[reportUnknownVariableType]
        if cast("dict[str, object]", index).get("default", False):
            del index["default"]
    indexes.append({  # pyright: ignore[reportUnknownMemberType]
        "url": f"{mahoraga_base_url}/pypi/simple",
        "default": True,
        "cache-control": {
            "api": "max-age=600",
            "files": "max-age=365000000, immutable",
        },
    })


def _uv_config_file() -> Path:
    # Ignore default locations if UV_CONFIG_FILE is present
    # https://docs.rs/uv/0.12.13/src/uv/lib.rs.html#312-321
    if config_file := os.getenv("UV_CONFIG_FILE"):
        return Path(config_file)

    # uv relys on `etcetera` when locating config files
    # https://docs.rs/uv-dirs/0.0.80/src/uv_dirs/lib.rs.html#116-120
    # Handle the differences between `etcetera` and `platformdirs` here
    match sys.platform:
        case "darwin":
            # https://docs.rs/etcetera/0.11.0/src/etcetera/base_strategy/xdg.rs.html#194-196
            if "XDG_CONFIG_HOME" not in os.environ:
                return Path.home() / ".config/uv/uv.toml"
        case "win32":
            # https://docs.rs/etcetera/0.11.0/src/etcetera/base_strategy/windows.rs.html#190-196
            if appdata := os.getenv("APPDATA"):
                return Path(appdata, "uv", "uv.toml")
        case _:
            pass

    return user_config_path("uv", roaming=True) / "uv.toml"


if __name__ == "__main__":
    _main()
