"""진단 기록 (개발자만 읽을 수 있게 암호화).

시스템 로그·오류·크래시·함수 호출 추적을 diag/ 폴더의 파일에 쓴다. 게임에는 개발자의 공개키만 들어 있어서
플레이어 PC의 파일은 누구도 읽을 수 없고, 개발자가 개인키로만 푼다 (tools/diag/diag_tool.py read).
버그 제보 때 플레이어는 diag/ 폴더의 최근 파일을 보내 주면 된다.

암호: 실행마다 임시 X25519 키를 만들어 개발자 공개키와 합의(ECDH) → HKDF-SHA256 → AES-256-GCM.
파일 = b"SDG1" + 임시 공개키(32) + 기록들. 기록 = 길이(4, big) + nonce(12) + 암호문(태그 포함).
기록마다 따로 암호화해 이어 쓰므로 게임이 튕겨도 그 직전 기록까지 남는다.

공개키(diag_pubkey.py)가 없거나 cryptography를 못 쓰면 아무것도 쓰지 않는다 (평문으로 남기지 않는다).
보관: 진단 파일은 계속 보관한다 (게임이 지우지 않는다, 개발자 결정).
"""
import datetime
import json
import os
import struct
import sys
import threading

MAGIC = b"SDG1"
INFO = b"stigma-diag v1"

_lock = threading.Lock()
_state = None   # None: 아직 안 엶 / False: 못 씀 / dict: 열린 파일과 암호


def diag_dir():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.abspath(".")
    return os.path.join(base, "diag")


def _public_key_bytes():
    try:
        from diag_pubkey import DIAG_PUBLIC_KEY
        key = bytes.fromhex(DIAG_PUBLIC_KEY.strip())
        return key if len(key) == 32 else None
    except Exception:
        return None


def derive_key(shared, eph_pub, dev_pub):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=eph_pub + dev_pub, info=INFO).derive(shared)


def _open(session_id):
    global _state
    dev_pub = _public_key_bytes()
    if dev_pub is None:
        _state = False
        return
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives import serialization
        eph = X25519PrivateKey.generate()
        eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        shared = eph.exchange(X25519PublicKey.from_public_bytes(dev_pub))
        aead = AESGCM(derive_key(shared, eph_pub, dev_pub))
        os.makedirs(diag_dir(), exist_ok=True)
        name = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + f"_{session_id[:8]}.sdg"
        f = open(os.path.join(diag_dir(), name), "ab")
        f.write(MAGIC + eph_pub)
        f.flush()
        _state = {"f": f, "aead": aead, "n": 0}
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:   # 깨진 cryptography(PanicException 등)도 게임을 멈추지 않게: 기록만 끈다
        _state = False


def write(kind, payload, session_id):
    """기록 한 줄 (kind: log / trace). 실패해도 게임에는 영향을 주지 않는다."""
    with _lock:
        if _state is None:
            _open(session_id)
        if not _state:
            return
        try:
            _state["n"] += 1
            nonce = b"\0\0\0\0" + struct.pack(">Q", _state["n"])
            data = json.dumps({"k": kind, **payload}, ensure_ascii=False, default=str).encode("utf-8")
            ct = _state["aead"].encrypt(nonce, data, MAGIC)
            _state["f"].write(struct.pack(">I", len(ct)) + nonce + ct)
            _state["f"].flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            pass


def enabled():
    """공개키가 있고 암호 라이브러리를 실제로 쓸 수 있을 때만."""
    if _public_key_bytes() is None:
        return False
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        AESGCM(b"\0" * 32)
        return True
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return False


def purge_plain_logs():
    """예전 버전이 평문으로 남긴 기록을 지운다 (log.txt, stigma_data.db의 events 표). 암호화 기록을 쓸 수 있을 때만."""
    if not enabled():
        return
    base = os.path.abspath(".")   # 예전 기록은 현재 폴더 기준 상대 경로로 쓰였다 (sys_log·core와 같게)
    try:
        p = os.path.join(base, "log.txt")
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass
    try:
        import sqlite3
        db = os.path.join(base, "stigma_data.db")
        if os.path.exists(db):
            with sqlite3.connect(db) as c:
                if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone():
                    c.execute("DROP TABLE events")
                    c.commit()
                    c.execute("VACUUM")
    except Exception:
        pass
