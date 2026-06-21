# リーフィー動画工場 — セットアップ（最小工数ループ版）

人がやることは「Telegram で OK/NG を押す」だけ。生成も投稿も自動です。
そのために **一度だけ** 下のセットアップが要ります（鍵類は本人が登録）。

## ループの流れ
1. 週次cron `generate-batch` が `shotlist.csv`（ネタ貯金）の未使用5本を生成
2. 各クリップを GitHub Releases にアップ（公開URL化）＋ Telegram に OK/NG ボタン付きで配信
3. あなたがスマホで OK / NG を押す ← 唯一の手作業
4. 毎時cron `publish` が押下を回収し、OK分を **1日1本** Instagram に自動公開
5. 進捗は `state.json` に記録（リポジトリに自動コミット）

ネタが尽きると Telegram に警告が来るので、`shotlist.csv` に行を足すだけ（`status` 列は空のまま）。

## 必要な GitHub Secrets
リポジトリ → Settings → Secrets and variables → Actions に登録。

| Secret | 用途 | 取り方 |
|---|---|---|
| `FAL_KEY` | 画像/動画生成 | 既存 |
| `LORA_URL` | キャラLoRA | 既存 |
| `TELEGRAM_BOT_TOKEN` | 配信＋承認 | 下記A |
| `TELEGRAM_CHAT_ID` | 送り先 | 下記A |
| `IG_USER_ID` | 投稿先IG | 下記B |
| `IG_ACCESS_TOKEN` | IG投稿 | 下記B |

`GITHUB_TOKEN` は Actions が自動付与（登録不要）。

> リポジトリは **public のまま** にしてください。Instagram は GitHub Releases の公開URLから動画を取得します。private にすると取得できません。

## A. Telegram（5分）
1. Telegram で `@BotFather` に `/newbot` → bot名を決めるとトークンが出る → `TELEGRAM_BOT_TOKEN`
2. 作った bot を開いて自分から `/start`（1メッセージ送るだけ）
3. ブラウザで `https://api.telegram.org/bot<トークン>/getUpdates` を開き、`message.chat.id` の数値を控える → `TELEGRAM_CHAT_ID`

## B. Instagram Graph API（自動投稿）
1. IG を **プロ（クリエイター or ビジネス）** アカウントにし、Facebookページに連携
2. [Meta for Developers](https://developers.facebook.com/) でアプリ作成 → プロダクトに「Instagram」を追加
3. 権限 `instagram_basic` `instagram_content_publish` `pages_show_list` を付け、**長期（long-lived）アクセストークン** を発行 → `IG_ACCESS_TOKEN`
   - 自分のアカウントへの投稿は開発モード＋自分をテスター登録で動きます（公開アプリ審査は不要）
4. グラフAPIエクスプローラ等で自分の **IGビジネスアカウントID** を取得 → `IG_USER_ID`

> ⚠️ 長期トークンも約60日で失効します。失効したら手順3で再発行して `IG_ACCESS_TOKEN` を更新してください（投稿が止まったらまずここを疑う）。

## 動かし方
- 初回テスト: Actions → `generate-batch` を手動Run → Telegram に届くか確認 → OK を押す → `publish` を手動Run → IGに上がるか確認
- 以降は放置。週次で生成、毎時で投稿判定が回ります。
- 投稿ペースを変える: `publish.yml` の `POSTS_PER_DAY`、生成本数は `generate-batch.yml` の `BATCH_SIZE`。
- キャプション/ハッシュタグ: `publisher.py` の `POST_CAPTION`（または同名のSecret/変数で上書き）。

## ファイル
- `shotlist.csv` … ネタ貯金（`status` 空＝未使用）。ここだけ時々足す
- `pipeline.py` … 生成→Releasesアップ→Telegram配信→状態記録
- `publisher.py` … 承認回収→IGドリップ投稿
- `common.py` … Telegram / GitHub Releases / state.json の共通処理
- `state.json` … ループの状態（自動生成・自動更新）
