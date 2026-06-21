"""
キャラ専用LoRAを学習するスクリプト。
使い方:
  1. training_images/ に学習用画像を20〜30枚入れてコミット（角度・表情・ポーズを散らす）
  2. このスクリプトを実行（GitHub Actions の "train-lora" から手動実行 or ローカル）
  3. ログ末尾に出る LORA_URL をコピーして、リポジトリの Secret に LORA_URL として登録
※ fal の API キーは環境変数 FAL_KEY で渡す（自分で設定。コードには絶対書かない）
"""
import os
import glob
import zipfile
import fal_client

DATASET_DIR = os.environ.get("DATASET_DIR", "training_images")
TRIGGER_WORD = os.environ.get("TRIGGER_WORD", "mochi_green_spirit")
TRAIN_STEPS = int(os.environ.get("TRAIN_STEPS", "1000"))


def zip_dataset(folder: str, zip_path: str = "dataset.zip") -> str:
    files = [f for f in glob.glob(os.path.join(folder, "*"))
             if f.lower().endswith((".png", ".jpg", ".jpeg", ".txt"))]
    if not files:
        raise SystemExit(f"[!] {folder}/ に画像が見つからない。20〜30枚入れてね。")
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in files:
            z.write(f, os.path.basename(f))
    print(f"[i] {len(files)} 個のファイルを {zip_path} にまとめた")
    return zip_path


def _log(update):
    if isinstance(update, fal_client.InProgress):
        for line in update.logs:
            print(line["message"])


def main():
    zip_path = zip_dataset(DATASET_DIR)
    images_url = fal_client.upload_file(zip_path)  # fal ストレージに上げてURL化
    print("[i] 学習開始（数分かかる）…")
    result = fal_client.subscribe(
        "fal-ai/flux-lora-fast-training",
        arguments={
            "images_data_url": images_url,
            "trigger_word": TRIGGER_WORD,   # このトリガー語でキャラを呼び出す
            "is_style": False,              # キャラ/被写体の学習なので False
            "steps": TRAIN_STEPS,
        },
        with_logs=True,
        on_queue_update=_log,
    )
    lora_url = result["diffusers_lora_file"]["url"]
    print("\n=========================================")
    print("LORA_URL=", lora_url)
    print("↑ これを Secret(LORA_URL) に登録すれば学習完了")
    print("=========================================")


if __name__ == "__main__":
    main()
