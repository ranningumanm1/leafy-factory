"""
量産パイプライン本体。
shotlist.csv を読み、各行ごとに:
  1) LoRAでキーフレーム画像を生成（キャラ固定）
  2) Kling で image-to-video（動かす）
  3) ffmpeg で 9:16 整形 + 字幕を後焼き込み
  4) output/ に書き出し（→ GitHub Actions の成果物として確認）

固定する層 = キャラ（LoRA + トリガー語）。
変える層 = shotlist.csv の中身（ネタ・動き・字幕）。ここだけ毎回いじる。
"""
import os
import csv
import subprocess
import tempfile
import pathlib
import requests
import fal_client

# ---- 設定（環境変数で上書き可。鍵類は Secret から渡る）----
LORA_URL = os.environ["LORA_URL"]                       # 学習済みLoRAのURL（必須）
TRIGGER = os.environ.get("TRIGGER_WORD", "leafy_catspirit")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "fal-ai/flux-lora")
VIDEO_MODEL = os.environ.get("VIDEO_MODEL", "fal-ai/kling-video/v2.1/standard/image-to-video")
# 注意: Klingはバージョンで画像パラメータ名が違う。
#   v2.1 standard/pro => "image_url" / v2.6 pro・v3 => "start_image_url"
VIDEO_IMAGE_PARAM = os.environ.get("VIDEO_IMAGE_PARAM", "image_url")
CAPTION_FONT = os.environ.get(
    "CAPTION_FONT", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
)  # 日本語字幕にCJKフォントは必須
OUT_DIR = pathlib.Path("output")
OUT_DIR.mkdir(exist_ok=True)

# キャラの芯（コンセプトブリーフのキャラクターバイブルと一致させる固定ワード）
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
        "image_size": "portrait_16_9",   # 9:16 縦
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "num_images": 1,
        "output_format": "jpeg",
    })
    return r["images"][0]["url"]


def gen_video(image_url: str, motion_prompt: str, duration: int) -> str:
    args = {
        "prompt": motion_prompt,
        "duration": str(duration),
        "generate_audio": False,   # 音源はInstagram側 or 後工程で付ける
        VIDEO_IMAGE_PARAM: image_url,
    }
    r = fal_client.subscribe(VIDEO_MODEL, arguments=args)
    return r["video"]["url"]


def download(url: str, path: str):
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)


def finalize(raw_video: str, out_path: str, caption: str):
    """9:16に整形し、字幕を後焼き込み（textfileでエスケープ事故を回避）"""
    vf = ("scale=1080:1920:force_original_aspect_ratio=increase,"
          "crop=1080:1920,setsar=1")
    if caption.strip():
        cap_file = tempfile.NamedTemporaryFile("w", suffix=".txt",
                                               delete=False, encoding="utf-8")
        cap_file.write(caption.strip())
        cap_file.close()
        vf += (f",drawtext=fontfile='{CAPTION_FONT}':textfile='{cap_file.name}':"
               "fontcolor=white:fontsize=64:borderw=5:bordercolor=black@0.9:"
               "x=(w-text_w)/2:y=h-300")
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_video, "-vf", vf,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out_path],
        check=True,
    )


def main():
    with open("shotlist.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"[i] {len(rows)} 本を生成する")
    for row in rows:
        sid = row["id"].strip()
        print(f"\n=== shot {sid} ===")
        try:
            img = gen_keyframe(row["image_prompt"])
            print("  keyframe:", img)
            vid = gen_video(img, row["motion_prompt"], int(row.get("duration", 5)))
            print("  raw video:", vid)
            raw_path = OUT_DIR / f"{sid}_raw.mp4"
            download(vid, str(raw_path))
            final_path = OUT_DIR / f"{sid}.mp4"
            finalize(str(raw_path), str(final_path), row.get("caption", ""))
            raw_path.unlink(missing_ok=True)
            print("  done:", final_path)
        except Exception as e:
            print(f"  [!] shot {sid} 失敗: {e}")
    print("\n[i] output/ を確認 → OKな分だけ投稿してね")


if __name__ == "__main__":
    main()
