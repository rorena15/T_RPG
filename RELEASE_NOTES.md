# PROTOCOL: STIGMA v1.9.0 — 1막: 낙인

> *"시스템에 의해 버려진 코드가 데드존을 살아남는다."*

---

## 주요 변경 사항

### Mac 지원 추가

이제 macOS에서도 PROTOCOL: STIGMA를 플레이할 수 있습니다.

- **`PROTOCOL_STIGMA_mac.tar.gz`** 파일을 릴리즈에서 다운로드
- 압축 해제 후 터미널에서 실행:

  ```bash
  tar -xzf PROTOCOL_STIGMA_mac.tar.gz
  chmod +x PROTOCOL_STIGMA
  ./PROTOCOL_STIGMA
  ```

- 한국어 폰트 자동 감지 (`Apple SD Gothic Neo` → `AppleGothic` → `Noto Sans CJK KR` 순)
- 자동 업데이트는 Mac에서 지원되지 않습니다. 새 버전은 릴리즈 페이지에서 직접 다운로드 해주세요.

---

### GUI 터미널 개선

- **D2Coding 폰트 번들 내장** — 별도 설치 없이 한글이 올바르게 렌더링됩니다
- Windows/Mac 양 플랫폼에서 동일한 폰트 출력 보장
- ANSI 색상 렌더링 정확도 개선

---

### 빌드 파이프라인 고도화

GitHub Actions 릴리즈 워크플로우에 다음 옵션이 추가되었습니다:

| 옵션 | 설명 |
|------|------|
| `latest` | 새 태그로 최신 릴리즈 생성 |
| `rerelease` | 기존 태그 파일만 교체 (재배포) |
| `draft` | 초안으로 저장 (게시 안 함) |
| `prerelease` | 베타 표시 릴리즈 |

---

## 버그 수정

- **경로 버그 수정** — 루트 디렉토리에서 실행 시 `database.json` 누락 오류 해결 (`resource_path()` CWD 의존 제거)
- **테두리 정렬 수정** — 일부 UI 박스 테두리가 어긋나던 문제 수정
- **특수 문자 버그 수정** — 일부 환경에서 한국어 특수 문자 출력 오류 해결
- **서식 깨짐 수정** — ANSI 코드 처리 중 발생하던 레이아웃 붕괴 수정

---

## 다운로드

| 플랫폼 | 파일 | 비고 |
|--------|------|------|
| **Windows 64비트** | `PROTOCOL_STIGMA.exe` | 더블클릭으로 바로 실행 |
| **macOS (Apple Silicon / Intel)** | `PROTOCOL_STIGMA_mac.tar.gz` | 터미널 실행 필요 |

> Windows Defender 경고 시 → `추가 정보` → `실행` 선택

---

## 알려진 이슈

- Mac에서 자동 업데이트 미지원 (GitHub 릴리즈 페이지에서 수동 다운로드)
- 소스 실행(`python Main.py`) 환경에서는 pygame 기반 GUI가 비활성화되며 일반 터미널로 동작합니다

---

## 시스템 요구 사항

| 항목 | Windows | macOS |
|------|---------|-------|
| OS | Windows 10/11 64비트 | macOS 12 이상 (Monterey+) |
| 실행 | EXE 더블클릭 | 터미널에서 실행 |
| Python | 불필요 (번들됨) | 불필요 (번들됨) |

---

*1막 '낙인' 데모 빌드 — 플레이 타임 약 1~2시간*  
*엔딩 3종 + 히든 엔딩 1종*
