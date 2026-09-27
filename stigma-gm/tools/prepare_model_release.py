"""배포용 모델(암호화한 GGUF)을 GitHub 릴리스 제한(파일당 2GiB 미만)에 맞게 조각내고, 게임이 쓸 manifest를 만든다.

업로드는 하지 않는다 (공개 배포라 사람이 확인한 뒤 `gh release upload`로 올린다).
  실행:  python tools/prepare_model_release.py --tag models-v1
결과:  E:/Git_Project/stigma-train/release/<tag>/ 에 조각 파일과 manifest.json
"""
import argparse
import hashlib
import json
import os

import model_crypt

PART_BYTES = 1_900_000_000  # GitHub 릴리스 파일당 2GiB 미만
MODELS = {  # 게임 설정의 모드 → 암호화한 GGUF (tools/model_crypt.py encrypt, 키 태그 = 릴리스 태그)
    "full": "E:/Git_Project/stigma-train/models/enc/stigma-gm-full.dat",
    "lite": "E:/Git_Project/stigma-train/models/enc/stigma-gm-lite.dat",
}
REPO = "rorena15/T_RPG"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="models-v1")
    p.add_argument("--out", default="E:/Git_Project/stigma-train/release")
    args = p.parse_args()
    out_dir = os.path.join(args.out, args.tag)
    os.makedirs(out_dir, exist_ok=True)
    for stale in os.listdir(out_dir):  # 예전 조각(평문 시절 포함)이 같이 올라가지 않게 비운다
        if ".part" in stale or stale == "manifest.json":
            os.remove(os.path.join(out_dir, stale))
    base_url = f"https://github.com/{REPO}/releases/download/{args.tag}/"
    manifest = {"tag": args.tag, "models": {}}
    for mode, path in MODELS.items():
        if not model_crypt.check(args.tag, path):  # 평문이나 다른 키로 암호화한 파일은 절대 올리지 않는다
            raise SystemExit(f"{path}: {args.tag} 키로 암호화된 파일이 아님")
        name = os.path.basename(path)
        whole = hashlib.sha256()
        parts = []
        with open(path, "rb") as f:
            i = 0
            while True:
                chunk_hash, written = hashlib.sha256(), 0
                part_name = f"{name}.part{i + 1}"
                with open(os.path.join(out_dir, part_name), "wb") as out:
                    while written < PART_BYTES:
                        buf = f.read(min(8 << 20, PART_BYTES - written))
                        if not buf:
                            break
                        out.write(buf)
                        whole.update(buf)
                        chunk_hash.update(buf)
                        written += len(buf)
                if written == 0:
                    os.remove(os.path.join(out_dir, part_name))
                    break
                parts.append({"url": base_url + part_name, "size": written, "sha256": chunk_hash.hexdigest()})
                i += 1
        manifest["models"][mode] = {"file": name, "size": os.path.getsize(path), "sha256": whole.hexdigest(),
                                    "parts": parts}
        print(f"{mode}: {name} -> {len(parts)} part(s)")
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
