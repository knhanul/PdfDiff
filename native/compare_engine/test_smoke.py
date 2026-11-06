"""
간단한 스모크 테스트.
빌드 후 이 스크립트를 실행해 모듈이 로드되는지 확인하세요.
"""
import sys
from pathlib import Path

# 빌드 결과 경로를 필요에 따라 조정
build_dir = Path(__file__).parent / "build" / "Release"
if build_dir.exists():
    sys.path.insert(0, str(build_dir))

try:
    import compare_engine as ce
    print("compare_engine loaded:", ce)

    opts = ce.ComparisonOptions()
    print("Options created:", opts)

    # 더미 데이터
    g1 = ce.Glyph()
    g1.ch = "a"
    g1.page = 0
    g1.y = 10.0

    g2 = ce.Glyph()
    g2.ch = "b"
    g2.page = 0
    g2.y = 10.0

    norm = ce.normalize([g1, g2], opts)
    print("Normalized count:", len(norm))

    ops = ce.diff(norm, norm)
    print("Diff ops:", len(ops))
    print("OK")
except Exception as e:
    print("Error:", e)
    print("빌드가 완료되었는지, pyd/so 경로가 맞는지 확인하세요.")
