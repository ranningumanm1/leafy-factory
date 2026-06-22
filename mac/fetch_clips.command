#!/bin/bash
# リーフィー完成クリップ取り込みツール（Mac側）
# ダブルクリックで実行: GitHub Releases にある新しいクリップだけをDLし、
# ~/Pictures/Leafy に保存 → 写真アプリに取り込み（iCloud経由でiPhoneにも届く）。
# 認証不要（公開リポを読むだけ）。
set -eo pipefail

REPO="ranningumanm1/leafy-factory"
TAG="clips"
DEST="$HOME/Pictures/Leafy"
mkdir -p "$DEST"

echo "🌱 新しいクリップを確認中..."
JSON=$(curl -fsL "https://api.github.com/repos/$REPO/releases/tags/$TAG" 2>/dev/null) \
  || { echo 'まだクリップがありません（生成が1回も走っていないかも）'; exit 0; }
ASSETS=$(printf '%s' "$JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for a in d.get('assets', []):
    print(a['name'] + chr(9) + a['browser_download_url'])
")

new_files=()
while IFS=$'\t' read -r name url; do
  [ -z "$name" ] && continue
  case "$name" in
    *.txt) curl -fsL "$url" -o "$DEST/$name" 2>/dev/null || true; continue ;;
  esac
  if [ ! -f "$DEST/$name" ]; then
    echo "  ⬇️  $name"
    curl -fsSL "$url" -o "$DEST/$name"
    new_files+=("$DEST/$name")
  fi
done <<< "$ASSETS"

count=${#new_files[@]}
if [ "$count" -gt 0 ]; then
  echo "📷 写真アプリに取り込み中..."
  for f in "${new_files[@]}"; do
    case "$f" in
      *.mp4|*.mov|*.jpg|*.jpeg|*.png)
        osascript -e "tell application \"Photos\" to import POSIX file \"$f\"" >/dev/null 2>&1 || true ;;
    esac
  done
  open "$DEST"
fi

echo "✅ 完了：新規 $count 本（保存先: $DEST）"
