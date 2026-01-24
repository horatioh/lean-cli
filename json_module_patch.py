from pathlib import Path
p = Path("lean/models/json_module.py")
s = p.read_text(encoding="utf-8")

old_marker = "is_empty = user_choice is None or (isinstance(user_choice, str) and user_choice.strip() == \"\")"
if old_marker not in s:
    print("❗ Unerwarteter Datei-Inhalt — 'is_empty' Marker nicht gefunden. Abort.")
    raise SystemExit(1)

# Wir ersetzen den Block ab 'is_empty = ...' bis zur Zeile 'configuration._value = user_choice'
import re

pattern = re.compile(
    r"is_empty\s*=\s*user_choice\s+is\s+None\s+or\s+\(isinstance\(user_choice,\s*str\)\s+and\s+user_choice\.strip\(\)\s*==\s*\"\"\)\s*\n\n\s*if\s+is_empty:.*?\n\s*configuration\._value\s*=\s*user_choice",
    re.DOTALL
)

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

new = pattern.sub(replacement, s, count=1)
if new == s:
    print("❗ Ersetzung fehlgeschlagen: Pattern nicht gefunden / nicht ersetzt.")
    raise SystemExit(1)

p.write_text(new, encoding="utf-8")
print("✅ Patch angewendet: lean/models/json_module.py wurde aktualisiert.")
# show small diff-ish context
print("---- Kontext nach Änderung (lines around replacement):")
text = new.splitlines()
for i,l in enumerate(text):
    if "env_has_key" in l:
        start=max(0,i-5); end=min(len(text), i+15)
        print("\n".join(f"{j+1:5d}: {text[j]}" for j in range(start,end)))
        break
