#!/usr/bin/env python3
# apply_json_module_conditional_fix.py
# Macht ein Backup und ersetzt die Bedingungsprüfung für InternalInputUserInput
# damit für option._condition die get_default(...) Werte verwendet werden.
#
# Usage: run from repo root: python apply_json_module_conditional_fix.py

from pathlib import Path
import re, shutil, time, sys

TARGET = Path("lean/models/json_module.py")
if not TARGET.exists():
    print("❗ Datei lean/models/json_module.py nicht gefunden. Bitte im Verzeichnis ~/git/lean-cli ausführen.")
    sys.exit(2)

# Backup
bak = TARGET.with_suffix(".py.bak." + str(int(time.time())))
shutil.copy2(TARGET, bak)
print(f"Backup erstellt: {bak}")

text = TARGET.read_text(encoding="utf-8")

# We try to locate the 'for option in config._value_options:' loop inside the
# earlier block that handles InternalInputUserInput/_is_conditional.
# We'll keep indentation robust by capturing the indent of the 'for' line.
pattern = re.compile(
    r"(?P<indent>^[ \t]*)for\s+option\s+in\s+config\._value_options:\s*\n"  # for line and indent
    r"(?P<body>(?:^(?P=indent)[ \t]+.*\n)+?)"  # body lines with greater indent
    r"(?=^(?P=indent)[ \t]*\S)",                # lookahead: next top-level line (same indent) starts non-space
    re.MULTILINE
)

m = pattern.search(text)
if not m:
    # fallback: looser search for the first occurrence of "for option in config._value_options"
    print("Hinweis: exaktes Pattern nicht gefunden, versuche lockeres Matching...")
    m2 = re.search(r"(^[ \t]*)for\s+option\s+in\s+config\._value_options:\s*\n(.*?)(?=^[ \t]*\S)",
                   text, re.MULTILINE | re.DOTALL)
    if not m2:
        print("❗ Konnte die 'for option in config._value_options:'-Schleife nicht finden.")
        print("Bitte poste die Ausgabe von:\n  sed -n '320,460p' lean/models/json_module.py")
        sys.exit(3)
    indent = m2.group(1)
    body = m2.group(2)
    start_idx = m2.start(0)
    end_idx = m2.end(0)
else:
    indent = m.group("indent")
    body = m.group("body")
    start_idx = m.start(0)
    end_idx = m.end(0)

# Show snippet we found (brief)
print("\n--- Gefundener Block (erste 8 Zeilen):")
for i, ln in enumerate(body.splitlines()[:8]):
    print(f"{i+1:2d}: {ln}")
print("...")

# Build replacement preserving indent
# replacement will use same indent + one level of extra indentation (indent + 4 spaces or a tab)
# detect whether indent uses tabs or spaces; for the inner indent we add 4 spaces
inner = indent + " " * 4

replacement_block = f"""{indent}for option in config._value_options:
{inner}# Verwende get_default(...) für die Abhängigkeitsprüfung, damit CLI-Optionen
{inner}# oder lean.json environment properties berücksichtigt werden (sonst greift die
{inner}# Prüfung auf _value, das erst später gesetzt wird).
{inner}dependent_id = option._condition._dependent_config_id
{inner}try:
{inner}    dependent_value = self.get_default(
{inner}        lean_config, dependent_id, environment_name, logger
{inner}    )
{inner}except Exception:
{inner}    # Fallback: falls get_default fehlschlägt, verwende den bisherigen Weg
{inner}    try:
{inner}        dependent_value = self.get_config_value_from_name(dependent_id)
{inner}    except Exception:
{inner}        dependent_value = None
{inner}
{inner}if option._condition.check(dependent_value):
{inner}    config._value = option._value
{inner}    break
"""

# Replace the first occurrence between start_idx and end_idx
new_text = text[:start_idx] + replacement_block + text[end_idx:]

if new_text == text:
    print("❗ Ersetzung hat keine Änderung erzeugt (Text unverändert). Abbruch.")
    sys.exit(4)

TARGET.write_text(new_text, encoding="utf-8")
print("✅ Änderung angewendet: lean/models/json_module.py aktualisiert.\n")

# Show context around where we replaced (lines)
lines = new_text.splitlines()
line_no = new_text[:start_idx].count("\n")
start = max(0, line_no - 4)
end = min(len(lines), line_no + 30)
print("---- Kontext (Zeilen um die Änderung):")
for i in range(start, end):
    print(f"{i+1:04d}: {lines[i]}")

print("\nNächste Schritte:")
print("1) Test: führe den deploy-Aufruf erneut (wie vorher).")
print("2) Wenn alles gut ist, committe die Änderung:")
print("     git add lean/models/json_module.py")
print("     git commit -m \"fix(json_module): evaluate conditional options using get_default to consider CLI/env props\"")
print("\nRollback (falls nötig):")
print(f"     cp {bak} lean/models/json_module.py")

