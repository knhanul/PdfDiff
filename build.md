# 빌드 가이드 (build.md)

> **최종 빌드 버전: v2.3.0** 2026.11.03 — PDF 입력폼 관리 기능 추가 포함 리뉴얼

PyInstaller를 사용해 타겟별(`posid` / `post` / `nuni`) Windows 실행 파일을 빌드하는 방법을 설명합니다.

## 사전 준비

### 1. 가상환경 생성 및 활성화

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> 프롬프트가 `(.venv)`로 표시되어 있는지 반드시 확인하세요. 활성화되지 않은 상태에서 패키지를 설치하면 전역 Python에 설치되어 빌드 시 `ModuleNotFoundError`가 발생합니다.

### 2. 의존성 설치

```powershell
pip install -r requirements.txt
pip install pyinstaller
```

### 3. 설치 확인

```powershell
python -c "import PyQt6; print(PyQt6.__file__)"
```

경로가 `.venv\Lib\site-packages\PyQt6\...`로 출력되면 정상입니다.

## 빌드 실행

### 기본 빌드

```powershell
python build.py --target posid --version 2.3.0 --release-date 2026-11-03
```

### 인자

| 인자 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `--target` | O | - | `posid` / `post` / `nuni` 중 하나 |
| `--version` | X | `1.2.0` | 앱 버전 (정보 팝업에 표시) |
| `--release-date` | X | 오늘 날짜 | 제작일자, `YYYY-MM-DD` 형식 (정보 팝업에 표시) |
| `--onefile` | X | `false` | 단일 실행 파일(`.exe`)로 빌드. 생략 시 디렉터리 모드 |

### 타겟별 예시

```powershell
# posid 타겟
python build.py --target posid --version 2.0.1 --release-date 2026-09-23

# post 타겟
python build.py --target post --version 1.0.0 --release-date 2026-09-23

# nuni 타겟
python build.py --target nuni --version 1.0.0 --release-date 2026-09-23
```

## 빌드 모드

`build.py`는 두 가지 빌드 모드를 지원합니다.

### 디렉터리 모드 (기본)

```powershell
python build.py --target posid --version 2.0.1 --release-date 2026-09-23
```

- `dist/PDFCompare/` 폴더 전체 배포
- 실행 파일과 종속 파일이 분리되어 있어 **시작 속도가 빠름**
- 업데이트 시 일부 파일만 교체 가능

### 원파일 모드 (`--onefile`)

```powershell
python build.py --target posid --version 2.0.1 --release-date 2026-09-23 --onefile
```

- `dist/PDFCompare.exe` 단일 파일 배포
- 모든 종속성이 하나의 exe에 압축되어 **배포가 간편** (단일 파일 복사만으로 실행)
- **시작 속도가 상대적으로 느림** (실행 시 임시 폴더에 압축 해제)
- 실행 파일 크기가 큼 (모든 리소스 포함)

> **선택 가이드**: 배포 편의성이 중요하면 원파일 모드, 실행 성능이 중요하면 디렉터리 모드를 사용하세요.

## 빌드 과정

`build.py`가 수행하는 작업:

1. **버전 파일 생성** — `app/common/build_version.txt`에 `APP_VERSION`, `PDF_COMPARE_RELEASE_DATE` 기록
2. **환경변수 설정** — `BUILD_TARGET`, `APP_VERSION`, `PDF_COMPARE_RELEASE_DATE`
3. **PyInstaller 실행** — `main.py`를 엔트리포인트로 `PDFCompare.exe` 생성
   - `--windowed` (콘솔 창 없음)
   - 타겟 아이콘 적용 (`assets/<target>/<target>_icon.ico`)
   - `--add-data`로 `assets/`, `assets/<target>/`, `app/common/build_version.txt` 번들링
   - `configs.*`, `app.tools.*` 모듈을 `--hidden-import`로 명시

## 결과물

빌드가 완료되면 다음 파일이 생성됩니다:

### 디렉터리 모드 (기본)

| 경로 | 설명 |
| --- | --- |
| `dist/PDFCompare/PDFCompare.exe` | 실행 파일 |
| `dist/PDFCompare/` | 종속 파일들 (DLL, 데이터 등) |
| `build/` | 중간 빌드 산출물 (삭제 가능) |
| `PDFCompare.spec` | PyInstaller 스펙 파일 (자동 생성) |

`dist/PDFCompare/` 폴더 전체를 배포하면 됩니다.

### 원파일 모드 (`--onefile`)

| 경로 | 설명 |
| --- | --- |
| `dist/PDFCompare.exe` | 단일 실행 파일 (모든 종속성 포함) |
| `build/` | 중간 빌드 산출물 (삭제 가능) |
| `PDFCompare.spec` | PyInstaller 스펙 파일 (자동 생성) |

`dist/PDFCompare.exe` 파일 하나만 배포하면 됩니다.

## 빌드 시 주의사항

### PyQt6 번들링 확인

빌드 로그에 다음 라인이 나타나야 PyQt6가 정상 번들링된 것입니다:

```
INFO: Processing standard module hook 'hook-PyQt6.py' ...
```

이 라인이 없다면 venv에 PyQt6가 설치되지 않은 것입니다. 가상환경을 활성화한 후 `pip install -r requirements.txt`를 다시 실행하세요.

### PermissionError 발생 시

```
PermissionError: [WinError 5] 액세스가 거부되었습니다: 'C:\Pjt\DeskUtil\dist\PDFCompare'
```

이전 버전의 실행 파일이 실행 중이어서 `dist/` 디렉터리를 삭제하지 못한 경우입니다. 실행 중인 앱을 모두 종료한 후 다시 빌드하세요.

### jinja2 경고 (무시 가능)

```
WARNING: Hidden import "jinja2" not found!
```

pandas의 선택적 의존성 경고로, 앱 동작에 영향을 주지 않으므로 무시해도 됩니다.

## 개발 모드 실행

빌드 없이 개발 중에는 다음 명령으로 실행할 수 있습니다:

```powershell
# 기본 타겟 (posid)
python main.py

# 특정 타겟 지정
$env:BUILD_TARGET = "post"; python main.py
$env:BUILD_TARGET = "nuni"; python main.py
```

개발 모드에서는 `build_version.txt`가 없으면 기본값(`1.2.0`, `2025-12-31`)이 사용됩니다. 빌드 시 설정한 버전을 개발 모드에서도 확인하려면 `build.py`를 한 번 실행해 `build_version.txt`를 생성해두면 됩니다.
