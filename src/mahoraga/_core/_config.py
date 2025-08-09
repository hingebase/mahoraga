# Copyright 2025 hingebase

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__all__ = ["Config", "Predicate", "Server"]

import asyncio
import functools
import ipaddress
import itertools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Annotated, Literal, override

import annotated_types as at
import pydantic
import pydantic_settings
import rattler.networking
import rattler.platform

try:
    import uvloop  # pyright: ignore[reportMissingImports]
except ImportError:
    uvloop = None

Predicate = functools.singledispatch(at.Predicate)


@Predicate.register
def _(func: str) -> at.Predicate:
    def wrapper(input_value: object, /) -> bool:
        return eval(func, {"input_value": input_value})  # noqa: S307
    wrapper.__qualname__ = func
    return at.Predicate(wrapper)


_model_config: pydantic.ConfigDict = {
    "alias_generator": lambda x: x.replace("_", "-"),
}


class Server(pydantic.BaseModel, **_model_config):
    host: Annotated[
        ipaddress.IPv4Address,
        pydantic.Field(description="The host to serve on"),
    ] = ipaddress.IPv4Address("127.0.0.1")
    port: Annotated[
        pydantic.PositiveInt,
        pydantic.Field(description="The TCP port to serve on"),
        at.Le(65535),
    ] = 3450
    keep_alive: Annotated[
        pydantic.PositiveInt,
        pydantic.Field(description="Time in seconds to wait before closing "
                                   "idle connections"),
    ] = 5

    def rattler_client(self) -> rattler.Client:
        return _rattler_client(self.host, self.port)


class _HttpUrl(pydantic.AnyUrl):
    _constraints = pydantic.UrlConstraints(
        max_length=1900,
        allowed_schemes=["http", "https"],
        host_required=True,
    )


class _Log(pydantic.BaseModel):
    level: Literal["debug", "info", "warning", "error", "critical"] = "info"
    access: bool = True


class _CORS(pydantic.BaseModel, **_model_config):
    allow_origins: list[str] = []
    allow_methods: list[str] = ["GET"]
    allow_headers: list[str] = []
    allow_credentials: bool = False
    allow_origin_regex: str | None = None
    expose_headers: list[str] = []
    max_age: pydantic.NonNegativeInt = 600


_adapter = pydantic.TypeAdapter(list[_HttpUrl])


class _Conda(pydantic.BaseModel, **_model_config):
    default: list[_HttpUrl] = _adapter.validate_python([
        "https://conda.anaconda.org/",
    ])
    with_label: dict[str, str | list[_HttpUrl]] = {
        "nvidia": _adapter.validate_python([
            "https://mirrors.sustech.edu.cn/anaconda-extra/cloud/",
        ]),
    }
    without_label: dict[str, str | list[_HttpUrl]] = {
        "auto": _adapter.validate_python([
            "https://mirror.nju.edu.cn/anaconda/cloud/",
            "https://mirror.nyist.edu.cn/anaconda/cloud/",
            "https://mirrors.cqupt.edu.cn/anaconda/cloud/",
            "https://mirrors.hit.edu.cn/anaconda/cloud/",
            "https://mirrors.lzu.edu.cn/anaconda/cloud/",
            "https://mirrors.pku.edu.cn/anaconda/cloud/",
            "https://mirrors.shanghaitech.edu.cn/anaconda/cloud/",
            "https://mirrors.sustech.edu.cn/anaconda/cloud/",
            "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/",
        ]),
        "biobakery": "auto",
        "bioconda": _adapter.validate_python([
            "https://mirror.nju.edu.cn/anaconda/cloud/",
            "https://mirror.nyist.edu.cn/anaconda/cloud/",
            "https://mirrors.cqupt.edu.cn/anaconda/cloud/",
            "https://mirrors.hit.edu.cn/anaconda/cloud/",
            "https://mirrors.lzu.edu.cn/anaconda/cloud/",
            "https://mirrors.pku.edu.cn/anaconda/cloud/",
            "https://mirrors.shanghaitech.edu.cn/anaconda/cloud/",
            "https://mirrors.sustech.edu.cn/anaconda/cloud/",
            "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/",
            "https://prefix.dev/",
        ]),
        "c4aarch64": "auto",
        "caffe2": "auto",
        "conda-forge": "bioconda",
        "deepmodeling": "auto",
        "dglteam": "auto",
        "emscripten-forge-dev": "nvidia",
        "fastai": "auto",
        "fermi": "auto",
        "idaholab": "auto",
        "matsci": "auto",
        "menpo": "auto",
        "MindSpore": "auto",
        "mordred-descriptor": "auto",
        "msys2": "auto",
        "numba": "auto",
        "nvidia": _adapter.validate_python([
            "https://prefix.dev/",
        ]),
        "ohmeta": "auto",
        "omnia": "auto",
        "Paddle": "auto",
        "peterjc123": "auto",
        "plotly": "auto",
        "psi4": "auto",
        "pytorch": "bioconda",
        "pytorch-lts": "auto",
        "pytorch-test": "auto",
        "pytorch3d": "auto",
        "pyviz": "auto",
        "qiime2": "auto",
        "rapidsai": "bioconda",
        "rdkit": "auto",
        "robostack": "nvidia",
        "robostack-humble": "nvidia",
        "robostack-jazzy": "nvidia",
        "robostack-noetic": "nvidia",
        "robostack-staging": "nvidia",
        "simpleitk": "auto",
        "speleo3": "auto",
        "stackless": "auto",
        "ursky": "auto",
    }


class _PyPI(pydantic.BaseModel):
    html: list[_HttpUrl] = _adapter.validate_python([
        "https://mirror.nju.edu.cn/pypi/web/",
        "https://mirrors.aliyun.com/pypi/web/",
        "https://mirrors.cloud.tencent.com/pypi/",
        "https://mirrors.huaweicloud.com/repository/pypi/",
        "https://mirrors.neusoft.edu.cn/pypi/web/",
        "https://mirrors.pku.edu.cn/pypi/web/",
        "https://mirrors.qlu.edu.cn/pypi/web/",
        "https://mirrors.sustech.edu.cn/pypi/web/",
    ])
    json_: Annotated[list[_HttpUrl], pydantic.Field(alias="json")] = (
        _adapter.validate_python([
            "https://mirrors.bfsu.edu.cn/pypi/web/",
            "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/",
            "https://pypi.org/",
        ])
    )

    def all(self) -> Iterator[_HttpUrl]:
        return itertools.chain(self.html, self.json_)


class _Upstream(pydantic.BaseModel, **_model_config):
    conda: _Conda = _Conda()
    pyodide: list[_HttpUrl] = _adapter.validate_python([
        "https://cdn.jsdelivr.net/",
        "https://fastly.jsdelivr.net/",
        "https://gcore.jsdelivr.net/",
        "https://originfastly.jsdelivr.net/",
        "https://quantil.jsdelivr.net/",
        "https://testingcf.jsdelivr.net/",
    ])
    pypi: _PyPI = _PyPI()
    python: list[_HttpUrl] = _adapter.validate_python([
        "https://cdn.npmmirror.com/binaries/python/{version}/{name}",
        "https://mirror.bjtu.edu.cn/python/{version}/{name}",
        "https://mirror.nju.edu.cn/python/{version}/{name}",
        "https://mirrors.aliyun.com/python-release/windows/{name}",
        "https://mirrors.huaweicloud.com/python/{version}/{name}",
        "https://mirrors.ustc.edu.cn/python/{version}/{name}",
        "https://www.python.org/ftp/python/{version}/{name}",
    ])
    python_build_standalone: list[_HttpUrl] = _adapter.validate_python([
        "https://mirror.nju.edu.cn/github-release/astral-sh/python-build-standalone/",
        "https://mirrors.lzu.edu.cn/github-release/astral-sh/python-build-standalone/",
        "https://cdn.npmmirror.com/binaries/python-build-standalone/",
        "https://pycdn-2025-03-02.oss-cn-shanghai.aliyuncs.com/mirror/astral-sh/python-build-standalone/",
        "https://github.com/astral-sh/python-build-standalone/releases/download/",
    ])
    backup: set[str] = {
        "conda.anaconda.org",
        "github.com",
        "prefix.dev",
        "pycdn-2025-03-02.oss-cn-shanghai.aliyuncs.com",
        "pypi.org",
        "www.python.org",
    }


class Config(
    pydantic_settings.BaseSettings,
    toml_file="mahoraga.toml",
    **_model_config,
):
    server: Server = Server()
    log: _Log = _Log()
    shard: dict[str, set[rattler.platform.PlatformLiteral]] = {}
    cors: _CORS = _CORS()
    upstream: _Upstream = _Upstream()
    eager_task_execution: bool = False

    def loop_factory(self) -> asyncio.AbstractEventLoop:
        if uvloop and not TYPE_CHECKING:
            loop = uvloop.new_event_loop()
        else:
            loop = asyncio.SelectorEventLoop()
        if self.eager_task_execution:
            loop.set_task_factory(asyncio.eager_task_factory)
        return loop

    @override
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        return (pydantic_settings.TomlConfigSettingsSource(settings_cls),)


@functools.lru_cache(maxsize=1)
def _rattler_client(host: ipaddress.IPv4Address, port: int) -> rattler.Client:
    if host.is_unspecified:
        host = ipaddress.IPv4Address("127.0.0.1")
    return rattler.Client([
        rattler.networking.MirrorMiddleware({
            "https://conda.anaconda.org/": [
                str(_HttpUrl(f"http://{host}:{port}/conda/")),
            ],
        }),
    ])
