import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TARGETS = {
    'posid': {
        'app_name': 'nunidesk_posid',
        'asset_dir': 'assets/posid',
        'icon': 'assets/posid/posid_icon.ico',
    },
    'post': {
        'app_name': 'nunidesk_post',
        'asset_dir': 'assets/post',
        'icon': 'assets/post/post_icon.ico',
    },
    'nuni': {
        'app_name': 'nunidesk_nuni',
        'asset_dir': 'assets/nuni',
        'icon': 'assets/nuni/nuni_icon.ico',
    },
}


def build(target_name: str, version: str = None, release_date: str = None, onefile: bool = False):
    project_root = Path(__file__).resolve().parent
    target = TARGETS[target_name]
    env = os.environ.copy()
    env['BUILD_TARGET'] = target_name
    
    # 버전과 생성일자를 파일로 저장 (런타임에서 읽기 위해)
    version_file = project_root / 'app' / 'common' / 'build_version.txt'
    version_content = f"APP_VERSION={version or '1.2.0'}\nPDF_COMPARE_RELEASE_DATE={release_date or datetime.now().strftime('%Y-%m-%d')}\n"
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
        'app.tools.pdf_compare',
        '--hidden-import',
        'app.tools.pdf_header_footer_compare',
        '--hidden-import',
        'app.tools.pdf_modify',
        str(project_root / 'main.py'),
    ]
    # 원파일 모드 (--onefile) 또는 디렉터리 모드 (기본)
    if onefile:
        command[10:10] = ['--onefile']
    icon_path = project_root / target['icon']
    if icon_path.exists():
        command[10:10] = ['--icon', str(icon_path)]
    
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
