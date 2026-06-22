"""
生成パイプライン（クラウド側＝GitHub Actionsで自動運転）。
  1) shotlist.csv = ネタ貯金 から「未使用(status空)」を先頭N件だけ取り出す
  2) 各件: LoRAでキーフレーム → Kling で動画 → mmaudioで動きに合う効果音 → ffmpeg 9:16整形（字幕なし）
  3) 最終mp4を GitHub Releases にアップ（= Macが取りに来られる公開URL）
  4) shotlist.csv の該当行を使用済みに印（次回は次のネタへ進む）

完成クリップの受け取りは Mac 側の mac/fetch_clips.command が担当（Releasesから写真アプリへ）。
投稿は人が手動。ここは「作って置いておく」までが仕事。
"""
import os
import csv
import subprocess
import tempfile
import pathlib
import datetime
import requests
import fal_client

LORA_URL = os.environ["LORA_URL"]
TRIGGER = os.environ.get("TRIGGER_WORD", "leafy_catspirit")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "fal-ai/flux-lora")
VIDEO_MODEL = os.environ.get("VIDEO_MODEL", "fal-ai/kling-video/v2.1/standard/image-to-video")
VIDEO_IMAGE_PARAM = os.environ.get("VIDEO_IMAGE_PARAM", "image_url")
# 効果音: fal mmaudio が動画を見て、動きに同期した音を生成する
AUDIO_MODEL = os.environ.get("AUDIO_MODEL", "fal-ai/mmaudio-v2")
ADD_AUDIO = os.environ.get("ADD_AUDIO", "1") not in ("0", "false", "False", "")
SFX_NEG = os.environ.get(
    "SFX_NEG", "music, song, melody, human voice, speech, lyrics, harsh noise, distortion")
# モード: image=falでキャラ画像だけ生成（安い・Klingで動画化） / video=falで動画まで（高い）
MODE = os.environ.get("MODE", "image")
IMAGE_ONLY = MODE.strip().lower() != "video"
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
RUN_ID = os.environ.get("GITHUB_RUN_NUMBER") or datetime.date.today().isoformat()
CAPTION_FONT = os.environ.get(
    "CAPTION_FONT", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
SHOTLIST = "shotlist.csv"
OUT_DIR = pathlib.Path("output")
OUT_DIR.mkdir(exist_ok=True)

# GitHub Releases（完成クリップの公開URL置き場。MacがここからDLする）
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
RELEASE_TAG = os.environ.get("RELEASE_TAG", "clips")

# キャラの芯（CHARACTER.md の公式設定と一致させる固定ワード）
CHAR_CORE = (
    "original chibi plush cat spirit, 2-head-tall, fluffy lime-green fur, "
    "white face belly and paw-tips, pink paw pads, "
    "large round expressive green eyes, pink blush cheeks, cheerful smile with a tiny fang, "
    "a small orange-gold flower mark on the forehead, "
    "triangular cat ears with sunny-yellow inner and a small white flower at the inner base, "
    "green leaf-shaped spikes around the head with a curled green sprout on top, "
    "a green swirl leaf mark on the belly (Leafy's emblem), "
    "heart-shaped leaf tail tip with a gold swirl that curls, "
    "small green leaf cape with gold trim and an acorn pendant clasp, "
    "soft plush toy texture, soft 3D cartoon render, whimsical storybook style"
)
NEG = ("fire, flame, magical aura, glowing powers, collectible monster, game creature, "
       "branded product, logo, human proportions, realistic skin, scary, text, watermark, "
       "resembling any existing franchise character, "
       "plain white background, blank studio backdrop, empty background")

# フレーミング固定句（最重要・縦動画の着地を守る）。
# Klingは「転ぶ/倒れる」等の大きな動作で勝手にカメラを引き、画面外＝横方向の世界を
# 生成して「枠が横に伸びる」事故を起こす。これを毎回のmotion_promptに自動付与して封じる。
FRAMING_LOCK = (
    "vertical 9:16 portrait framing held for the entire clip, "
    "locked static camera, no zoom, no dolly, no pull-back, no camera shake, "
    "the character stays fully inside the vertical frame at all times, "
    "all motion contained within the portrait frame, "
    "no horizontal expansion, no widening, no letterboxing, no scene reveal to the sides")

# 背景の世界観（ここを差し替えれば季節・舞台を変えられる）
BACKGROUND = os.environ.get(
    "BACKGROUND",
    "in a cozy autumn forest, warm golden-hour light, colorful red and orange fallen maple leaves, "
    "soft blurred bokeh autumn trees, gentle depth of field, whimsical storybook atmosphere")


def gen_keyframe(image_prompt: str) -> str:
    r = fal_client.subscribe(IMAGE_MODEL, arguments={
        "prompt": f"{TRIGGER}, {CHAR_CORE}, {image_prompt}, {BACKGROUND}",
        "negative_prompt": NEG,
        "loras": [{"path": LORA_URL, "scale": 1.0}],
        "image_size": "portrait_16_9",
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "num_images": 1,
        "output_format": "jpeg",
    })
    return r["images"][0]["url"]


def lock_framing(motion_prompt: str) -> str:
    """motion_prompt に縦9:16維持の固定句を必ず付ける（重複時は付けない）。"""
    mp = (motion_prompt or "").strip().rstrip(",")
    if "vertical 9:16 portrait framing held" in mp:
        return mp
    return f"{mp} — {FRAMING_LOCK}" if mp else FRAMING_LOCK


def gen_video(image_url: str, motion_prompt: str, duration: int) -> str:
    r = fal_client.subscribe(VIDEO_MODEL, arguments={
        "prompt": lock_framing(motion_prompt),
        "duration": str(duration),
        "generate_audio": False,   # 音は mmaudio で別途・動きに合わせて付ける
        VIDEO_IMAGE_PARAM: image_url,
    })
    return r["video"]["url"]


def gen_audio(video_url: str, motion_prompt: str) -> str:
    """動画を見て、動きに同期した可愛い効果音を生成（音入り動画のURLを返す）。"""
    prompt = ("cute playful cartoon sound effects, "
              "soft squishy plush footsteps, puni-puni squishy paw steps, gentle padding steps, "
              "soft bouncy boing, gentle plop and tumble, light squeaky-toy pops, "
              "springy cartoon foley, kawaii and wholesome, "
              "matching the action: " + motion_prompt)
    r = fal_client.subscribe(AUDIO_MODEL, arguments={
        "video_url": video_url,
        "prompt": prompt,
        "negative_prompt": SFX_NEG,
    })
    return r["video"]["url"]


def download(url: str, path: str):
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)


def finalize(raw_video: str, out_path: str, caption: str):
    """9:16整形。caption が空なら字幕は焼かない（運用は字幕なし）。"""
    vf = ("scale=1080:1920:force_original_aspect_ratio=increase,"
          "crop=1080:1920,setsar=1")
    if caption.strip():
        cap = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                          encoding="utf-8")
        cap.write(caption.strip())
        cap.close()
        vf += (f",drawtext=fontfile='{CAPTION_FONT}':textfile='{cap.name}':"
               "fontcolor=white:fontsize=64:borderw=5:bordercolor=black@0.9:"
               "x=(w-text_w)/2:y=h-300")
    subprocess.run(["ffmpeg", "-y", "-i", raw_video, "-vf", vf,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", out_path],
                   check=True)


def _gh_headers():
    return {"Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json"}


def _ensure_release() -> dict:
    r = requests.get(
        f"https://api.github.com/repos/{GH_REPO}/releases/tags/{RELEASE_TAG}",
        headers=_gh_headers(), timeout=30)
    if r.status_code == 200:
        return r.json()
    r = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/releases",
        headers=_gh_headers(), timeout=30,
        json={"tag_name": RELEASE_TAG, "name": "Leafy clips",
              "body": "自動生成クリップの置き場（Macが取りに来る）"})
    r.raise_for_status()
    return r.json()


def upload_asset(file_path: str, asset_name: str, content_type: str = "video/mp4") -> str:
    """ファイルをReleaseアセットとしてアップロードし、公開URLを返す。"""
    release = _ensure_release()
    for a in release.get("assets", []):
        if a["name"] == asset_name:
            requests.delete(a["url"], headers=_gh_headers(), timeout=30)
    upload_url = release["upload_url"].split("{")[0]
    with open(file_path, "rb") as f:
        r = requests.post(f"{upload_url}?name={asset_name}",
                          headers={**_gh_headers(), "Content-Type": content_type},
                          data=f.read(), timeout=600)
    r.raise_for_status()
    return r.json()["browser_download_url"]


def write_backlog(fieldnames, rows):
    with open(SHOTLIST, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    with open(SHOTLIST, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    todo = [r for r in rows if not r.get("status", "").strip()][:BATCH_SIZE]
    if not todo:
        print("[i] 未使用ネタなし。shotlist.csv に行を足してください。終了")
        return
    remaining = sum(1 for r in rows if not r.get("status", "").strip())
    print(f"[i] モード: {MODE}（画像のみ={IMAGE_ONLY}）")
    print(f"[i] {len(todo)} 本を生成する（残り未使用: {remaining} 本）")

    made = 0
    queue = []   # 画像のみモード用: (key, 公開URL, 動きプロンプト) をためてKling用一覧にする
    for row in todo:
        sid = row["id"].strip()
        key = f"{RUN_ID}_{sid}"
        print(f"\n=== shot {key} ===")
        try:
            img = gen_keyframe(row["image_prompt"])
            if IMAGE_ONLY:
                # falは画像だけ。動画化は Kling.ai Pro で手動（コスト削減）
                img_path = OUT_DIR / f"{key}.jpg"
                download(img, str(img_path))
                public_url = upload_asset(str(img_path), f"{key}.jpg", "image/jpeg")
                row["status"] = f"img:{RUN_ID}"
                made += 1
                queue.append((key, public_url, row["motion_prompt"]))
                print("  image:", public_url)
                continue
            vid = gen_video(img, row["motion_prompt"], int(row.get("duration", 5) or 5))
            if ADD_AUDIO:
                try:
                    vid = gen_audio(vid, row["motion_prompt"])
                    print("  + 効果音を付与")
                except Exception as ae:
                    print(f"  [!] 効果音の付与に失敗（無音で続行）: {ae}")
            raw_path = OUT_DIR / f"{key}_raw.mp4"
            final_path = OUT_DIR / f"{key}.mp4"
            download(vid, str(raw_path))
            finalize(str(raw_path), str(final_path), row.get("caption", ""))
            raw_path.unlink(missing_ok=True)

            public_url = upload_asset(str(final_path), f"{key}.mp4")
            row["status"] = f"gen:{RUN_ID}"   # 使用済み（失敗時は空のまま＝次回再挑戦）
            made += 1
            print("  done:", public_url)
        except Exception as e:
            print(f"  [!] shot {key} 失敗: {e}")

    if IMAGE_ONLY and queue:
        lines = ["# リーフィー Kling キュー（最新バッチ）",
                 "# Klingに渡す設定: アスペクト比 9:16（縦）固定 / 長さ 10秒 / 音声と映像の同期=オン",
                 "# 重要: 生成中に『延長(extend)』や『ズームアウト』は使わない。最後まで縦9:16のまま。",
                 "# 各画像はURLをそのままKlingに貼れます（ファイル不要）", ""]
        for i, (k, u, p) in enumerate(queue, 1):
            lines += [f"[{i}] {k}", f"  画像URL: {u}",
                      f"  プロンプト: {lock_framing(p)}", ""]
        qpath = OUT_DIR / "kling_queue.txt"
        qpath.write_text("\n".join(lines), encoding="utf-8")
        upload_asset(str(qpath), "kling_queue.txt", "text/plain")
        print("  kling_queue.txt を更新（URL+プロンプト一覧）")

    write_backlog(fieldnames, rows)
    print(f"\n[i] 完成 {made} 本。Mac の fetch_clips.command で取り込めます")


if __name__ == "__main__":
    main()
