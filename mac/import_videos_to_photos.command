#!/bin/bash
# リーフィー完成動画の「着地」固定ツール（Mac側）
# Klingがダウンロードした動画(~/Downloads/kling_*.mp4)を写真アプリのアルバム「Leafy」へ自動取り込み。
# 取り込み済みは記録して二重取り込みを防止。取り込んだ動画は ~/Pictures/Leafy/動画/ に退避する。
# 認証不要。launchd(com.leafy.import)から定期実行、またはダブルクリックで手動実行。
set -eo pipefail

SRC="$HOME/Downloads"
ARCHIVE="$HOME/Pictures/Leafy/動画"
STATE="$HOME/Pictures/Leafy/.imported_videos.txt"
mkdir -p "$ARCHIVE"
touch "$STATE"

shopt -s nullglob
new_files=()
for f in "$SRC"/kling_*.mp4; do
  base=$(basename "$f")
  if ! grep -qxF "$base" "$STATE"; then
    new_files+=("$f")
  fi
done

count=${#new_files[@]}
if [ "$count" -eq 0 ]; then
  echo "✅ 新しい動画はありません。"
  exit 0
fi

echo "📷 写真アプリ（アルバム Leafy）に取り込み中... ($count 本)"
for f in "${new_files[@]}"; do
  if osascript -e "set v to (POSIX file \"$f\" as alias)" \
    -e 'tell application "Photos"' \
    -e 'if not (exists album "Leafy") then make new album named "Leafy"' \
    -e 'import {v} into album "Leafy" skip check duplicates false' \
    -e 'end tell' >/dev/null 2>&1; then
    base=$(basename "$f")
    echo "$base" >> "$STATE"
    mv "$f" "$ARCHIVE/$base"
    echo "  ✔ $base"
  else
    echo "  ⚠ 取り込み失敗（次回再試行）: $(basename "$f")"
  fi
done

echo "✅ 完了：$count 本を写真アプリへ。元動画は $ARCHIVE に退避。"
