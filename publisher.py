"""
公開パイプライン（自動運転の後半）。毎時cronで回る想定。
  1) Telegram のボタン押下を回収 → state.json の各クリップを approved / rejected に更新
  2) 承認済み(approved)で未投稿のものを「1日N本」までドリップで Instagram に公開
  3) 状態を保存（投稿済みは posted に）

常駐サーバーは不要。毎時 getUpdates でボタンを拾うので、押し忘れない限り取りこぼさない。
人がやるのは Telegram のボタンだけ。ここは完全自動。
"""
import os
import time
import datetime
import requests

import common

IG_USER_ID = os.environ.get("IG_USER_ID", "")
IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
GRAPH = "https://graph.facebook.com/v21.0"
POSTS_PER_DAY = int(os.environ.get("POSTS_PER_DAY", "1"))
POST_CAPTION = os.environ.get(
    "POST_CAPTION",
    "leafy がんばる🌱 #leafy #リーフィー #ショート動画 #癒し #マスコット")


def jst_today() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date().isoformat()


def collect_approvals(state: dict):
    """Telegramのボタンを回収して状態を更新。"""
    offset, events = common.tg_get_callbacks(state.get("tg_offset", 0))
    state["tg_offset"] = offset
    for key, action, message_id, cb_id in events:
        clip = state["clips"].get(key)
        if not clip:
            common.tg_ack(cb_id, "対象が見つかりません")
            continue
        if clip["status"] in ("posted",):
            common.tg_ack(cb_id, "投稿済みです")
            continue
        if action == "ok":
            clip["status"] = "approved"
            common.tg_ack(cb_id, "OK！投稿待ちに入れました")
        elif action == "ng":
            clip["status"] = "rejected"
            common.tg_ack(cb_id, "了解、捨てます")
        common.tg_mark_message(message_id, action)


def ig_publish(video_url: str, caption: str):
    """Reelsとして公開。container作成→FINISHED待ち→publish。"""
    r = requests.post(f"{GRAPH}/{IG_USER_ID}/media", data={
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "access_token": IG_TOKEN}, timeout=60)
    r.raise_for_status()
    creation_id = r.json()["id"]

    # 動画の取り込み完了を待つ（最大~5分）
    for _ in range(30):
        s = requests.get(f"{GRAPH}/{creation_id}",
                         params={"fields": "status_code", "access_token": IG_TOKEN},
                         timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"IG取り込みエラー: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("IG取り込みがタイムアウト")

    p = requests.post(f"{GRAPH}/{IG_USER_ID}/media_publish",
                      data={"creation_id": creation_id, "access_token": IG_TOKEN},
                      timeout=60)
    p.raise_for_status()
    return p.json().get("id")


def drip_publish(state: dict):
    today = jst_today()
    if state.get("last_post_date") != today:
        state["last_post_date"] = today
        state["posts_today"] = 0

    while state["posts_today"] < POSTS_PER_DAY:
        # 古い承認分から順に投稿
        nxt = None
        for key, clip in sorted(state["clips"].items(),
                                key=lambda kv: kv[1].get("created", "")):
            if clip["status"] == "approved":
                nxt = (key, clip)
                break
        if not nxt:
            break
        key, clip = nxt
        try:
            post_id = ig_publish(clip["url"], POST_CAPTION)
            clip["status"] = "posted"
            clip["ig_post_id"] = post_id
            state["posts_today"] += 1
            state["last_post_date"] = today
            common.tg_notify(f"📤 Instagramに公開しました: {key}")
        except Exception as e:
            common.tg_notify(f"⚠️ 投稿失敗 {key}: {e}")
            print(f"[!] publish失敗 {key}: {e}")
            break   # 失敗時はそれ以上進めない（次のcronで再試行）


def main():
    state = common.load_state()
    collect_approvals(state)
    if IG_USER_ID and IG_TOKEN:
        drip_publish(state)
    else:
        print("[i] IG資格情報が未設定。承認の回収のみ実施")
    common.save_state(state)
    waiting = sum(1 for c in state["clips"].values() if c["status"] == "approved")
    print(f"[i] 投稿待ち(approved): {waiting} 本 / 本日投稿: {state['posts_today']} 本")


if __name__ == "__main__":
    main()
