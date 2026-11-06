# PdfDiff Comparison Engine (C++)

PyQt6 UI는 그대로 두고, **비교 엔진만 C++로 분리**한 모듈입니다.  
VSCode에서 열고 빌드할 수 있습니다.

## 요구 사항
- CMake ≥ 3.18
- C++17 컴파일러 (MSVC / Clang / GCC)
- Python 3.10+ (개발용)
- pybind11 (CMake가 자동으로 받아옴)

## VSCode에서 빌드

1. 이 폴더를 VSCode로 엽니다.
2. CMake Tools 확장 설치 (권장)
3. 터미널에서:

```powershell
mkdir build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

빌드가 성공하면 `build/Release/compare_engine.pyd` (또는 `compare_engine.so`)가 생성됩니다.

## Python에서 사용 예시

```python
import compare_engine as ce

opts = ce.ComparisonOptions()
opts.mode = ce.Mode.Body   # 또는 Strict / Custom

# raw_glyphs: PyMuPDF에서 추출한 문자 리스트를 Glyph 형태로 변환해 전달
normalized = ce.normalize(raw_glyphs, opts, page_aware=True)
ops = ce.diff(normalized_a, normalized_b)

for op in ops:
    print(op.type, op.a_start, op.a_end, op.b_start, op.b_end)
```

## 다음 단계 (확장 포인트)
- `src/normalizer.cpp` : 원본 Python의 `_reconstruct_lines`, `_deduplicate_glyphs` 로직을 더 정밀하게 이식
- Myers diff 또는 Google diff-match-patch 스타일로 `Comparator` 교체
- MuPDF C API를 직접 연동해 텍스트 추출까지 엔진 안으로 이동
- 벤치마크 추가

## 기존 PdfDiff와 연동
1. 빌드된 `compare_engine.pyd`를 PdfDiff 프로젝트의 `app/` 또는 site-packages에 둡니다.
2. `pdf_compare_worker.py` 등에서 Python 정규화/비교 호출을 `compare_engine` 호출로 교체합니다.
