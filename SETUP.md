# リーフィー動画工場 — セットアップ（Macフォルダ受け取り版）

人がやることは「Mac に届いた完成クリップを見て、気に入ったのを Instagram に手動投稿」だけ。
生成はクラウドで自動。Telegram も IG連携も不要。

## ループの流れ
1. 週次cron `generate-batch` が `shotlist.csv`（ネタ貯金）の未使用5本を自動生成
2. 完成した9:16クリップを GitHub Releases（タグ `clips`）にアップ
3. Mac で `mac/fetch_clips.command` をダブルクリック → 新しいクリップを `~/Pictures/Leafy` にDL＆**写真アプリに取り込み**
4. iCloud写真でiPhoneにも同期 → 気に入ったものを Instagram に手動投稿

ネタが尽きたら `shotlist.csv` に行を足すだけ（`status` 列は空のまま＝未使用）。

## 必要な GitHub Secrets（新規登録ナシ）
| Secret | 用途 | 状態 |
|---|---|---|
| `FAL_KEY` | 画像/動画生成 | 既存 |
| `LORA_URL` | キャラLoRA | 既存 |

`GITHUB_TOKEN` は Actions が自動付与。**追加のトークンは要りません。**

> リポジトリは **public のまま** にしてください。Macは GitHub Releases の公開URLからクリップを取得します。

## Mac側の使い方
1. Finder で `leafy-factory/mac/fetch_clips.command` を **ダブルクリック**
   - 初回だけ「実行してよいか」「写真アプリの操作を許可するか」を聞かれるので許可
2. 新しいクリップが `~/Pictures/Leafy` に入り、写真アプリにも取り込まれる
3. 写真（またはiPhone）から、良いものを Instagram に投稿

> 手動で取りに行くのが面倒なら、後述の「自動で取り込む」を設定すれば放置でOK。

### （任意）自動で取り込む
毎時バックグラウンドで取りに行かせたい場合：
```bash
mkdir -p ~/Library/LaunchAgents
cp "<このリポジトリのパス>/mac/com.leafy.fetch.plist" ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.leafy.fetch.plist
```
（停止は `launchctl unload ~/Library/LaunchAgents/com.leafy.fetch.plist`）

## 動かし方（初回テスト）
1. Actions → `generate-batch` → Run workflow（手動実行）
2. 数分待ってから Mac で `fetch_clips.command` をダブルクリック
3. `~/Pictures/Leafy` と写真アプリにリーフィーのクリップが出ればOK

- 生成本数を変える: `generate-batch.yml` の `BATCH_SIZE`
- 投稿ペース・内容は人が自由に（自動投稿なし）

## ファイル
- `shotlist.csv` … ネタ貯金（`status` 空＝未使用）。ここだけ時々足す
- `pipeline.py` … 生成→9:16整形→Releasesへアップ→使用済み印
- `mac/fetch_clips.command` … Mac取り込みツール（ダブルクリック）
- `mac/com.leafy.fetch.plist` … 自動取り込み用（任意）
- `.github/workflows/generate-batch.yml` … 週次の自動生成
