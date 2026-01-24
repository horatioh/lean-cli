#!/usr/bin/env python3
# test_get_settings_patch.py
# Usage: PYTHONPATH=~/git/lean-cli python test_get_settings_patch.py

from types import SimpleNamespace
import importlib
import sys

# import the module (ensure PYTHONPATH points to your local lean-cli)
mod = importlib.import_module("lean.models.json_module")
JsonModule = mod.JsonModule
InternalInputUserInput = mod.InternalInputUserInput
AuthConfiguration = mod.AuthConfiguration

print("Module import OK:", mod.__name__)

# Build fake option condition that never matches
class NeverMatchCondition:
    def __init__(self, dependent_config_id):
        self._dependent_config_id = dependent_config_id
    def check(self, value):
        return False

# Build fake option object
FakeOption = SimpleNamespace
fake_option = FakeOption(_condition=NeverMatchCondition("ib-account"), _value="agentX")

# Fake conditional config
fake_conditional = SimpleNamespace(
    _id="ib-agent-description",
    _is_conditional=True,
    _value_options=[fake_option],
    _value=None
)
# Pretend it is InternalInputUserInput type for the function's type check:
# (some code checks 'type(config) is InternalInputUserInput'), so create instance of that class if possible.
# If the real InternalInputUserInput is constructable, try to create one; otherwise, trick via subclassing.
try:
    # Attempt real construction path if class accepts minimal args (best-effort)
    fake_conditional = InternalInputUserInput.__new__(InternalInputUserInput)
    # set attributes expected by our get_settings logic
    fake_conditional._id = "ib-agent-description"
    fake_conditional._is_conditional = True
    fake_conditional._value_options = [fake_option]
    fake_conditional._value = None
except Exception:
    # fallback: leave our SimpleNamespace; but ensure type comparison in get_settings will not pass.
    # To force the code path we want (type(config) is InternalInputUserInput) we will inject our fake list below.
    pass

# Normal config
normal_config = SimpleNamespace(
    _id="ib-weekly-restart-utc-time",
    _value="22:00:00"
)

# Build a fake module-like object that contains the minimal methods/attributes used in get_settings
class FakeModule:
    def __init__(self, configs):
        self._id = "interactive-brokers"
        self._lean_configs = configs

    # copy over helper methods used by get_settings
    def _check_if_config_passes_filters(self, config, all_for_platform_type=False):
        return True

    def get_config_value_from_name(self, name):
        # no dependent config exists in this test
        raise Exception("not found")

    def get_default(self, lean_config, conf_id, environment_name, logger):
        # return empty string for ib-user-name/ib-password when asked
        if conf_id in ("ib-user-name", "ib-password"):
            return ""
        return None

# If InternalInputUserInput instantiation worked earlier, include it; else force the typed-check by
# inserting an actual InternalInputUserInput instance in the list when possible.
configs_list = [normal_config]

# If fake_conditional is an instance of InternalInputUserInput use it directly, else try to build one wrapper
if isinstance(fake_conditional, InternalInputUserInput):
    configs_list.insert(0, fake_conditional)
else:
    # Try to allocate a real InternalInputUserInput via __new__ above may have failed; attempt dynamic workaround:
    try:
        real_i = InternalInputUserInput.__new__(InternalInputUserInput)
        real_i._id = "ib-agent-description"
        real_i._is_conditional = True
        real_i._value_options = [fake_option]
        real_i._value = None
        configs_list.insert(0, real_i)
    except Exception:
        # fallback: append the SimpleNamespace and bypass the type-check by temporarily monkeypatching
        # the 'type' check isn't easy to monkeypatch, so for the worst case we simulate the later stage:
        print("WARNING: could not create InternalInputUserInput instance; adding SimpleNamespace and note that the prefill/conditional-block may not run exactly the same way.")
        configs_list.insert(0, SimpleNamespace(
            _id="ib-agent-description",
            _is_conditional=True,
            _value_options=[fake_option],
            _value=None
        ))

fm = FakeModule(configs_list)

# Bind the patched get_settings function from the real module to our fake instance.
patched_get_settings = mod.JsonModule.get_settings
bound = patched_get_settings.__get__(fm, fm.__class__)

print("\nRunning patched get_settings() on fake module...\n")
try:
    out = bound()
    print("get_settings() returned successfully.")
    print("Returned settings dict:")
    for k, v in out.items():
        print(f"  {k!s}: {v!s}")
except Exception as e:
    print("get_settings() raised an exception:", repr(e))
    import traceback
    traceback.print_exc()

