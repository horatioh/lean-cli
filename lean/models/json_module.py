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

from abc import ABC
from copy import copy
from enum import Enum
from typing import Any, Dict, List, Type

from click import get_current_context
from click.core import ParameterSource

from lean.components.util.auth0_helper import get_authorization
from lean.components.util.logger import Logger
from lean.constants import MODULE_CLI_PLATFORM, MODULE_PLATFORM, MODULE_TYPE
from lean.container import container
from lean.models.configuration import (
    AuthConfiguration,
    BrokerageEnvConfiguration,
    ChoiceUserInput,
    Configuration,
    InternalInputUserInput,
    PathParameterUserInput,
)

_logged_messages = set()


class JsonModule(ABC):
    """The JsonModule class is the base class extended for all json modules."""

    def __init__(
        self, json_module_data: Dict[str, Any], module_type: str, platform: str
    ) -> None:
        self._module_type: str = module_type
        self._platform: str = platform
        self._product_id: int = (
            json_module_data["product-id"] if "product-id" in json_module_data else 0
        )
        self._id: str = json_module_data["id"]
        self._display_name: str = json_module_data["display-id"]
        self._specifications_url: str = (
            json_module_data["specifications"]
            if "specifications" in json_module_data
            else None
        )
        self._installs: bool = (
            json_module_data["installs"]
            if ("installs" in json_module_data and platform == MODULE_CLI_PLATFORM)
            else False
        )
        self._lean_configs: List[Configuration] = []
        for config in json_module_data["configurations"]:
            self._lean_configs.append(Configuration.factory(config))
        self._lean_configs = self.sort_configs()
        self._is_module_installed: bool = False
        self._initial_cash_balance: LiveInitialStateInput = (
            LiveInitialStateInput(json_module_data["live-cash-balance-state"])
            if "live-cash-balance-state" in json_module_data
            else None
        )
        self._initial_holdings: LiveInitialStateInput = (
            LiveInitialStateInput(json_module_data["live-holdings-state"])
            if "live-holdings-state" in json_module_data
            else False
        )
        self._minimum_seat = (
            json_module_data["minimum-seat"]
            if "minimum-seat" in json_module_data
            else None
        )

    def get_id(self):
        return self._id

    def sort_configs(self) -> List[Configuration]:
        sorted_configs = []
        filter_configs = []
        brokerage_configs = []
        for config in self._lean_configs:
            if isinstance(config, BrokerageEnvConfiguration):
                brokerage_configs.append(config)
            else:
                if config.has_filter_dependency:
                    filter_configs.append(config)
                else:
                    sorted_configs.append(config)
        return brokerage_configs + sorted_configs + filter_configs

    def get_name(self) -> str:
        """Returns the user-friendly name which users can identify this object by.

        :return: the user-friendly name to display to users
        """
        return self._display_name

    def _check_if_config_passes_filters(
        self, config: Configuration, all_for_platform_type: bool
    ) -> bool:
        for condition in config._filter._conditions:
            if condition._dependent_config_id == MODULE_TYPE:
                target_value = self._module_type
            elif condition._dependent_config_id == MODULE_PLATFORM:
                target_value = self._platform
            else:
                if all_for_platform_type:
                    # skip, we want all configurations that match type and platform, for help
                    continue
                target_value = self.get_config_value_from_name(
                    condition._dependent_config_id
                )
            if not target_value:
                return False
            elif isinstance(target_value, dict):
                return all(condition.check(value) for value in target_value.values())
            elif not condition.check(target_value):
                return False
        return True

    def get_config_value_from_name(self, target_name: str) -> str:
        [idx] = [
            i
            for i in range(len(self._lean_configs))
            if self._lean_configs[i]._id == target_name
        ]
        return self._lean_configs[idx]._value

    def is_value_in_config(self, searched_value: str) -> bool:
        searched_value = searched_value.lower()
        for i in range(len(self._lean_configs)):
            value = self._lean_configs[i]._value
            if isinstance(value, str):
                value = value.lower()
            if isinstance(value, list):
                value = [x.lower() for x in value]

            if searched_value in value:
                return True
        return False

    def get_settings(self) -> Dict[str, str]:
        """
        Build and return settings for this module.

        Robust behavior:
        - Prefill conditional InternalInputUserInput values using any available lean_config /
        environment_name / logger from the caller via globals() if present (best-effort).
        - If a conditional can't match any option, WARN and treat it as an explicit empty value
        (do NOT raise), so non-interactive flows continue.
        - Preserve previous behavior of converting values to strings and replacing escaped newlines
        and backslashes.
        """
        settings: Dict[str, str] = {"id": self._id}

        # Try to obtain context used by previous code paths (best-effort).
        lean_config = globals().get("lean_config", None)
        environment_name = globals().get("environment_name", None)
        logger = globals().get("logger", None)

        # --- PREFILL FOR INTERNAL CONDITIONALS (best-effort) ---
        # If we have a lean_config and/or environment context, try to prefill _value for
        # InternalInputUserInput entries so option condition checks work reliably.
        try:
            for _cfg in self._lean_configs:
                if getattr(_cfg, "_value", None) is None:
                    try:
                        # Use self.get_default if available, otherwise leave as None.
                        if lean_config is not None and logger is not None:
                            _cfg._value = self.get_default(
                                lean_config, _cfg._id, environment_name, logger
                            )
                    except Exception:
                        # Prefill best-effort: ignore failures.
                        pass
        except Exception:
            # Never fail here — prefill is a convenience.
            pass
        # --- END PREFILL ---

        # Now evaluate conditional InternalInputUserInput items. If no condition matches,
        # treat as explicit empty (log a warning) to allow non-interactive usage.
        for config in self._lean_configs:
            if type(config) is InternalInputUserInput and getattr(
                config, "_is_conditional", False
            ):
                try:
                    matched = False
                    for option in getattr(config, "_value_options", []):
                        dep_id = option._condition._dependent_config_id
                        try:
                            target_value = self.get_config_value_from_name(dep_id)
                        except Exception:
                            # If we couldn't look up the dependent config, try to use prefills or None
                            target_value = getattr(
                                next(
                                    (c for c in self._lean_configs if c._id == dep_id),
                                    None,
                                ),
                                "_value",
                                None,
                            )
                        if option._condition.check(target_value):
                            config._value = option._value
                            matched = True
                            break
                    if not matched:
                        # Instead of raising (which breaks non-interactive workflows), warn and treat
                        # the config as explicitly empty so downstream code can handle it.
                        if logger is not None and hasattr(logger, "warning"):
                            logger.warning(
                                f'No condition matched among present options for "{config._id}". '
                                "Treating as explicitly empty to allow non-interactive execution."
                            )
                        else:
                            # fallback to print if no logger available
                            print(
                                f'WARNING: No condition matched among present options for "{config._id}". '
                                "Treating as explicitly empty to allow non-interactive execution."
                            )
                        config._value = "" if config._value is None else config._value
                except Exception:
                    # Never allow a conditional evaluation exception to bubble out of get_settings.
                    if logger is not None and hasattr(logger, "warning"):
                        logger.warning(
                            f'Error while evaluating conditional config "{config._id}". Treating as empty.'
                        )
                    else:
                        print(
                            f'WARNING: Error while evaluating conditional config "{config._id}".'
                        )

        # Build settings dict (respecting filters)
        for configuration in self._lean_configs:
            try:
                if not self._check_if_config_passes_filters(
                    configuration, all_for_platform_type=False
                ):
                    continue
                if isinstance(configuration, AuthConfiguration) and isinstance(
                    configuration._value, dict
                ):
                    for key, value in configuration._value.items():
                        settings[key] = str(value)
                else:
                    # Convert to string, unescape newline escapes and normalize backslashes.
                    settings[configuration._id] = (
                        (
                            ""
                            if configuration._value is None
                            else str(configuration._value)
                        )
                        .replace("\\n", "\n")
                        .replace("\\", "/")
                    )
            except Exception:
                # Skip problematic configuration entries but log if possible.
                if logger is not None and hasattr(logger, "warning"):
                    logger.warning(
                        f"Skipping config '{getattr(configuration, '_id', '<unknown>')}' due to error."
                    )
                else:
                    print(
                        f"WARNING: Skipping config '{getattr(configuration, '_id', '<unknown>')}' due to error."
                    )

        return settings

    def get_all_input_configs(
        self, filters: List[Type[Configuration]] = []
    ) -> List[Configuration]:
        return [
            copy(config)
            for config in self._lean_configs
            if config._is_required_from_user
            if not isinstance(config, tuple(filters))
            and self._check_if_config_passes_filters(config, all_for_platform_type=True)
        ]

    def convert_lean_key_to_variable(self, lean_key: str) -> str:
        """Replaces hyphens with underscore to follow python naming convention.

        :param lean_key: string that uses hyphnes as separator. Used in lean config
        """
        return lean_key.replace("-", "_")

    def convert_variable_to_lean_key(self, variable_key: str) -> str:
        """Replaces underscore with hyphens to follow lean config naming convention.

        :param variable_key: string that uses underscore as separator as per python convention.
        """
        return variable_key.replace("_", "-")

    def get_project_id(self, default_project_id: int, require_project_id: bool) -> int:
        """Retrieve the project ID, prompting the user if required and default is invalid.

        :param default_project_id: The default project ID to use.
        :param require_project_id: Flag to determine if prompting is necessary.
        :return: A valid project ID.
        """
        from click import prompt

        project_id: int = default_project_id
        if require_project_id and project_id <= 0:
            project_id = prompt(
                "Please enter any cloud project ID to proceed with Auth0 authentication",
                -1,
                show_default=False,
            )
        return project_id

    def config_build(
        self,
        lean_config: Dict[str, Any],
        logger: Logger,
        interactive: bool = True,
        user_provided_options: Dict[str, Any] = None,
        properties: Dict[str, Any] = None,
        environment_name: str = None,
        hide_input: bool = False,
    ) -> "JsonModule":
        """
        Build configuration values for this module, prompting for missing values (interactive)
        or collecting missing options for non-interactive usage.

        Defensive behavior added:
        - Accepts keys in dash-form and underscore-form from both user_provided_options and properties.
        - Treats presence of a key in `properties` (even if its value is empty string) as "explicitly provided".
        - Prefills InternalInputUserInput values before evaluating conditional options.
        - Avoids uninitialized user_choice.
        """
        from click import get_current_context

        # Normalize inputs
        user_provided_options = dict(user_provided_options or {})
        properties = dict(properties or {})

        # Helper: return a map that contains both dash and underscore variants for every key
        def _normalized_options_map(opts: Dict[str, Any]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for k, v in opts.items():
                out[k] = v
                if "-" in k:
                    out[k.replace("-", "_")] = v
                if "_" in k:
                    out[k.replace("_", "-")] = v
            return out

        user_provided_options = _normalized_options_map(user_provided_options)
        properties = _normalized_options_map(properties)

        missing_options: List[str] = []

        # Prefill InternalInputUserInput config values from lean_config so condition checks are reliable
        try:
            for _cfg in self._lean_configs:
                if getattr(_cfg, "_value", None) is None:
                    try:
                        _cfg._value = self.get_default(
                            lean_config, _cfg._id, environment_name, logger
                        )
                    except Exception:
                        pass
        except Exception:
            # defensive: do not fail if prefill errors
            pass

        for configuration in self._lean_configs:
            # skip if config filtered out
            if not self._check_if_config_passes_filters(
                configuration, all_for_platform_type=False
            ):
                continue

            user_choice = None

            # two name variants to check: original lean-key (hyphen) and python-variable (underscore)
            lean_key = configuration._id
            var_key = self.convert_lean_key_to_variable(lean_key)

            # 1) check user_provided_options (CLI) in both forms
            if (
                var_key in user_provided_options
                and user_provided_options[var_key] is not None
            ):
                user_choice = user_provided_options[var_key]
                logger.debug(
                    f"JsonModule({self._display_name}): user provided '{user_choice}' for '{var_key}'"
                )
            elif (
                lean_key in user_provided_options
                and user_provided_options[lean_key] is not None
            ):
                user_choice = user_provided_options[lean_key]
                logger.debug(
                    f"JsonModule({self._display_name}): user provided '{user_choice}' for '{lean_key}'"
                )
            else:
                # 2) check properties (these come from the environment in lean.json) — *presence* means explicitly provided
                if var_key in properties:
                    # if present in properties, use its value (can be empty string)
                    user_choice = properties[var_key]
                    logger.debug(
                        f"JsonModule({self._display_name}): property provided (from environment) '{var_key}' -> '{user_choice}'"
                    )
                elif lean_key in properties:
                    user_choice = properties[lean_key]
                    logger.debug(
                        f"JsonModule({self._display_name}): property provided (from environment) '{lean_key}' -> '{user_choice}'"
                    )
                else:
                    # 3) fallback: get default from lean_config (if any)
                    try:
                        user_choice = self.get_default(
                            lean_config, lean_key, environment_name, logger
                        )
                    except Exception:
                        user_choice = None
                    logger.debug(
                        f"JsonModule({self._display_name}): Configuration not provided '{lean_key}'"
                    )

            # Now decide whether value is "empty" and needs prompting / marking as missing
            is_empty = user_choice is None or (
                isinstance(user_choice, str) and user_choice.strip() == ""
            )

            if is_empty:
                if interactive:
                    # interactive: prompt user
                    default_value = configuration._input_default
                    user_choice = configuration.ask_user_for_input(
                        default_value, logger, hide_input=hide_input
                    )
                    if not isinstance(configuration, BrokerageEnvConfiguration):
                        try:
                            self._save_property({f"{configuration._id}": user_choice})
                        except Exception:
                            pass
                else:
                    # non-interactive: if optional, allow default; else if properties contained the key treat as explicit empty
                    if configuration._optional:
                        if configuration._input_default is not None:
                            user_choice = configuration._input_default
                    else:
                        # if the key existed in properties (even if empty) we've already assigned user_choice to that (possibly "")
                        # treat an explicitly-present-but-empty string as provided (do not mark as missing)
                        present_in_properties = (lean_key in properties) or (
                            var_key in properties
                        )
                        present_in_user_opts = (lean_key in user_provided_options) or (
                            var_key in user_provided_options
                        )

                        if present_in_properties or present_in_user_opts:
                            # keep user_choice as "" or None->"" so it's treated as explicitly provided
                            if user_choice is None:
                                user_choice = ""
                            logger.debug(
                                f"JsonModule({self._display_name}): explicit empty provided for '{lean_key}' (properties/user opts)"
                            )
                        else:
                            # genuinely missing
                            missing_options.append(f"--{lean_key}")

            # set the resolved value on configuration
            configuration._value = user_choice

        # If there are missing options in non-interactive mode, raise as before
        if len(missing_options) > 0:
            raise RuntimeError(
                f"""You are missing the following option{"s" if len(missing_options) > 1 else ""}: {", ".join(missing_options)}"""
            )

        return self

    def get_paths_to_mount(self) -> Dict[str, str]:
        return {
            config._id: config._value
            for config in self._lean_configs
            if (
                isinstance(config, PathParameterUserInput)
                and self._check_if_config_passes_filters(
                    config, all_for_platform_type=False
                )
            )
        }

    def ensure_module_installed(
        self, organization_id: str, module_version: str
    ) -> None:
        """
        Ensures that the specified module is installed. If the module is not installed, it will be installed.

        Args:
            organization_id (str): The ID of the organization where the module should be installed.
            module_version (str): The version of the module to install. If not provided,
            the latest version will be installed.

        Returns:
            None
        """
        if not self._is_module_installed and self._installs:
            container.logger.debug(
                f"JsonModule.ensure_module_installed(): installing module {self}: {self._product_id}"
            )
            container.module_manager.install_module(
                self._product_id, organization_id, module_version
            )
            self._is_module_installed = True

    def get_default(
        self,
        lean_config: Dict[str, Any],
        key: str,
        environment_name: str,
        logger: Logger,
    ):
        user_choice = None
        if lean_config is not None:
            if (
                environment_name
                and "environments" in lean_config
                and environment_name in lean_config["environments"]
                and key in lean_config["environments"][environment_name]
            ):
                user_choice = lean_config["environments"][environment_name][key]
                logger.debug(
                    f"JsonModule({self._display_name}): found '{user_choice}' for '{key}', in environment"
                )
            elif key in lean_config:
                user_choice = lean_config[key]
                logger.debug(
                    f"JsonModule({self._display_name}): found '{user_choice}' for '{key}'"
                )
        return user_choice

    def __repr__(self):
        return self.get_name()

    def _save_property(self, settings: Dict[str, Any]):
        from lean.container import container

        container.lean_config_manager.set_properties(settings)

    @property
    def specifications_url(self):
        return self._specifications_url


class LiveInitialStateInput(str, Enum):
    Required = "required"
    Optional = "optional"
    NotSupported = "not-supported"
