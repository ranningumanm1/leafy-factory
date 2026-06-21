"""
生成パイプライン（週次の自動運転の前半）。
  1) shotlist.csv = ネタ貯金 から「未使用(status空)」を先頭N件だけ取り出す
  2) 各件: LoRAでキーフレーム → Kling で動画 → ffmpeg で 9:16 整形（字幕は焼かない）
  3) 最終mp4を GitHub Releases にアップ（= Instagram が取得できる公開URL）
  4) Telegram に OK/NG ボタン付きで配信し、state.json に「承認待ち」で登録
  5) shotlist.csv の該当行を使用済みに印（次回は次のネタへ進む）

固定する層 = キャラ（LoRA + トリガー語）。変える層 = shotlist.csv のネタだけ。
人がやるのは Telegram で OK/NG を押すことだけ。投稿は publisher.py が自動でやる。
"""
import os
import csv
import subprocess
import tempfile
import pathlib
import datetime
import requests
import fal_client

import common

LORA_URL = os.environ["LORA_URL"]
TRIGGER = os.environ.get("TRIGGER_WORD", "leafy_catspirit")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "fal-ai/flux-lora")
VIDEO_MODEL = os.environ.get("VIDEO_MODEL", "fal-ai/kling-video/v2.1/standard/image-to-video")
VIDEO_IMAGE_PARAM = os.environ.get("VIDEO_IMAGE_PARAM", "image_url")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))   # 1回の自動運転で生成する本数
RUN_ID = os.environ.get("GITHUB_RUN_NUMBER") or datetime.date.today().isoformat()
CAPTION_FONT = os.environ.get(
    "CAPTION_FONT", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
SHOTLIST = "shotlist.csv"
OUT_DIR = pathlib.Path("output")
OUT_DIR.mkdir(exist_ok=True)

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
        common.tg_notify("⚠️ ネタ貯金(shotlist.csv)が尽きました。新しいネタを足してください。")
        print("[i] 未使用ネタなし。終了")
        return
    print(f"[i] {len(todo)} 本を生成する（残り未使用: "
          f"{sum(1 for r in rows if not r.get('status','').strip())} 本）")

    state = common.load_state()
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

            public_url = common.gh_upload_clip(str(final_path), f"{key}.mp4")
            msg_id = common.tg_send_video(str(final_path), key,
                                          caption=f"leafy {key}\nOKを押すと自動投稿待ちに入ります")
            state["clips"][key] = {
                "url": public_url,
                "caption": row.get("caption", ""),
                "status": "pending",
                "tg_message_id": msg_id,
                "created": datetime.datetime.utcnow().isoformat(timespec="seconds"),
            }
            row["status"] = f"gen:{RUN_ID}"   # 使用済みに印（失敗時は空のまま＝次回再挑戦）
            print("  done:", public_url)
        except Exception as e:
            print(f"  [!] shot {key} 失敗: {e}")

    common.save_state(state)
    write_backlog(fieldnames, rows)
    common.tg_notify(f"🌱 新しいクリップを {len(todo)} 本お届けしました。"
                     f"OK/NG を選んでね（OKは1日1本ずつ自動投稿されます）")
    print("\n[i] Telegram を確認 → OK/NG を押す")


if __name__ == "__main__":
    main()
