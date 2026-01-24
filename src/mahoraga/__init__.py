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

"""There is no public Python API, please use the CLI instead."""

__all__ = []

import importlib.metadata
import multiprocessing as mp
from typing import TYPE_CHECKING, cast

import dask.config

if TYPE_CHECKING:
    from pydantic import JsonValue

__version__ = importlib.metadata.version("mahoraga")

if mp.parent_process() is None:
    def _disable_dask_distributed_logging_config() -> None:
        match cfg := cast("dict[str, JsonValue]", dask.config.config):
            case {
                "distributed": {"logging-file-config": _, **ori} | {**ori},
            }:
                ori["logging"] = {"version": 1}
                cfg["distributed"] = ori
            case _:
                cfg["distributed"] = {"logging": {"version": 1}}

    _disable_dask_distributed_logging_config()
