#!/usr/bin/env bash
# Install all giri-skills into an agent's skills directory (symlink by default).
# Usage: scripts/install.sh [claude|agents|cursor|codex] [--copy]
#   claude → ~/.claude/skills      agents → ~/.agents/skills (universal)
#   cursor → ~/.cursor/skills      codex  → ~/.codex/skills
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-claude}"; MODE="${2:-}"
case "$TARGET" in
  claude) DEST="$HOME/.claude/skills";;
  agents) DEST="$HOME/.agents/skills";;
  cursor) DEST="$HOME/.cursor/skills";;
  codex)  DEST="$HOME/.codex/skills";;
  *) echo "unknown target $TARGET"; exit 1;;
esac
mkdir -p "$DEST"
n=0
while IFS= read -r skill; do
  name="$(basename "$skill")"
  rm -rf "$DEST/$name"
  if [[ "$MODE" == "--copy" ]]; then cp -r "$skill" "$DEST/$name"; else ln -s "$skill" "$DEST/$name"; fi
  n=$((n+1))
done < <(find "$ROOT/skills" "$ROOT/vendor" -name SKILL.md -exec dirname {} \; 2>/dev/null)
# shared/ is referenced by relative path from skills; expose it alongside
rm -rf "$DEST/_giri-shared"; ln -sfn "$ROOT/shared" "$DEST/_giri-shared"
echo "Installed $n skills to $DEST ($([[ "$MODE" == "--copy" ]] && echo copy || echo symlink))"
