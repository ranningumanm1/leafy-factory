"""
工場の共通部品。3つの外部サービスとの最小限のやりとりをここに集約する。
  - state.json : ループの状態（クリップ一覧・承認状況・投稿カウンタ・Telegram offset）
  - Telegram   : クリップをスマホに配信し、OK/NG ボタンの押下を回収する
  - GitHub Releases : 最終mp4を公開URLにする（Instagram APIは公開URLから動画を取得するため）

鍵類はすべて環境変数（GitHub Actions の Secrets）から渡る。ローカルでも env を入れれば動く。
"""
import os
import json
import pathlib
import requests

STATE_FILE = pathlib.Path("state.json")

# 1本のクリップが取りうる状態:
#   pending  … 生成してTelegramに送った。承認待ち
#   approved … 人がOKを押した。投稿待ち（ドリップ対象）
#   rejected … 人がNGを押した。投稿しない
#   posted   … Instagramに公開済み
DEFAULT_STATE = {
    "tg_offset": 0,          # 次に取得するTelegram update_id
    "last_post_date": "",    # 最後に投稿した日付(JST, YYYY-MM-DD)
    "posts_today": 0,        # その日の投稿本数（ドリップ上限の判定用）
    "clips": {},             # key -> {url, caption, status, tg_message_id, created}
}


def load_state() -> dict:
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for k, v in DEFAULT_STATE.items():
            s.setdefault(k, v)
        return s
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ---- Telegram ----------------------------------------------------------
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


def _tg(method: str) -> str:
    return f"https://api.telegram.org/bot{TG_TOKEN}/{method}"


def tg_send_video(file_path: str, key: str, caption: str = "") -> int:
    """ローカルmp4を送信し、OK/NGの2ボタンを付ける。message_id を返す。"""
    markup = {"inline_keyboard": [[
        {"text": "✅ OK（投稿する）", "callback_data": f"ok:{key}"},
        {"text": "🗑 NG（捨てる）", "callback_data": f"ng:{key}"},
    ]]}
    with open(file_path, "rb") as f:
        r = requests.post(_tg("sendVideo"), data={
            "chat_id": TG_CHAT,
            "caption": caption or key,
            "reply_markup": json.dumps(markup),
        }, files={"video": f}, timeout=300)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def tg_get_callbacks(offset: int):
    """未処理のボタン押下を取り出す。 (新offset, [(key, action, message_id, callback_id), ...])"""
    r = requests.get(_tg("getUpdates"), params={
        "offset": offset,
        "timeout": 0,
        "allowed_updates": json.dumps(["callback_query"]),
    }, timeout=60)
    r.raise_for_status()
    updates = r.json().get("result", [])
    out = []
    new_offset = offset
    for u in updates:
        new_offset = u["update_id"] + 1
        cq = u.get("callback_query")
        if not cq:
            continue
        data = cq.get("data", "")
        if ":" not in data:
            continue
        action, key = data.split(":", 1)
        out.append((key, action, cq["message"]["message_id"], cq["id"]))
    return new_offset, out


def tg_ack(callback_id: str, text: str):
    requests.post(_tg("answerCallbackQuery"),
                  data={"callback_query_id": callback_id, "text": text},
                  timeout=30)


def tg_mark_message(message_id: int, note: str):
    """承認/却下後にボタンを消し、判定結果をキャプション末尾に追記する。"""
    try:
        requests.post(_tg("editMessageReplyMarkup"), data={
            "chat_id": TG_CHAT, "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": []}),
        }, timeout=30)
    except Exception:
        pass


def tg_notify(text: str):
    if TG_TOKEN and TG_CHAT:
        requests.post(_tg("sendMessage"),
                      data={"chat_id": TG_CHAT, "text": text}, timeout=30)


# ---- GitHub Releases（公開URL置き場）-----------------------------------
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")   # "owner/repo"
RELEASE_TAG = os.environ.get("RELEASE_TAG", "clips")


def _gh_headers():
    return {"Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json"}


def _ensure_release() -> dict:
    """assetを貯めるための固定タグのReleaseを取得（無ければ作成）。"""
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/releases/tags/{RELEASE_TAG}",
        headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()
    r = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/releases",
        headers=_gh_headers(), timeout=30,
        json={"tag_name": RELEASE_TAG, "name": "Leafy clips",
              "body": "自動生成クリップの公開URL置き場（Instagram APIが取得する）"})
    r.raise_for_status()
    return r.json()


def gh_upload_clip(file_path: str, asset_name: str) -> str:
    """mp4をReleaseアセットとしてアップロードし、公開URLを返す。"""
    release = _ensure_release()
    # 同名アセットが残っていたら消してから上げ直す
    for a in release.get("assets", []):
        if a["name"] == asset_name:
            requests.delete(a["url"], headers=_gh_headers(), timeout=30)
    upload_url = release["upload_url"].split("{")[0]
    with open(file_path, "rb") as f:
        r = requests.post(
            f"{upload_url}?name={asset_name}",
            headers={**_gh_headers(), "Content-Type": "video/mp4"},
            data=f.read(), timeout=600)
    r.raise_for_status()
    return r.json()["browser_download_url"]
