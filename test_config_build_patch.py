# test_config_build_patch.py
import importlib
import inspect
import sys

try:
    mod = importlib.import_module("lean.models.json_module")
    JsonModule = mod.JsonModule
    print("Module import OK: lean.models.json_module")
except Exception as e:
    print("FAILED to import lean.models.json_module:", e)
    sys.exit(2)

# Ensure config_build exists and print its signature / first lines for verification
if hasattr(JsonModule, "config_build"):
    print()
    print("Found JsonModule.config_build(), signature and first lines:")
    src = inspect.getsource(JsonModule.config_build)
    first_lines = "\n".join(src.splitlines()[:20])
    print(first_lines)
    print()
    print("Test hint: now run a real deploy (or run your existing test harness).")
    print("Output marker: CONFIG_BUILD_OK")
    sys.exit(0)
else:
    print("JsonModule has no attribute 'config_build' — patch not applied.")
    sys.exit(3)

