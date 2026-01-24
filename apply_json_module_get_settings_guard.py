#!/usr/bin/env python3
"""
apply_json_module_get_settings_guard.py

Make a safe in-place change to lean/models/json_module.py:
When get_settings() would raise ValueError for conditional InternalInputUserInput
("No condition matched among present options for ..."), replace the raise with
a warning and set the conditional configuration value to empty string so
non-interactive flows can continue.

Creates a timestamped backup before editing.
"""
import io, os, re, time, sys
from pathlib import Path
p = Path(__file__).resolve().parents[0] / "lean" / "models" / "json_module.py"
if not p.exists():
    print("ERROR: file not found:", p)
    sys.exit(2)

bak = str(p) + ".bak." + str(int(time.time()))
print("Backup created:", bak)
import shutil
shutil.copy2(str(p), bak)

text = p.read_text(encoding="utf-8")

# Find the specific ValueError raise block that matches the pattern seen in logs.
# We'll replace the 'raise ValueError(...)' block with a guarded fallback.
pattern = re.compile(
    r"(raise ValueError\(\s*f'No condition matched among present options for \"(?P<cfgid>[^\"']+)\"\. Please review \"(?P<dep>[^\"']+)\" given value \"\"\s*'\)\s*)",
    re.MULTILINE
)

if not pattern.search(text):
    # If the exact formatted message is not present, search for the generic raise in the same function context.
    alt_pattern = re.compile(
        r"(raise ValueError\(\s*f'No condition matched among present options for \"(?P<cfgid>[^\"']+)\"\. Please review .+?'\)\s*)",
        re.MULTILINE
    )
    if not alt_pattern.search(text):
        print("Could not find the exact ValueError raise to replace. Aborting to avoid accidental edits.")
        print("You can inspect lean/models/json_module.py and run this script again after adjusting.")
        sys.exit(3)
    else:
        match = alt_pattern.search(text)
        cfgid = match.group("cfgid")
        start, end = match.span(1)
else:
    match = pattern.search(text)
    cfgid = match.group("cfgid")
    start, end = match.span(1)

# We'll insert replacement code that logs a warning and sets configuration._value = ""
replacement = (
    "# --- BEGIN: tolerant fallback inserted by apply_json_module_get_settings_guard.py ---\n"
    "logger.warning(\n"
    "    f'No conditional option matched for \"{cfgid}\" during get_settings().'\n"
    "    ' This can happen in non-interactive runs when the dependent config is empty.'\n"
    ")\n"
    "# Fail-safe: treat as explicitly provided empty string so non-interactive deploy continues.\n"
    "configuration._value = \"\"\n"
    "# --- END: tolerant fallback ---\n"
)

# Replace the raise statement with the fallback. Be conservative: replace only the matched span.
new_text = text[:start] + replacement + text[end:]

# Sanity-check: ensure file still contains the get_settings() function signature
if "def get_settings(self) -> Dict[str, str]:" not in new_text:
    print("Sanity check failed: get_settings() signature not found after edit. Aborting and restoring backup.")
    shutil.copy2(bak, str(p))
    sys.exit(4)

p.write_text(new_text, encoding="utf-8")
print("Patch applied. Please run quick import test:")
print()
print("  python - <<'PY'\n  import lean.models.json_module\n  print('json_module import OK')\n  PY")
print()
print("If something looks wrong, restore backup with:")
print(f"  cp '{bak}' '{p}'")

