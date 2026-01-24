#!/usr/bin/env python3
# smoke_test_config_build_patch.py
import inspect
import importlib
import traceback
import sys
from types import SimpleNamespace

print(">>> Importing lean.models.json_module ...")
try:
    mod = importlib.import_module("lean.models.json_module")
    print("Module import OK:", mod.__name__)
except Exception:
    print("Module import FAILED")
    traceback.print_exc()
    sys.exit(2)

# Show presence of function
has_cfg = hasattr(mod.JsonModule, "config_build")
print("config_build present:", has_cfg)
if not has_cfg:
    print("ERROR: config_build not found on JsonModule")
    sys.exit(3)

# Print first lines of the function for manual verification
src = inspect.getsource(mod.JsonModule.config_build)
print("\n>>> config_build() preview (first 30 lines):\n")
print("\n".join(src.splitlines()[:30]))

# Now do a light runtime invocation:
print("\n>>> Attempt minimal run: instantiate a dummy subclass and call config_build() non-interactively.")
try:
    # Create a minimal JsonModule subclass that avoids heavy initialization
    class Dummy(mod.JsonModule):
        def __init__(self):
            # avoid calling super().__init__ which expects complex json_module_data
            # Instead set just the fields used by config_build
            self._display_name = "Dummy"
            self._lean_configs = []
            self._is_module_installed = False

    dummy = Dummy()

    # Call config_build with minimal safe arguments
    res = dummy.config_build({}, logger=SimpleNamespace(debug=print, info=print, warning=print), interactive=False, user_provided_options={}, properties={}, environment_name=None)
    print("config_build() call returned:", "OK" if res is dummy else "returned object")
except Exception as e:
    print("config_build() raised an exception:")
    traceback.print_exc()
    sys.exit(4)

print("\n>>> SMOKE TEST COMPLETE. If config_build() loaded and returned OK, paste this entire output into the chat.")

