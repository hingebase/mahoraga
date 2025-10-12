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

"""Client-side patch for `panel` to work along with `mahoraga`."""

import dataclasses
import importlib.abc
import importlib.util
import sys
import types  # noqa: TC003
from importlib.machinery import ModuleSpec  # noqa: TC003
from typing import override


def monkey_patch(cdn: str = "http://127.0.0.1:3450/") -> None:
    """Patch `panel` to use a custom CDN.

    Raises:
        RuntimeError: `panel` has been imported before patching.

    """
    for name in "panel", "panel.io":
        if name in sys.modules:
            message = "%r has been imported"
            raise RuntimeError(message % name)
        sys.modules[name] = importlib.util.module_from_spec(_find_spec(name))
    name = "panel.io.resources"
    try:
        spec = _find_spec(name)
    finally:
        del sys.modules["panel.io"], sys.modules["panel"]
    spec.loader = loader = _PatchLoader(spec.loader, cdn)
    sys.modules[name] = module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)


@importlib.util.LazyLoader.factory  # pyright: ignore[reportArgumentType]
@dataclasses.dataclass
class _PatchLoader(importlib.abc.Loader):
    loader: importlib.abc.InspectLoader
    cdn: str

    @override
    def create_module(self, spec: ModuleSpec) -> types.ModuleType | None:
        return self.loader.create_module(spec)

    @override
    def exec_module(self, module: types.ModuleType) -> None:
        code = self.loader.get_code(module.__name__)
        if not code:
            message = "cannot load module %r when get_code() returns None"
            raise ImportError(message % module.__name__)
        consts = tuple(
            f"{self.cdn.rstrip('/')}/npm/@holoviz/panel@"
            if x == "https://cdn.holoviz.org/panel/" else x
            for x in code.co_consts
        )
        exec(code.replace(co_consts=consts), module.__dict__)  # noqa: S102


def _find_spec(name: str) -> ModuleSpec:
    if spec := importlib.util.find_spec(name):
        return spec
    message = "No module named %r"
    raise ModuleNotFoundError(message % name, name=name)
