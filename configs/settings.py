import importlib
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = 'posid'
TARGET_MODULES = {
    'posid': 'configs.target_posid',
    'post': 'configs.target_post',
    'nuni': 'configs.target_nuni',
}


def _detect_target_from_version_file():
    """번들된 build_version.txt의 BUILD_TARGET에서 타겟 추출"""
    try:
        if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
            version_file = Path(sys._MEIPASS) / 'app' / 'common' / 'build_version.txt'
        else:
            version_file = BASE_DIR / 'app' / 'common' / 'build_version.txt'
        if version_file.exists():
            for line in version_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line.startswith('BUILD_TARGET='):
                    return line.split('=', 1)[1].strip().lower()
    except Exception:
        pass
    return None


def _detect_target_from_executable():
    """실행 파일 이름에서 타겟 추출"""
    try:
        # PyInstaller 빌드된 환경인지 확인
        if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
            exe_path = sys.executable
            exe_name = Path(exe_path).stem.lower()
            
            # 실행 파일 이름에서 타겟 추출 (예: nunidesk_post.exe -> post)
            for target in TARGET_MODULES.keys():
                if f'_{target}' in exe_name or exe_name.endswith(target):
                    return target
    except:
        pass
    return None


def _load_target():
    # 환경변수 우선, 없으면 빌드 버전 파일의 BUILD_TARGET,
    # 없으면 실행 파일 이름에서 추출, 없으면 기본값
    build_target = os.environ.get('BUILD_TARGET')
    if not build_target:
        build_target = _detect_target_from_version_file()
    if not build_target:
        build_target = _detect_target_from_executable()
    if not build_target:
        build_target = DEFAULT_TARGET
    
    build_target = build_target.strip().lower()
    module_name = TARGET_MODULES.get(build_target, TARGET_MODULES[DEFAULT_TARGET])
    module = importlib.import_module(module_name)
    target = dict(module.TARGET)
    target['BUILD_TARGET'] = build_target if build_target in TARGET_MODULES else DEFAULT_TARGET
    target['BASE_DIR'] = BASE_DIR
    target['ASSET_DIR_PATH'] = BASE_DIR / target['ASSET_DIR']
    target['LOGO_FILE_NAME'] = f"{target['BUILD_TARGET']}_logo.png"
    if 'ICON_FILE_NAME' not in target:
        target['ICON_FILE_NAME'] = 'icon.ico'
    target['LOGO_PATH'] = target['ASSET_DIR_PATH'] / target['LOGO_FILE_NAME']
    target['ICON_PATH'] = target['ASSET_DIR_PATH'] / target['ICON_FILE_NAME']
    return target


SETTINGS = _load_target()
