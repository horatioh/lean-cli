#!/usr/bin/env python3
# apply_json_module_patch_v2.py
# Robust patcher: ersetzt die logic rund um is_empty / missing_options
from pathlib import Path
import re, shutil, time, sys

P = Path("lean/models/json_module.py")
if not P.exists():
    print("❗ Datei lean/models/json_module.py nicht gefunden. Bitte im Verzeichnis ~/git/lean-cli ausführen.")
    sys.exit(2)

bak = P.with_suffix(".py.bak." + str(int(time.time())))
shutil.copy2(P, bak)
print(f"Backup erstellt: {bak}")

text = P.read_text(encoding="utf-8")

# flexible search: find 'is_empty' line and the block until 'configuration._value = user_choice'
# we allow arbitrary whitespace and comments in between
pattern = re.compile(
    r"(is_empty\s*=\s*user_choice\s+is\s+None\s+or\s+\(.*?\)\s*\n)"   # the is_empty line (loose)
    r"(.*?)"                                                         # anything in between (non-greedy)
    r"(\n\s*configuration\._value\s*=\s*user_choice)",                # the line we stop at (include newline before)
    re.DOTALL | re.IGNORECASE
)

m = pattern.search(text)
if not m:
    # Try even looser: find 'is_empty' anywhere and then find next 'configuration._value'
    print("Warnung: exakter Pattern-Search für 'is_empty' nicht erfolgreich. Versuche looseres Matching...")
    pattern2 = re.compile(r"(is_empty\s*=.*?\n)(.*?)(\n\s*configuration\._value\s*=)", re.DOTALL | re.IGNORECASE)
    m2 = pattern2.search(text)
    if not m2:
        print("❗ Konnte weder das erwartete 'is_empty' Block noch 'configuration._value' finden.")
        print("Bitte poste die Zeilen 1..520 von lean/models/json_module.py hier (oder mindestens 320..460).")
        sys.exit(3)
    start_idx = m2.start(1)
    end_idx = m2.end(3)
else:
    start_idx = m.start(1)
    end_idx = m.end(3)

# prepare replacement block
replacement = r"""# Leer-/None-Check: Empty string gilt nicht automatisch als "fehlend",
        # wenn der Key explizit in der lean.json environment properties vorhanden ist.
        is_empty = user_choice is None or (isinstance(user_choice, str) and user_choice.strip() == "")

        # Prüfe explizit, ob dieser Key in der lean.json environment (properties) vorhanden ist.
        env_has_key = False
        try:
            environment_name_local = environment_name if 'environment_name' in globals() else None
            envs = lean_config.get('environments') or {}
            env_block = envs.get(environment_name_local) if isinstance(envs, dict) else None
            if env_block and isinstance(env_block, dict):
                env_props = env_block.get('properties', {}) or {}
                if configuration._id in env_props:
                    env_has_key = True
        except Exception:
            env_has_key = False

        if is_empty:
            if interactive:
                default_value = configuration._input_default
                user_choice = configuration.ask_user_for_input(default_value, logger, hide_input=hide_input)

                if not isinstance(configuration, BrokerageEnvConfiguration):
                    self._save_property({f"{configuration._id}": user_choice})
            else:
                # Non-interactive mode:
                # If the configuration is optional, allow it to be empty (connect-only scenarios)
                # Otherwise require it — UNLESS the key is present in lean.json environment properties.
                if configuration._optional:
                    if configuration._input_default is not None:
                        user_choice = configuration._input_default
                    # else keep empty
                else:
                    if env_has_key:
                        # explicit empty string in lean.json counts as "provided" (connect-only)
                        # keep user_choice as empty string and do NOT add to missing_options
                        pass
                    else:
                        missing_options.append(f"--{configuration._id}")

        configuration._value = user_choice"""

# perform replacement
new_text = text[:start_idx] + replacement + text[end_idx:]

P.write_text(new_text, encoding="utf-8")
print("✅ Patch angewendet (robust). Zeige Kontext (nächste 30 Zeilen):")
lines = new_text.splitlines()
# find where replacement begins to display context
line_no = new_text[:start_idx].count("\n")
start = max(0, line_no - 3)
end = min(len(lines), line_no + 40)
for i in range(start, end):
    print(f"{i+1:4d}: {lines[i]}")
print("\nFalls du möchtest, committe die Änderung:\n  git add lean/models/json_module.py && git commit -m \"fix: allow empty env props as provided\"\n")

