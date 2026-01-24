# test_patch_local.py
from importlib import import_module
import traceback

print(">>> Importing module lean.models.json_module ...")
try:
    mod = import_module("lean.models.json_module")
    print("Module import OK:", mod.__name__)
except Exception as e:
    print("Module import FAILED")
    traceback.print_exc()
    raise SystemExit(1)

JsonModule = mod.JsonModule

print("\n>>> Inspecting patched functions signatures...")
print("get_settings present:", hasattr(JsonModule, "get_settings"))
print("config_build present:", hasattr(JsonModule, "config_build"))

# Build a fake JsonModule instance with minimal config entries to exercise logic
fake_json = {
    "id": "interactive-brokers",
    "display-id": "Interactive Brokers",
    "configurations": [
        # Minimal fake configuration entries to trigger conditional logic:
        {
            "id": "ib-account",
            "type": "internal-input",
            "is-required-from-user": False,
            "optional": False,
            "input-default": None
        },
        {
            "id": "ib-user-name",
            "type": "internal-input",
            "is-required-from-user": False,
            "optional": True,
            "input-default": None
        },
        {
            "id": "ib-password",
            "type": "internal-input",
            "is-required-from-user": False,
            "optional": True,
            "input-default": None
        },
        # A conditional internal input (simulate _value_options structure)
        {
            "id": "ib-agent-description",
            "type": "internal-input",
            "is-required-from-user": False,
            "optional": True,
            "is-conditional": True,
            # value_options will be constructed by Configuration.factory normally;
            # we will patch an InternalInputUserInput object afterwards to add value options.
        }
    ]
}

# Create instance; use factory that exists in the file (Configuration.factory)
from lean.models.configuration import Configuration
# Convert the provided dictionaries to configuration objects via the existing factory if possible,
# otherwise create a simple fallback.
try:
    cfg_objs = [Configuration.factory(c) for c in fake_json["configurations"]]
except Exception:
    # Fallback: create minimal objects with attributes used by the functions
    cfg_objs = []
    class SimpleCfg:
        def __init__(self, _id, optional=False, input_default=None):
            self._id = _id
            self._optional = optional
            self._input_default = input_default
            self._is_required_from_user = False
            self._value = None
            self._is_conditional = False
            self._value_options = []
            self._filter = type("F", (), {"_conditions": []})()
        def ask_user_for_input(self, default, logger, hide_input=False):
            return default
    cfg_objs = [
        SimpleCfg("ib-account", optional=False),
        SimpleCfg("ib-user-name", optional=True),
        SimpleCfg("ib-password", optional=True),
        SimpleCfg("ib-agent-description", optional=True),
    ]
    # Mark last as conditional to force conditional code path:
    cfg_objs[-1]._is_conditional = True
    # Create fake option with a condition object that won't match:
    class FakeCondition:
        def __init__(self, dependent_config_id):
            self._dependent_config_id = dependent_config_id
        def check(self, val):
            return False
    class FakeOption:
        def __init__(self, cond):
            self._condition = cond
            self._value = "agent-x"
    cfg_objs[-1]._value_options = [FakeOption(FakeCondition("ib-account"))]

# Instantiate JsonModule (we supply minimal json_module_data)
json_module_data = {"id": fake_json["id"], "display-id": fake_json["display-id"], "configurations": []}
m = JsonModule(json_module_data, module_type="brokerage", platform="cli")
# replace _lean_configs with our constructed cfg objects to control behavior
m._lean_configs = cfg_objs

# Prepare a fake lean_config that has an environment with explicit empty string for user/password
fake_lean_config = {
    "environments": {
        "live-ibkr-local-history": {
            "properties": {
                "ib-user-name": "",
                "ib-password": ""
            }
        }
    }
}
# provide a lightweight logger with debug/info/warning methods
class L:
    def debug(self, *a, **k): print("DEBUG:", *a)
    def info(self, *a, **k): print("INFO:", *a)
    def warning(self, *a, **k): print("WARNING:", *a)
logger = L()

print("\n>>> Running config_build in non-interactive mode (should not raise)...")
try:
    m.config_build(fake_lean_config, logger, interactive=False, user_provided_options={"ib_account":"DUO869864"}, environment_name="live-ibkr-local-history")
    print("config_build(): OK")
except Exception:
    print("config_build() raised:")
    traceback.print_exc()

print("\n>>> Running get_settings() (should return a dict and not raise)...")
try:
    # put lean_config/env/logger into globals to mimic calling context (same as CLI path)
    globals()["lean_config"] = fake_lean_config
    globals()["environment_name"] = "live-ibkr-local-history"
    globals()["logger"] = logger
    s = m.get_settings()
    print("get_settings() returned:", s)
except Exception:
    print("get_settings() raised:")
    traceback.print_exc()

print("\n>>> TEST DONE. Paste this entire output into the chat.")

