import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TARGETS = {
    'posid': {
        'app_name': 'PDFCompare',
        'asset_dir': 'assets/posid',
        'icon': 'assets/posid/posid_icon.ico',
    },
    'post': {
        'app_name': 'PDFCompare',
        'asset_dir': 'assets/post',
        'icon': 'assets/post/post_icon.ico',
    },
    'nuni': {
        'app_name': 'PDFCompare',
        'asset_dir': 'assets/nuni',
        'icon': 'assets/nuni/nuni_icon.ico',
    },
}


def _prepare_splash_image(project_root: Path, target_name: str):
    """스플래시용 이미지 경로를 반환한다.

    PyInstaller 스플래시는 Pillow 없이 760x480까지만 허용하므로,
    초과 시 PyMuPDF로 1/2씩 축소한 사본을 build/ 아래에 만든다.
    """
    splash_src = project_root / 'assets' / f'{target_name}_signature.png'
    if not splash_src.exists():
        return None
    try:
        import pymupdf
        pix = pymupdf.Pixmap(str(splash_src))
        if pix.width <= 760 and pix.height <= 480:
            return splash_src
        while pix.width > 760 or pix.height > 480:
            pix.shrink(1)
        build_dir = project_root / 'build'
        build_dir.mkdir(exist_ok=True)
        resized = build_dir / f'{target_name}_splash.png'
        pix.save(str(resized))
        return resized
    except Exception:
        # 변환 실패 시 원본을 그대로 사용 (PyInstaller가 크기 검사에서 안내)
        return splash_src


def build(target_name: str, version: str = None, release_date: str = None, onefile: bool = False):
    project_root = Path(__file__).resolve().parent
    target = TARGETS[target_name]
    env = os.environ.copy()
    env['BUILD_TARGET'] = target_name
    
    # 버전과 생성일자를 파일로 저장 (런타임에서 읽기 위해)
    version_file = project_root / 'app' / 'common' / 'build_version.txt'
    version_content = (
        f"APP_VERSION={version or '1.2.0'}\n"
        f"PDF_COMPARE_RELEASE_DATE={release_date or datetime.now().strftime('%Y-%m-%d')}\n"
        f"BUILD_TARGET={target_name}\n"
    )
    version_file.write_text(version_content, encoding='utf-8')
    
    # 환경변수도 설정 (개발 환경용)
    if version:
        env['APP_VERSION'] = version
    if release_date:
        env['PDF_COMPARE_RELEASE_DATE'] = release_date
    
    separator = ';' if os.name == 'nt' else ':'
    command = [
        sys.executable,
        '-m',
        'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        # pymupdf.layout는 앱에서 사용하지 않는 ONNX 레이아웃 분석기로,
        # 리소스 파일이 번들에 없으면 import pymupdf 자체가 실패하므로 제외
        '--exclude-module',
        'pymupdf.layout',
        '--name',
        target['app_name'],
        '--hidden-import',
        'configs.settings',
        '--hidden-import',
        'configs.target_posid',
        '--hidden-import',
        'configs.target_post',
        '--hidden-import',
        'configs.target_nuni',
        '--hidden-import',
        'win32com',
        '--hidden-import',
        'win32com.client',
        str(project_root / 'main.py'),
    ]
    # 도구 모듈은 런타임에 lazy import되므로 app/tools 아래 모듈을 모두 명시
    for tool_file in sorted((project_root / 'app' / 'tools').glob('*.py')):
        if tool_file.stem != '__init__':
            command[10:10] = ['--hidden-import', f'app.tools.{tool_file.stem}']
    # 원파일 모드 (--onefile) 또는 디렉터리 모드 (기본)
    if onefile:
        command[10:10] = ['--onefile']
    icon_path = project_root / target['icon']
    if icon_path.exists():
        command[10:10] = ['--icon', str(icon_path)]

    # 원파일 압축 해제/로딩 동안 표시할 스플래시 이미지 (assets/<target>_signature.png)
    splash_path = _prepare_splash_image(project_root, target_name)
    if splash_path:
        command[10:10] = ['--splash', str(splash_path)]
    
    # 타겟별 에셋 디렉토리 추가
    asset_dir_path = project_root / target['asset_dir']
    if asset_dir_path.exists():
        add_data_arg = f"{asset_dir_path}{separator}{target['asset_dir']}"
        command[10:10] = ['--add-data', add_data_arg]
    
    # 공통 assets 폴더 추가 (AIResearch.png 포함)
    assets_dir = project_root / 'assets'
    if assets_dir.exists():
        add_data_arg = f"{assets_dir}{separator}assets"
        command[10:10] = ['--add-data', add_data_arg]
    
    # 빌드 버전 파일 추가
    if version_file.exists():
        add_data_arg = f"{version_file}{separator}app/common"
        command[10:10] = ['--add-data', add_data_arg]
    
    subprocess.run(command, cwd=project_root, env=env, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=sorted(TARGETS.keys()), required=True)
    parser.add_argument('--version', default='1.2.0', help='버전 (기본값: 1.2.0)')
    parser.add_argument('--release-date', default=datetime.now().strftime('%Y-%m-%d'), 
                       help='생성일자 (기본값: 오늘 날짜)')
    parser.add_argument('--onefile', action='store_true',
                       help='단일 실행 파일로 빌드 (기본: 디렉터리 모드)')
    args = parser.parse_args()
    build(args.target, args.version, args.release_date, args.onefile)
