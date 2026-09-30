"""동적 서사 실행기(llama-server) 관리와 추가 데이터(모델) 다운로드.

- 모델은 게임에 넣지 않는다. 사용자 데이터 폴더(%LOCALAPPDATA%/PROTOCOL_STIGMA/models)에 받아 둔다.
  받을 곳과 검증값은 gm_models.json (stigma-gm/tools/prepare_model_release.py가 만든 manifest).
- 실행기는 게임에 동봉한다: exe 안의 runtime/llama/ (개발 중에는 개발/runtime/llama/, install_llama_runtime.py로 복사).
- 게임 시작 때 백그라운드로 서버를 띄우고 예열 요청을 한 번 보낸다 (Vulkan 첫 실행은 셰이더 컴파일로 느리다).
  GPU로 못 띄우면 CPU로 다시 띄운다. 게임이 끝나면 같이 끈다.
- 배포 모델은 보호되어 있어 동봉한 전용 서버로만 연다 (gm_key.py는 공개 저장소에 없다).
  서버에는 실행마다 새 접근 키를 걸어, 다른 프로그램이 떠 있는 서버를 가져다 쓰지 못하게 한다.
표준 라이브러리만 쓴다.
"""
import atexit
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request

try:
    import gm_key  # 생성 파일 (gitignore). 없으면 배포 모델은 못 띄운다 (개발용 모델은 된다)
except ImportError:
    gm_key = None

APP = "PROTOCOL_STIGMA"
HEALTH_TIMEOUT = 180  # 첫 실행은 셰이더 컴파일로 오래 걸릴 수 있다
_HERE = os.path.dirname(os.path.abspath(__file__))


def _resource(*parts):
    base = getattr(sys, "_MEIPASS", _HERE)
    return os.path.join(base, *parts)


def data_dir():
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(root, APP)
    os.makedirs(os.path.join(path, "models"), exist_ok=True)
    return path


def manifest():
    with open(_resource("gm_models.json"), encoding="utf-8") as f:
        return json.load(f)


def model_path(mode):
    info = manifest()["models"].get(mode)
    return os.path.join(data_dir(), "models", info["file"]) if info else None


def model_installed(mode):
    info = manifest()["models"].get(mode)
    path = model_path(mode)
    return bool(info and path and os.path.exists(path) and os.path.getsize(path) == info["size"])


def server_binary():
    name = "llama-server.exe" if os.name == "nt" else "llama-server"
    path = _resource("runtime", "llama", name)
    return path if os.path.exists(path) else None


# ── 서버 ────────────────────────────────────────────────────────────────

class _Server:
    def __init__(self):
        self.proc = None
        self.mode = None
        self.url = None
        self.api_key = None
        self.state = "stopped"   # stopped / starting / ready / failed / missing
        self._lock = threading.Lock()

    def start(self, mode):
        """mode의 모델로 서버를 백그라운드에서 띄운다. 이미 같은 모드로 떠 있으면 그대로."""
        with self._lock:
            alive = self.proc is not None and self.proc.poll() is None
            if self.mode == mode and (self.state == "starting" or (self.state == "ready" and alive)):
                return
            self._stop_locked()
            self.mode = mode
            if mode == "off":
                return
            if not model_installed(mode) or not server_binary():
                self.state = "missing"
                return
            self.state = "starting"
        threading.Thread(target=self._launch, args=(mode,), daemon=True).start()

    def _launch(self, mode):
        log = open(os.path.join(data_dir(), "server.log"), "ab")
        for ngl in ("99", "0"):  # GPU에 전부 올리고, 안 되면 CPU로
            port = _free_port()
            # -lm none: 모델 파일을 메모리에 비춰 두지 않는다. GPU에 다 올린 뒤 RAM 점유가 5.0GB -> 0.45GB (8B 실측)
            args = [server_binary(), "-m", model_path(mode), "--host", "127.0.0.1", "--port", str(port),
                    "-ngl", ngl, "-c", "4096", "--no-webui", "-lm", "none"]
            flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: 콘솔 창을 띄우지 않는다
            api_key = secrets.token_urlsafe(32)
            env = dict(os.environ, LLAMA_API_KEY=api_key)  # 명령줄은 누구나 보이니 환경변수로
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log, stderr=log, env=env, creationflags=flags)
            _tie_to_game(proc)
            try:
                if gm_key is not None:
                    proc.stdin.write(gm_key.half_hex().encode("ascii"))
                proc.stdin.close()
            except OSError:
                pass
            url = f"http://127.0.0.1:{port}"
            if _wait_health(url, proc):
                try:  # 예열: 셰이더 컴파일과 첫 프롬프트 처리를 미리 끝낸다
                    _post(url + "/completion", {"prompt": "시작", "n_predict": 1}, timeout=HEALTH_TIMEOUT, api_key=api_key)
                except OSError:
                    pass
                with self._lock:
                    if self.mode != mode:  # 기다리는 동안 모드가 바뀌었다
                        proc.terminate()
                        return
                    self.proc, self.url, self.api_key, self.state = proc, url, api_key, "ready"
                return
            proc.kill()
        with self._lock:
            if self.mode == mode:
                self.state = "failed"

    def _stop_locked(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc, self.url, self.api_key, self.state = None, None, None, "stopped"

    def stop(self):
        with self._lock:
            self._stop_locked()
            self.mode = None


_job = None


def _tie_to_game(proc):
    """서버를 게임 프로세스에 묶는다 (Windows Job Object, 핸들이 닫히면 같이 종료).
    게임을 창 닫기·강제 종료로 끝내도 서버가 GPU를 붙잡고 남지 않게 (실측: 남아 있었다)."""
    global _job
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
        if _job is None:
            k32.CreateJobObjectW.restype = wintypes.HANDLE
            _job = k32.CreateJobObjectW(None, None)
            info = EXT()
            info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(_job, 9, ctypes.byref(info), ctypes.sizeof(info))  # ExtendedLimitInformation
        k32.AssignProcessToJobObject(_job, wintypes.HANDLE(int(proc._handle)))
    except Exception:  # noqa: BLE001 - 묶지 못해도 atexit 종료는 그대로 있다
        pass


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(url, body, timeout=30, api_key=None):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _wait_health(url, proc):
    end = time.time() + HEALTH_TIMEOUT
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + "/health", timeout=2) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    return False


server = _Server()
atexit.register(server.stop)


# ── 다운로드 ──────────────────────────────────────────────────────────────

class Download:
    """모드의 모델을 조각 단위로 받는다. 끊겨도 이어받고, 조각과 전체를 sha256으로 검증한다.
    run()은 백그라운드 스레드에서 돌리고, 화면은 done/total/speed/phase/error를 읽는다."""

    def __init__(self, mode):
        self.info = manifest()["models"][mode]
        self.mode = mode
        self.total = self.info["size"]
        self.done = 0
        self.speed = 0.0
        self.phase = "download"   # download / verify / done / error / cancelled
        self.error = ""
        self.cancel = False
        self.dir = os.path.join(data_dir(), "models")

    def free_space_ok(self):
        import shutil
        return shutil.disk_usage(self.dir).free > self.total * 2 + (200 << 20)  # 조각 + 합친 파일

    def run(self):
        try:
            parts = []
            for i, part in enumerate(self.info["parts"]):
                path = os.path.join(self.dir, f"{self.info['file']}.part{i + 1}")
                self._fetch(part, path, sum(p["size"] for p in self.info["parts"][:i]))
                if self.cancel:
                    self.phase = "cancelled"
                    return
                parts.append(path)
            self.phase = "verify"
            final = os.path.join(self.dir, self.info["file"])
            tmp = final + ".tmp"
            whole = hashlib.sha256()
            with open(tmp, "wb") as out:
                for path in parts:
                    with open(path, "rb") as f:
                        while True:
                            buf = f.read(8 << 20)
                            if not buf:
                                break
                            out.write(buf)
                            whole.update(buf)
            if whole.hexdigest() != self.info["sha256"]:
                os.remove(tmp)
                raise ValueError("checksum")
            os.replace(tmp, final)
            for path in parts:
                os.remove(path)
            self.phase = "done"
        except Exception as e:  # noqa: BLE001 - 화면에 보여 주고 다시 시도하게 한다
            self.phase, self.error = "error", str(e)

    def _fetch(self, part, path, offset):
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if have == part["size"] and _sha256(path) == part["sha256"]:
            self.done = offset + have
            return
        if have > part["size"]:
            os.remove(path)
            have = 0
        req = urllib.request.Request(part["url"], headers={"User-Agent": APP, "Range": f"bytes={have}-"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if have and r.status != 206:  # 서버가 이어받기를 지원하지 않으면 처음부터
                have = 0
            mode = "ab" if have else "wb"
            t0, got0 = time.time(), have
            with open(path, mode) as f:
                while not self.cancel:
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    f.write(buf)
                    have += len(buf)
                    self.done = offset + have
                    dt = time.time() - t0
                    if dt > 0.5:
                        self.speed = (have - got0) / dt
        if not self.cancel and (have != part["size"] or _sha256(path) != part["sha256"]):
            os.remove(path)
            raise ValueError("part checksum")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(8 << 20)
            if not buf:
                return h.hexdigest()
            h.update(buf)
