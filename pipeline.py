"""
生成パイプライン（クラウド側＝GitHub Actionsで自動運転）。
  1) shotlist.csv = ネタ貯金 から「未使用(status空)」を先頭N件だけ取り出す
  2) 各件: LoRAでキーフレーム → Kling で動画 → ffmpeg で 9:16 整形（字幕は焼かない）
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

CHAR_CORE = (
    "original chibi mascot cat, 2-head-tall, fluffy lime-green fur, white face and belly, "
    "a green swirl mark on the belly, large round expressive eyes, "
    "tiny triangular cat ears with sunny-yellow inner, small leaf-shaped spikes around the head, "
    "heart-shaped leaf tail tip, small leaf cape with a gold clasp, "
    "soft plush toy texture, cute genuine smile, soft 3D cartoon render"
)
NEG = ("fire, flame, magical aura, glowing powers, collectible monster, game creature, "
       "branded product, logo, human proportions, realistic skin, scary, text, watermark, "
       "resembling any existing franchise character")


def gen_keyframe(image_prompt: str) -> str:
    r = fal_client.subscribe(IMAGE_MODEL, arguments={
        "prompt": f"{TRIGGER}, {CHAR_CORE}, {image_prompt}, clean simple background",
        "negative_prompt": NEG,
        "loras": [{"path": LORA_URL, "scale": 1.0}],
        "image_size": "portrait_16_9",
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "num_images": 1,
        "output_format": "jpeg",
    })
    return r["images"][0]["url"]


def gen_video(image_url: str, motion_prompt: str, duration: int) -> str:
    r = fal_client.subscribe(VIDEO_MODEL, arguments={
        "prompt": motion_prompt,
        "duration": str(duration),
        "generate_audio": False,
        VIDEO_IMAGE_PARAM: image_url,
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
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out_path],
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


def upload_clip(file_path: str, asset_name: str) -> str:
    """mp4をReleaseアセットとしてアップロードし、公開URLを返す。"""
    release = _ensure_release()
    for a in release.get("assets", []):
        if a["name"] == asset_name:
            requests.delete(a["url"], headers=_gh_headers(), timeout=30)
    upload_url = release["upload_url"].split("{")[0]
    with open(file_path, "rb") as f:
        r = requests.post(f"{upload_url}?name={asset_name}",
                          headers={**_gh_headers(), "Content-Type": "video/mp4"},
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
    print(f"[i] {len(todo)} 本を生成する（残り未使用: {remaining} 本）")

    made = 0
    for row in todo:
        sid = row["id"].strip()
        key = f"{RUN_ID}_{sid}"
        print(f"\n=== shot {key} ===")
        try:
            img = gen_keyframe(row["image_prompt"])
            vid = gen_video(img, row["motion_prompt"], int(row.get("duration", 5) or 5))
            raw_path = OUT_DIR / f"{key}_raw.mp4"
            final_path = OUT_DIR / f"{key}.mp4"
            download(vid, str(raw_path))
            finalize(str(raw_path), str(final_path), row.get("caption", ""))
            raw_path.unlink(missing_ok=True)

            public_url = upload_clip(str(final_path), f"{key}.mp4")
            row["status"] = f"gen:{RUN_ID}"   # 使用済み（失敗時は空のまま＝次回再挑戦）
            made += 1
            print("  done:", public_url)
        except Exception as e:
            print(f"  [!] shot {key} 失敗: {e}")

    write_backlog(fieldnames, rows)
    print(f"\n[i] 完成 {made} 本。Mac の fetch_clips.command で写真アプリに取り込めます")


if __name__ == "__main__":
    main()
