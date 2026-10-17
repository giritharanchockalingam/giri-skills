#!/usr/bin/env bash
# Scaffold a new skill from the template.
# Usage: scripts/new-skill.sh <domain: presales|build|ai-platform|career> <skill-name>
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="$1"; NAME="$2"
DEST="$ROOT/skills/$DOMAIN/$NAME"
[[ -e "$DEST" ]] && { echo "exists: $DEST"; exit 1; }
cp -r "$ROOT/templates/skill-template" "$DEST"
sed -i "s/^name: skill-name/name: $NAME/; s/# Skill Name/# $NAME/; s/domain: presales | build | ai-platform | career/domain: $DOMAIN/" "$DEST/SKILL.md"
sed -i "s/\"skill\": \"skill-name\"/\"skill\": \"$NAME\"/" "$DEST/evals/evals.json"
echo "Created $DEST — edit SKILL.md, then: python3 scripts/validate.py"
