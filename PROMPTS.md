# リーフィー プロンプト品質ガイド

このファイル＝プロンプトの「正解の型」。質を上げる改善ループの中心。
新ネタを作る時・既存を直す時は必ずこの型に沿う。学びは LEARNINGS.md に蓄積し、ここへ反映する。

## 4つのプロンプト層
1. キャラの芯 = `pipeline.py` の `CHAR_CORE`（CHARACTER.md と一致・固定）
2. 背景 = `pipeline.py` の `BACKGROUND`（季節・舞台。今は秋の森）
3. キーフレーム画像 = `shotlist.csv` の `image_prompt`（最初の1枚の「絵」）
4. 動き = `shotlist.csv` の `motion_prompt`（Klingに渡す「演技」）

→ 画像 = CHAR_CORE + BACKGROUND + image_prompt が自動合成される。
　so image_prompt は「キャラ・背景の説明を繰り返さない」。ポーズ・小道具・構図・光だけ足す。

## image_prompt の型（キーフレーム）
要素を順に：[開始ポーズ/構え] + [小道具] + full body [視点: front / 3/4 / side] + composed for vertical 9:16 + [光・被写界深度の一言]
- 1キャラ・全身・縦構図を必ず明示（見切れ防止）
- 「動きの直前」の静止ポーズにする（動きはmotion側で表現）
- 例: standing frame-left ready to run, a small twig on the mossy ground just ahead, full body 3/4 view, composed for vertical 9:16, soft morning light

## motion_prompt の型（Kling・最重要）
「演技の流れ＝ビート」で書く。型：
[セットアップの動き] → [メインの行動] → [かわいい失敗＋物理] → [一拍おく(comedic beat)] → [立ち直り＋感情] — 物理/間/カメラ/構図/ループ の固定句
- 物理: bouncy squash-and-stretch（ぷにっと潰れて伸びる）
- 間: holds a brief beat / pauses（笑いの“間”を必ず入れる）
- 感情: beaming / shy giggle / proud / sparkly eyes など具体的に
- カメラ: fixed camera（固定）
- 構図: full body in frame（全身キープ）
- 仕上げ: smooth loopable motion（つなぎ目が自然＝リール向き）
- 例: takes two eager running steps and hops over the twig, catches a back paw and tumbles forward into a soft plush roll, holds a brief upside-down comedic beat, then springs upright beaming with a happy tail-wiggle — bouncy squash-and-stretch, gentle wholesome timing, fixed camera, full body in frame, smooth loopable motion

## 黄金パターン（リーフィーの芯）
踊る/挑戦する → かわいく転ぶ(plush roll) → 一拍 → 立ち直って笑う。
「失敗のかわいさ」と「立ち直りの明るさ」がブランド。怖さ・派手さは入れない。

## 品質チェックリスト（生成前）
- [ ] 全身・縦9:16・固定カメラになっているか
- [ ] 「行動→失敗→間→立ち直り」の4ビートがあるか
- [ ] 物理(squash-and-stretch)と感情語が入っているか
- [ ] loopable / wholesome の仕上げ句があるか
- [ ] キャラ・背景をimage_promptで重複説明していないか

## NG（質を下げる）
炎/魔法/光る能力、既存キャラ要素、人間体型、リアル肌、文字・ロゴ・透かし、怖い表情、
カメラの激しい動き、複数キャラ、見切れ。
