"""패치한 llama-server 확인 스크립트 (Linux·Mac 빌드, CI에서도 쓴다).
배포용 설정·모델은 쓰지 않고, 시험용 설정과 작은 무작위 모델로 로드·생성이 되는지 본다.

  python smoke_test.py genkey --src LLAMA_SRC --out testkey.json   # 빌드 전에
  bash build_server.sh LLAMA_SRC
  python smoke_test.py run --src LLAMA_SRC --server LLAMA_SRC/build-stigma/bin/llama-server --key testkey.json
필요: numpy, cryptography
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))   # stigma-gm/tools
import model_crypt  # noqa: E402


def c_array(b):
    return ", ".join(f"0x{x:02x}" for x in b)


def genkey(src, out):
    """model_crypt.emit과 같은 모양의 stigma-key.inc (시험용 키)."""
    a, b = secrets.token_bytes(32), secrets.token_bytes(32)
    m1 = secrets.token_bytes(32)
    m2 = bytearray(32)
    for i in range(32):
        m2[31 - i] = a[i] ^ m1[i] ^ ((i * 37 + 11) & 0xFF)
    with open(os.path.join(src, "ggml", "src", "stigma-key.inc"), "w", newline="\n") as f:
        f.write("// TEST KEY (smoke_test.py) - not the release key\n")
        f.write("static void stigma_bin_half(uint8_t out[32]) {\n")
        f.write(f"    static const volatile uint8_t m1[32] = {{ {c_array(m1)} }};\n")
        f.write(f"    static const volatile uint8_t m2[32] = {{ {c_array(m2)} }};\n")
        f.write("    for (int i = 0; i < 32; i++) {\n")
        f.write("        out[i] = (uint8_t) (m1[i] ^ m2[31 - i] ^ (uint8_t) (i*37 + 11));\n")
        f.write("    }\n}\n")
    with open(out, "w") as f:
        json.dump({"bin_half": a.hex(), "game_half": b.hex()}, f)
    print(f"test key -> {out}")


def tiny_model(src, path):
    """토크나이저는 llama.cpp의 어휘 파일에서, 가중치는 무작위. 말은 헛소리지만 끝까지 로드·생성돼야 한다."""
    import numpy as np
    sys.path.insert(0, os.path.join(src, "gguf-py"))
    import gguf
    voc = gguf.GGUFReader(os.path.join(src, "models", "ggml-vocab-llama-spm.gguf"))
    w = gguf.GGUFWriter(path, "llama")
    E, L, H, FF = 64, 2, 4, 128
    w.add_context_length(256); w.add_embedding_length(E); w.add_block_count(L); w.add_feed_forward_length(FF)
    w.add_head_count(H); w.add_head_count_kv(H); w.add_layer_norm_rms_eps(1e-5); w.add_rope_dimension_count(E // H)
    w.add_file_type(gguf.LlamaFileType.ALL_F32)
    put = {"tokenizer.ggml.model": w.add_tokenizer_model, "tokenizer.ggml.tokens": w.add_token_list,
           "tokenizer.ggml.scores": w.add_token_scores, "tokenizer.ggml.token_type": w.add_token_types,
           "tokenizer.ggml.bos_token_id": w.add_bos_token_id, "tokenizer.ggml.eos_token_id": w.add_eos_token_id,
           "tokenizer.ggml.unknown_token_id": w.add_unk_token_id}
    for f in voc.fields.values():
        if f.name in put:
            put[f.name](f.contents())
    n_vocab = len(voc.fields["tokenizer.ggml.tokens"].contents())
    rng = np.random.default_rng(0)
    r = lambda *s: (rng.standard_normal(s) * 0.02).astype(np.float32)  # noqa: E731
    w.add_tensor("token_embd.weight", r(n_vocab, E))
    w.add_tensor("output_norm.weight", np.ones(E, np.float32))
    w.add_tensor("output.weight", r(n_vocab, E))
    for i in range(L):
        p = f"blk.{i}."
        w.add_tensor(p + "attn_norm.weight", np.ones(E, np.float32))
        for n in ("attn_q", "attn_k", "attn_v", "attn_output"):
            w.add_tensor(p + n + ".weight", r(E, E))
        w.add_tensor(p + "ffn_norm.weight", np.ones(E, np.float32))
        w.add_tensor(p + "ffn_gate.weight", r(FF, E))
        w.add_tensor(p + "ffn_up.weight", r(FF, E))
        w.add_tensor(p + "ffn_down.weight", r(E, FF))
    w.write_header_to_file(); w.write_kv_data_to_file(); w.write_tensors_to_file(); w.close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(server, model, half_hex, timeout=90):
    """게임(gm_server.py)과 같은 방식으로 띄운다. (/completion 결과 글, 로그)"""
    port = free_port()
    args = [server, "-m", model, "--host", "127.0.0.1", "--port", str(port), "-ngl", "0", "-c", "256",
            "--no-webui", "-lm", "none"]
    logf = open(model + ".log", "wb")   # 파이프로 받으면 로그가 차서 서버가 멈출 수 있다
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=logf, stderr=subprocess.STDOUT)
    try:
        if half_hex:
            proc.stdin.write(half_hex.encode("ascii"))
        proc.stdin.close()
    except OSError:
        pass
    url = f"http://127.0.0.1:{port}"
    text = None
    end = time.time() + timeout
    while time.time() < end and proc.poll() is None:
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                if r.status == 200:
                    req = urllib.request.Request(url + "/completion", json.dumps({"prompt": "Hello", "n_predict": 8, "temperature": 0, "seed": 1}).encode(),
                                                 {"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=60) as r2:
                        text = json.loads(r2.read())["content"]
                    break
        except OSError:
            time.sleep(0.5)
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    logf.close()
    with open(model + ".log", "rb") as f:
        out = f.read().decode(errors="replace")
    return text, out


def run(src, server, keyfile, work):
    os.makedirs(work, exist_ok=True)
    k = json.load(open(keyfile))
    a, b = bytes.fromhex(k["bin_half"]), bytes.fromhex(k["game_half"])
    key = bytes(x ^ y for x, y in zip(a, b))
    plain = os.path.join(work, "tiny.gguf")
    enc = os.path.join(work, "tiny.gguf.enc")
    tiny_model(src, plain)
    data = open(plain, "rb").read()
    with open(enc, "wb") as f:
        f.write(model_crypt.cipher(key, len(data)).update(data))
    assert open(enc, "rb").read(4) != b"GGUF", "암호화가 안 됐다"

    cases = [("암호화 + 맞는 키", enc, b.hex(), True),
             ("암호화 + 틀린 키", enc, secrets.token_bytes(32).hex(), False),
             ("암호화 + 키 없음", enc, "", False),
             ("평문 gguf", plain, "", True)]
    ok = True
    texts = {}
    for name, model, half, expect in cases:
        text, log = serve(server, model, half)
        texts[name] = text
        got = text is not None
        mark = "OK " if got == expect else "FAIL"
        ok &= got == expect
        print(f"[{mark}] {name}: {'생성 ' + repr(text[:40]) if got else '로드 안 됨'}")
        if got != expect:
            print(log[-3000:])
    same = texts["암호화 + 맞는 키"] is not None and texts["암호화 + 맞는 키"] == texts["평문 gguf"]
    ok &= same
    print(f"[{'OK ' if same else 'FAIL'}] 암호화 모델과 평문 모델의 생성 결과가 같다")
    print("모두 통과" if ok else "실패가 있다")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("genkey"); g.add_argument("--src", required=True); g.add_argument("--out", default="testkey.json")
    r = sub.add_parser("run"); r.add_argument("--src", required=True); r.add_argument("--server", required=True)
    r.add_argument("--key", default="testkey.json"); r.add_argument("--work", default="smoke_work")
    a = ap.parse_args()
    if a.cmd == "genkey":
        genkey(a.src, a.out)
        return 0
    return run(a.src, a.server, a.key, a.work)


if __name__ == "__main__":
    sys.exit(main())
