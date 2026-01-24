#!/usr/bin/env python3
# apply_json_module_prefill_fix.py
#
# Fix: Pre-fill configuration._value using get_default()
# BEFORE InternalInputUserInput conditional evaluation.
# This avoids broken condition checks (ib-agent-description / ib-account).

from pathlib import Path
import shutil, time, sys

TARGET = Path("lean/models/json_module.py")
if not TARGET.exists():
    print("❌ lean/models/json_module.py not found")
    sys.exit(1)

backup = TARGET.with_suffix(".py.bak." + str(int(time.time())))
shutil.copy2(TARGET, backup)
print(f"Backup created: {backup}")

text = TARGET.read_text(encoding="utf-8").splitlines()

out = []
inserted = False

for line in text:
    out.append(line)

    # Insert just BEFORE conditional InternalInputUserInput evaluation
    if "if type(config) is InternalInputUserInput:" in line and not inserted:
        out.append("")
        out.append("        # --- PRE-FILL config values from lean_config before conditional evaluation ---")
        out.append("        for _cfg in self._lean_configs:")
        out.append("            if _cfg._value is None:")
        out.append("                try:")
        out.append("                    _cfg._value = self.get_default(lean_config, _cfg._id, environment_name, logger)")
        out.append("                except Exception:")
        out.append("                    pass")
        out.append("        # --- END PRE-FILL ---")
        inserted = True

TARGET.write_text("\n".join(out), encoding="utf-8")

if not inserted:
    print("⚠️ Warning: insertion point not found (code may have changed)")
else:
    print("✅ Pre-fill fix applied successfully")

