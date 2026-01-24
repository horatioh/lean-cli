# test_config_build_local_run.py
import importlib
import lean.models.json_module as json_module
from lean.components.util.logger import Logger

print("Import OK:", hasattr(json_module, "JsonModule"))

# Create a tiny fake subclass to instantiate
class DummyJsonModule(json_module.JsonModule):
    def __init__(self):
        # craft minimal json_module_data expected by ctor
        data = {
            "id": "InteractiveBrokersBrokerage",
            "display-id": "interactive-brokers",
            "configurations": [
                # minimal configuration-like dicts; we only need ids for the test
                {"id": "ib-user-name", "type": "internal-input", "optional": False},
                {"id": "ib-account", "type": "internal-input", "optional": False},
                {"id": "ib-password", "type": "internal-input", "optional": False},
                {"id": "ib-weekly-restart-utc-time", "type": "internal-input", "optional": True, "input-default": "22:00:00"},
            ],
        }
        # Call base ctor with dummy platform/type
        super().__init__(data, module_type="brokerage", platform="cli")

    # Minimal overrides used by the base impl in tests
    def get_default(self, lean_config, key, env_name, logger):
        # return default from lean_config['environments'][env_name]['properties'] if present
        try:
            envs = lean_config.get("environments", {})
            env_block = envs.get(env_name, {}) if env_name else {}
            props = env_block.get("properties", {}) if isinstance(env_block, dict) else {}
            return props.get(key, None)
        except Exception:
            return None

# instantiate
mod = DummyJsonModule()
logger = Logger()

# simulate lean_config with environment properties present (keys with hyphen and underscore)
lean_config = {
    "environments": {
        "live-ibkr-local-history": {
            "properties": {
                # both variants present like in your log; values intentionally empty strings
                "ib-account": "",
                "ib_user_name": "",
                "ib-password": "",
                # weekly restart present with value
                "ib-weekly-restart-utc-time": "22:00:00"
            }
        }
    }
}

# user_provided_options empty (replicates your run)
user_provided_options = {}
properties = {  # the handler sometimes passes a separate properties mapping
    "ib_account": "", "ib-account": "", "ib_user_name": "", "ib-user-name": "",
    "ib_password": "", "ib-password": "", "ib_weekly_restart_utc_time": "22:00:00",
}

try:
    mod.config_build(
        lean_config=lean_config,
        logger=logger,
        interactive=False,
        user_provided_options=user_provided_options,
        properties=properties,
        environment_name="live-ibkr-local-history",
        hide_input=True,
    )
    print("CONFIG_BUILD_OK")
except Exception as e:
    print("CONFIG_BUILD_FAILED:", type(e).__name__, str(e))

