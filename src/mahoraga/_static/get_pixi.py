# Copyright 2025-2026 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# /// script
# dependencies = ["py-rattler >=0.20.0"]
# requires-python = ">=3.14"
# ///

"""Install Pixi.

For details, see https://hingebase.github.io/mahoraga/tutorial.html#pixi
"""

import argparse
import asyncio
import os
import shutil
from pathlib import Path
from typing import NoReturn

import rattler.networking
import rattler.rattler


async def _install_pixi(
    target_prefix: os.PathLike[str],
    cache_dir: os.PathLike[str] | None,
    mahoraga_base_url: str,
    version: rattler.VersionSpec,
) -> None:
    specs = [rattler.MatchSpec(f"pixi {version}", strict=True)]
    client = rattler.Client([
        rattler.networking.MirrorMiddleware({
            "https://conda.anaconda.org/": [
                mahoraga_base_url.rstrip("/") + "/conda/",
            ],
        }),
    ])
    records = await rattler.solve(
        channels=["conda-forge"],
        specs=specs,
        gateway=rattler.Gateway(cache_dir, client=client),
        virtual_packages=rattler.VirtualPackage.detect(),
    )
    await _rattler_install(
        records,
        target_prefix,
        cache_dir,
        show_progress=False,
        client=client,
        requested_specs=specs,
    )


def _main() -> NoReturn:
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

    # https://pixi.sh/latest/reference/environment_variables/#configurable-environment-variables
    pixi_home = _pixi_home()
    cache_dir = _pixi_cache_dir()

    asyncio.run(
        _install_pixi(
            pixi_home,
            cache_dir,
            args.mahoraga_base_url,
            args.version,
        ),
    )
    pixi_home = pixi_home.resolve(strict=True)
    if pixi := shutil.which("pixi", path=pixi_home / "bin"):
        os.environ["PIXI_HOME"] = str(pixi_home)
        if cache_dir:
            os.environ["PIXI_CACHE_DIR"] = str(cache_dir.resolve(strict=True))
        os.execv(pixi, ("pixi", "info"))  # noqa: S606

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


def _pixi_home() -> Path:
    if pixi_home := os.getenv("PIXI_HOME"):
        return Path(pixi_home)
    return Path.home() / ".pixi"


async def _rattler_install(  # noqa: PLR0913, PLR0917
    records: list[rattler.RepoDataRecord],
    target_prefix: str | os.PathLike[str],
    cache_dir: os.PathLike[str] | None = None,
    installed_packages: list[rattler.PrefixRecord] | None = None,
    reinstall_packages: set[str] | None = None,
    ignored_packages: set[str] | None = None,
    platform: rattler.Platform | None = None,
    execute_link_scripts: bool = False,  # noqa: FBT001, FBT002
    show_progress: bool = True,  # noqa: FBT001, FBT002
    client: rattler.Client | None = None,
    requested_specs: list[rattler.MatchSpec] | None = None,
) -> None:
    await rattler.rattler.py_install(  # pyright: ignore[reportUnknownMemberType]
        records=records,
        target_prefix=str(target_prefix),
        cache_dir=cache_dir,
        installed_packages=installed_packages,
        reinstall_packages=reinstall_packages,
        ignored_packages=ignored_packages,
        platform=platform and platform._inner,  # noqa: SLF001  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
        client=client and client._client,  # noqa: SLF001  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
        execute_link_scripts=execute_link_scripts,
        show_progress=show_progress,
        requested_specs=requested_specs and [
            spec._match_spec  # noqa: SLF001  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
            for spec in requested_specs
        ],
    )


if __name__ == "__main__":
    _main()
