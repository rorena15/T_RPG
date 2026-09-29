"""진단 기록(diag/*.sdg) 개발자 도구: 키 만들기, 읽기.

  python tools/diag/diag_tool.py genkey [--key 경로]          # 한 번만. 개인키를 저장소 밖에 저장, 개발/diag_pubkey.py에 공개키
  python tools/diag/diag_tool.py read 파일.sdg [...] [--key 경로] [--json] [--kind log|trace]

개인키 기본 위치: ~/.stigma/diag_key.json (STIGMA_DIAG_KEY 환경 변수나 --key로 바꾼다).
개인키는 절대 저장소에 넣지 않는다. 잃으면 그 키로 암호화된 진단 파일은 영영 못 읽는다 (백업 필수).
파일 형식은 개발/diag.py 설명 참고.
"""
import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, "..", ".."))
PUBKEY_PY = os.path.join(GAME, "diag_pubkey.py")
DEFAULT_KEY = os.environ.get("STIGMA_DIAG_KEY", os.path.join(os.path.expanduser("~"), ".stigma", "diag_key.json"))

sys.path.insert(0, GAME)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import diag  # MAGIC, derive_key


def _raw_pub(pub):
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def genkey(path):
    if os.path.exists(path):
        sys.exit(f"이미 있다: {path}\n  새로 만들면 예전 진단 파일을 못 읽는다. 정말이면 파일을 옮기고 다시 실행.")
    priv = X25519PrivateKey.generate()
    raw = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = _raw_pub(priv.public_key()).hex()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"private": raw.hex(), "public": pub}, f)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    src = open(PUBKEY_PY, encoding="utf-8").read()
    import re
    src = re.sub(r'DIAG_PUBLIC_KEY = "[0-9a-fA-F]*"', f'DIAG_PUBLIC_KEY = "{pub}"', src)
    open(PUBKEY_PY, "w", encoding="utf-8").write(src)
    print(f"개인키: {path}  (백업해 두세요, 저장소에 넣지 마세요)")
    print(f"공개키: {pub}  → {PUBKEY_PY} 에 썼습니다. 커밋하면 다음 빌드부터 진단 기록이 켜집니다.")


def load_key(path):
    try:
        k = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"개인키가 없다: {path}  (--key로 지정)")
    priv = X25519PrivateKey.from_private_bytes(bytes.fromhex(k["private"]))
    return priv, _raw_pub(priv.public_key())


def read_file(path, priv, dev_pub):
    """파일 하나의 기록들을 차례로 돌려준다. 잘린 마지막 기록(게임이 튕긴 순간)은 건너뛴다."""
    data = open(path, "rb").read()
    if data[:4] != diag.MAGIC:
        raise ValueError("진단 파일이 아니다")
    eph_pub = data[4:36]
    aead = AESGCM(diag.derive_key(priv.exchange(X25519PublicKey.from_public_bytes(eph_pub)), eph_pub, dev_pub))
    i = 36
    while i + 4 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        if i + 16 + n > len(data):
            break
        nonce, ct = data[i + 4:i + 16], data[i + 16:i + 16 + n]
        i += 16 + n
        yield json.loads(aead.decrypt(nonce, ct, diag.MAGIC))


def fmt(r):
    if r.get("k") == "log":
        return f"[{r.get('t')}] [{r.get('lv')}] {r.get('msg')}"
    ok = "" if r.get("success", 1) else f"  !! {r.get('error_type')}: {r.get('error_message')}"
    hp = f"  hp={r['player_hp']}" if r.get("player_hp") is not None else ""
    return f"[{r.get('timestamp')}] {r.get('func_name')} ({r.get('duration_ms')}ms){hp}{ok}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("genkey")
    g.add_argument("--key", default=DEFAULT_KEY)
    r = sub.add_parser("read")
    r.add_argument("files", nargs="+")
    r.add_argument("--key", default=DEFAULT_KEY)
    r.add_argument("--json", action="store_true", help="기록을 JSON 한 줄씩 그대로")
    r.add_argument("--kind", choices=["log", "trace"], help="이 종류만")
    a = ap.parse_args()
    if a.cmd == "genkey":
        return genkey(a.key)
    priv, dev_pub = load_key(a.key)
    for path in a.files:
        print(f"── {os.path.basename(path)}")
        try:
            for rec in read_file(path, priv, dev_pub):
                if a.kind and rec.get("k") != a.kind:
                    continue
                print(json.dumps(rec, ensure_ascii=False) if a.json else fmt(rec))
        except Exception as e:
            print(f"  읽지 못함: {type(e).__name__}: {e}  (다른 키로 암호화된 파일일 수 있다)")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:   # | head 등으로 출력을 끊었을 때
        sys.stderr.close()
