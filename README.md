# PdfDiff

PyQt6 기반의 Windows 데스크톱 문서 유틸리티 애플리케이션입니다. PDF 비교 기능을 하나의 통합된 UI에서 제공합니다. 동일한 코드베이스에서 빌드 타겟(`posid`, `post`, `nuni`)에 따라 앱 이름/아이콘/테마 색상을 분리하여 배포할 수 있습니다.

## 주요 기능

| 기능 | 메뉴명 | 설명 |
| --- | --- | --- |
| PDF 지정 영역 비교 | 📄 영역지정비교 | 두 PDF에서 사용자가 지정한 영역(AREA)을 추출해 정규화 후 문자열 단위로 정밀 비교 |
| PDF 전체 비교 | 📄 전체비교 | 페이지 단위 전체 비교. 헤더/푸터 영역을 드래그로 제외 영역으로 설정 가능 |
| PDF 편집 | ✏️ PDF 편집 | 하나의 창에서 분할·병합·페이지 편집. 페이지를 체크해 구간 분할·회전·이동하고, 미리보기는 확대/축소 |
| PDF 생성 | 📝 PDF 생성 | 한글, 오피스, 마크다운, 텍스트, 이미지를 PDF로 변환. 폴더 드롭, 다중 선택, 결과 폴더, 작업 이력 |
| 이미지 추출 | 🖼️ 이미지 추출 | PDF에 포함된 이미지를 찾아 체크한 것만 원래 형식으로 저장 |

### 비교 조건

두 비교 화면의 하단 **비교 조건** 버튼에서 모드를 선택할 수 있습니다.

| 모드 | 동작 |
| --- | --- |
| 본문 비교 (기본값) | 기존 정규화·중복 문자 처리·문자 필터를 그대로 사용합니다. 공백, 줄바꿈, 대소문자 차이는 무시하며 일부 문장부호는 비교합니다. |
| 엄격한 텍스트 비교 | 추출된 공백, 줄바꿈, 대소문자, 특수문자를 모두 보존하여 비교합니다. |
| 사용자 설정 | 공백(탭 포함), 줄바꿈, 대소문자, 특수문자를 각각 비교하거나 무시할 수 있습니다. 특수문자 무시는 유니코드 문장부호·기호 전체에 적용됩니다. |

- 조건은 실행 중인 앱의 두 비교 화면에서 공유됩니다. 앱을 다시 실행하면 본문 비교로 시작합니다.
- 조건을 바꾸면 이전 비교결과와 하이라이트를 지우고 **재비교** 버튼으로 안내합니다. 파일, 선택 영역, 제외 영역, 검색어는 유지됩니다.
- 비교 작업 중에는 조건 변경이 잠깐 비활성화됩니다.
- 엄격/사용자 모드의 결과 목록에서는 공백 `␠`, 탭 `⇥`, 줄바꿈 `↵`, 줄 바꿈 없는 공백 `⍽`를 표시합니다. 이 표시는 결과를 읽기 위한 것이며 비교 데이터와 원본 PDF를 바꾸지 않습니다.
- 줄바꿈은 PDF에서 추출된 줄 경계와 페이지 경계로 표현됩니다. PDF에 문자로 저장되지 않은 시각적 여백이나 빈 줄까지 원본 편집 문서처럼 복원하는 기능은 아닙니다.
- 글꼴·색상·이미지·도장 비교와 OCR은 포함하지 않습니다. 엄격 모드도 PDF에서 추출 가능한 텍스트를 비교합니다.

비교 조건 회귀 테스트:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_comparison_options.py
```

## 프로젝트 구조

```
PdfDiff/
├── main.py                      # 엔트리포인트
├── build.py                     # PyInstaller 빌드 스크립트
├── requirements.txt             # 의존성 목록
├── app/
│   ├── main_window.py           # 메인 윈도우(사이드바 + 도구 컨테이너)
│   ├── common/
│   │   ├── resources.py         # 타겟별 리소스/버전 로딩
│   │   ├── styles.py            # QSS 스타일
│   │   ├── pdf_compare_worker.py# PDF 비교 백그라운드 스레드
│   │   ├── pdf_convert.py       # PDF 생성 변환
│   │   ├── pdf_images.py        # PDF 이미지 추출
│   │   ├── pdf_search_helper.py # PDF 텍스트 검색 헬퍼
│   │   └── loading_dialog.py    # 로딩 다이얼로그
│   └── tools/
│       ├── pdf_compare.py           # PDF 지정 영역 비교
│       ├── pdf_header_footer_compare.py  # PDF 전체 비교
│       ├── pdf_editor.py            # 통합 PDF 편집 (분할/병합/페이지)
│       ├── pdf_create.py            # PDF 생성 (문서/이미지 변환)
│       └── pdf_image_extract.py     # PDF 이미지 추출
├── configs/
│   ├── settings.py              # 타겟 로딩 로직 (환경변수/실행파일명에서 타겟 추출)
│   ├── target_posid.py          # posid 타겟 설정
│   ├── target_post.py           # post 타겟 설정
│   ├── target_nuni.py           # nuni 타겟 설정
│   └── target_qamate.py         # qamate 타겟 설정(빌드 대상 아님)
├── assets/                      # 타겟별 아이콘/로고
│   ├── posid/
│   ├── post/
│   ├── nuni/
│   └── qamate/
└── tests/                       # 단위 테스트
```

## 빌드 타겟

`configs/settings.py`가 실행 환경에 따라 타겟을 자동으로 로딩합니다.

1. 환경변수 `BUILD_TARGET` (빌드 시 `build.py`가 설정)
2. 실행 파일 이름에서 추출 (예: `nunidesk_posid.exe` → `posid`)
3. 기본값: `posid`

| 타겟 | 앱 이름 | 회사명 | 테마색 |
| --- | --- | --- | --- |
| `posid` | Posid 데스크 | 우체국금융개발원 | `#004b93` |
| `post` | nunidesk | 우정정보관리원 | `#6b46c1` |
| `nuni` | nunidesk | Nuni | `#0f766e` |

## 요구사항

- Windows 10/11
- Python 3.12+
- 의존성: `requirements.txt` 참조
  - PyQt6, PyMuPDF
  - 빌드 시 추가: `pyinstaller`

## 개발 환경 설정

```powershell
# 1. 가상환경 생성 및 활성화
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 의존성 설치 (가상환경 활성화 상태에서)
pip install -r requirements.txt
pip install pyinstaller

# 3. 개발 모드 실행 (기본 타겟: posid)
python main.py

# 특정 타겟으로 개발 실행
$env:BUILD_TARGET = "post"; python main.py
$env:BUILD_TARGET = "nuni"; python main.py
```

> **주의**: `pip install -r requirements.txt` 실행 시 프롬프트가 `(.venv)`로 표시되어 있는지 반드시 확인하세요. 가상환경이 활성화되지 않은 상태에서 설치하면 전역 Python에 패키지가 설치되어 빌드 시 `ModuleNotFoundError`가 발생합니다.

## 빌드 (PyInstaller)

`build.py`를 사용해 타겟별 실행 파일을 생성합니다.

```powershell
# 가상환경 활성화 상태에서 실행
python build.py --target posid --version 2.0.1 --release-date 2026-08-20
```

### 인자
| 인자 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `--target` | O | - | `posid` / `post` / `nuni` 중 하나 |
| `--version` | X | `1.2.0` | 앱 버전 |
| `--release-date` | X | 오늘 날짜 | 출시일자 (YYYY-MM-DD) |

### 빌드 과정
1. `app/common/build_version.txt`에 버전/출시일 기록
2. 환경변수 `BUILD_TARGET`, `APP_VERSION`, `PDF_COMPARE_RELEASE_DATE` 설정
3. PyInstaller로 `main.py`를 엔트리포인트로 `nunidesk_<target>.exe` 생성
   - `--windowed` (콘솔 창 없음)
   - 타겟 아이콘 적용 (`assets/<target>/<target>_icon.ico`)
   - `assets/`, `assets/<target>/`, `app/common/build_version.txt` 번들링
   - `configs.*`, `app.tools.*` 모듈을 hidden-import로 명시

### 결과물
- `dist/nunidesk_<target>/nunidesk_<target>.exe` — 실행 파일
- `build/` — 중간 산출물
- `nunidesk_<target>.spec` — PyInstaller 스펙 파일 (자동 생성)

### 빌드 시 주의사항
- 빌드 로그에 `Processing standard module hook 'hook-PyQt6.py' ...` 라인이 나타나야 PyQt6가 정상 번들링된 것입니다. 해당 라인이 없다면 venv에 PyQt6가 설치되지 않은 것입니다.
- `dist/<app>` 디렉터리 삭제 시 `PermissionError: [WinError 5]`가 발생하면 이전 빌드의 실행 파일이 실행 중인 것입니다. 앱을 종료한 후 다시 빌드하세요.

## 라이선스 메뉴 / 내부 보고서

타겟 설정의 `ENABLE_LICENSE_MENU`, `ENABLE_INTERNAL_REPORT` 플래그로 메뉴 노출을 타겟별로 제어합니다 (`configs/target_*.py` 참조).

## 문제 해결

### `ModuleNotFoundError: No module named 'PyQt6'` (빌드된 exe 실행 시)
venv에 PyQt6가 설치되지 않은 상태에서 빌드했을 때 발생합니다. 가상환경을 활성화한 후 `pip install -r requirements.txt`를 다시 실행하세요.

### `PermissionError: [WinError 5]` (빌드 중)
이전 버전의 실행 파일이 실행 중이어서 `dist/` 디렉터리를 삭제하지 못한 경우입니다. 실행 중인 앱을 모두 종료하세요.
