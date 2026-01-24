# QUANTCONNECT.COM - Democratizing Finance, Empowering Individuals.
# Lean CLI v1.0. Copyright 2021 QuantConnect Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Dict, List

from lean.components.util.logger import Logger
from lean.models.json_module import JsonModule
from lean.models.logger import Option


def build_and_configure_modules(
    target_modules: List[str],
    module_list: List[JsonModule],
    organization_id: str,
    lean_config: Dict[str, Any],
    properties: Dict[str, Any],
    logger: Logger,
    environment_name: str,
    module_version: str,
):
    """Builds and configures the given modules

    :param target_modules: the requested modules
    :param module_list: the available modules
    :param organization_id: the organization id
    :param lean_config: the current lean configs
    :param properties: the user provided arguments
    :param logger: the logger instance
    :param environment_name: the environment name to use
    :param module_version: The version of the module to install. If not provided, the latest version will be installed.
    """
    for target_module_name in target_modules:
        module = non_interactive_config_build_for_name(
            lean_config,
            target_module_name,
            module_list,
            properties,
            logger,
            environment_name,
        )
        # Ensures extra modules (not brokerage or data feeds) are installed.
        module.ensure_module_installed(organization_id, module_version)
        lean_config["environments"][environment_name].update(module.get_settings())


def non_interactive_config_build_for_name(
    lean_config: Dict[str, Any],
    target_module_name: str,
    module_list: List[JsonModule],
    properties: Dict[str, Any],
    logger: Logger,
    environment_name: str = None,
) -> JsonModule:
    return config_build_for_name(
        lean_config,
        target_module_name,
        module_list,
        properties,
        logger,
        interactive=False,
        environment_name=environment_name,
    )


def find_module(
    target_module_name: str, module_list: List[JsonModule], logger: Logger
) -> JsonModule:
    target_module: JsonModule = None
    # because we compare str we normalize everything to lower case
    target_module_name = target_module_name.lower()
    module_class_name = target_module_name.rfind(".")
    for module in module_list:
        # we search in the modules name and id
        module_id = module.get_id().lower()
        module_name = module.get_name().lower()

        if module_id == target_module_name or module_name == target_module_name:
            target_module = module
            break
        else:
            if (
                module_class_name != -1
                and module_id == target_module_name[module_class_name + 1 :]
                or module_name == target_module_name[module_class_name + 1 :]
            ):
                target_module = module
                break

    if not target_module:
        for module in module_list:
            # we search in the modules configuration values, this is for when the user provides an environment
            if (
                module.is_value_in_config(target_module_name)
                or module_class_name != -1
                and module.is_value_in_config(
                    target_module_name[module_class_name + 1 :]
                )
            ):
                target_module = module
        if not target_module:
            raise RuntimeError(
                f"""Failed to resolve module for name: '{target_module_name}'"""
            )
    logger.debug(f"Found module '{target_module_name}' from given name")
    return target_module


def config_build_for_name(
    lean_config: Dict[str, Any],
    target_module_name: str,
    module_list: List[JsonModule],
    properties: Dict[str, Any],
    logger: Logger,
    interactive: bool,
    environment_name: str = None,
) -> JsonModule:
    target_module = find_module(target_module_name, module_list, logger)
    target_module.config_build(
        lean_config,
        logger,
        interactive=interactive,
        properties=properties,
        environment_name=environment_name,
    )
    _update_settings(logger, environment_name, target_module, lean_config)
    return target_module


def interactive_config_build(
    lean_config: Dict[str, Any],
    models: [JsonModule],
    logger: Logger,
    user_provided_options: Dict[str, Any],
    show_secrets: bool,
    select_message: str,
    multiple: bool,
    environment_name: str = None,
) -> [JsonModule]:
    """Interactively configures the brokerage to use.

    :param lean_config: the LEAN configuration that should be used
    :param models: the modules to choose from
    :param logger: the logger to use
    :param user_provided_options: the dictionary containing user provided options
    :param show_secrets: whether to show secrets on input
    :param select_message: the user facing selection message
    :param multiple: true if multiple selections are allowed
    :param environment_name: the target environment name
    :return: the brokerage the user configured
    """
    options = [Option(id=b, label=b.get_name()) for b in models]

    modules: [JsonModule] = []
    if multiple:
        modules = logger.prompt_list(select_message, options, multiple=True)
    else:
        module = logger.prompt_list(select_message, options, multiple=False)
        modules.append(module)

    for module in modules:
        module.config_build(
            lean_config,
            logger,
            interactive=True,
            properties=user_provided_options,
            hide_input=not show_secrets,
            environment_name=environment_name,
        )
        _update_settings(logger, environment_name, module, lean_config)
    if multiple:
        return modules
    return modules[-1]


def _update_settings(logger, environment_name: str, target: dict, lean_config: dict):
    """
    Load environment properties for `environment_name` and update the module settings (`target`)
    in a robust way.

    Defensive behavior:
      - Skip None values.
      - Treat string "None", "null" and "" as empty.
      - Support Python lists, JSON arrays, comma-separated lists and single scalar strings.
      - Merge list-like keys preserving order and uniqueness.
    """
    import json
    from json import loads

    # helper to get property value from lean_config/environment
    def _get_env_properties():
        try:
            if not isinstance(lean_config, dict):
                return {}
            envs = lean_config.get("environments", {})
            env_block = envs.get(environment_name, {}) if environment_name else {}
            return (
                env_block.get("properties", {}) if isinstance(env_block, dict) else {}
            )
        except Exception:
            return {}

    env_props = _get_env_properties()

    # keys that are expected to hold list-like values and should be merged
    list_like_keys = [
        "data-queue-handler",
        # add additional list-like keys here if needed
    ]

    for key, value in env_props.items():
        # skip explicit None Python value
        if value is None:
            logger.debug(f"_update_settings: skipping {key}=None")
            continue

        # If the key is not present in target, set it directly
        if key not in target:
            target[key] = value
            logger.debug(f"_update_settings: assigned {key} -> {value!r}")
            continue

        # If the setting is expected to be list-like, try to merge
        if key in list_like_keys:
            parsed_value = None

            # already-Python list/tuple -> use as-is
            if isinstance(value, (list, tuple)):
                parsed_value = list(value)
                logger.debug(
                    f"_update_settings: property {key} is Python list/tuple -> {parsed_value!r}"
                )
            else:
                # treat empty-ish strings as empty list
                if isinstance(value, str) and value.strip() in ("", "None", "null"):
                    parsed_value = []
                    logger.debug(
                        f"_update_settings: property {key} contains explicit empty-ish value -> treat as []"
                    )
                else:
                    # attempt JSON parse for strings
                    if isinstance(value, str):
                        try:
                            parsed_value = loads(value)
                            # coerce non-list JSON (e.g. "A") into list
                            if not isinstance(parsed_value, list):
                                parsed_value = [parsed_value]
                            logger.debug(
                                f"_update_settings: parsed JSON for {key} -> {parsed_value!r}"
                            )
                        except Exception:
                            # fallback: comma-separated values
                            if "," in value:
                                parsed_value = [
                                    v.strip() for v in value.split(",") if v.strip()
                                ]
                                logger.debug(
                                    f"_update_settings: fallback CSV-split for {key} -> {parsed_value!r}"
                                )
                            else:
                                # single non-json scalar string -> coerce to list
                                parsed_value = [value]
                                logger.debug(
                                    f"_update_settings: coerced non-json scalar for {key} -> {parsed_value!r}"
                                )
                    else:
                        # unknown non-string/non-list value: try to coerce into list
                        try:
                            parsed_value = list(value)
                            logger.debug(
                                f"_update_settings: coerced iterable for {key} -> {parsed_value!r}"
                            )
                        except Exception:
                            parsed_value = [value]
                            logger.debug(
                                f"_update_settings: coerced fallback for {key} -> {parsed_value!r}"
                            )

            # ensure parsed_value is a list
            if parsed_value is None:
                parsed_value = []

            existing = list(target.get(key) or [])
            # preserve order, unique
            merged = list(dict.fromkeys(existing + parsed_value).keys())
            target[key] = merged
            logger.debug(f"_update_settings: merged {key} -> {merged!r}")
            continue

        # Non-list-like keys: overwrite with environment property
        target[key] = value
        logger.debug(f"_update_settings: overwritten {key} -> {value!r}")
