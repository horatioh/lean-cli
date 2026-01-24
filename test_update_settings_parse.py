# test_update_settings_parse.py
from types import SimpleNamespace
from lean.components.util.logger import Logger

def run_test():
    logger = Logger()
    # base target that simulates existing module settings
    base_target = {
        "data-queue-handler": ["QuantConnect.Brokerages.InteractiveBrokers.InteractiveBrokersBrokerage"]
    }

    properties_samples = {
        "case_none_string": {"data-queue-handler": "None"},
        "case_empty_string": {"data-queue-handler": ""},
        "case_json_array": {"data-queue-handler": '["A","B"]'},
        "case_python_list": {"data-queue-handler": ["X","Y"]},
        "case_comma_csv": {"data-queue-handler": "A, B, C"},
        "case_scalar_string": {"data-queue-handler": "singleValue"},
    }

    from lean.components.util import json_modules_handler

    print("RUNNING PARSE TESTS")
    for name, props in properties_samples.items():
        print("\n---", name, "---")
        # prepare a fresh target copy for each test
        tgt = {k: list(v) for k, v in base_target.items()}

        # prepare lean_config simulating environments -> env -> properties
        lean_config = {"environments": {"env": {"properties": props}}}

        try:
            # call the patched function: (logger, environment_name, target, lean_config)
            json_modules_handler._update_settings(logger, "env", tgt, lean_config)
            print("target after update:", tgt)
        except Exception as e:
            print("EXCEPTION:", type(e).__name__, e)

if __name__ == "__main__":
    run_test()

