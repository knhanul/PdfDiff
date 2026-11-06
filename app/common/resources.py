import os
import sys
from configs.settings import SETTINGS

# 빌드 버전 파일에서 읽기 (빌드된 실행 파일용)
def _read_build_version():
    try:
        # PyInstaller 환경인지 확인
        if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
            version_file = os.path.join(sys._MEIPASS, 'app', 'common', 'build_version.txt')
        else:
            version_file = os.path.join(os.path.dirname(__file__), 'build_version.txt')
        
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('APP_VERSION='):
                        return line.split('=', 1)[1]
    except:
        pass
    return None

def _read_build_release_date():
    try:
        # PyInstaller 환경인지 확인
        if hasattr(sys, 'frozen') and hasattr(sys, '_MEIPASS'):
            version_file = os.path.join(sys._MEIPASS, 'app', 'common', 'build_version.txt')
        else:
            version_file = os.path.join(os.path.dirname(__file__), 'build_version.txt')
        
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('PDF_COMPARE_RELEASE_DATE='):
                        return line.split('=', 1)[1]
    except:
        pass
    return None

VERSION = _read_build_version() or os.environ.get('APP_VERSION', '1.2.0')
RELEASE_DATE = _read_build_release_date() or os.environ.get('PDF_COMPARE_RELEASE_DATE', '2025-12-31')
DEVELOPER = SETTINGS['COMPANY_NAME']
APP_NAME = SETTINGS['APP_NAME']
COMPANY_NAME = SETTINGS['COMPANY_NAME']
THEME_COLOR_PRIMARY = SETTINGS['THEME_COLOR_PRIMARY']


def _runtime_base_path():
    try:
        return sys._MEIPASS
    except Exception:
        return str(SETTINGS['BASE_DIR'])


def _candidate_paths(relative_path):
    runtime_base = _runtime_base_path()
    asset_dir = SETTINGS['ASSET_DIR']
    build_target = SETTINGS['BUILD_TARGET']
    legacy_aliases = {
        'posid_logo.png': [f'{asset_dir}/{build_target}_logo.png', f'{asset_dir}/logo.png', 'posid_logo.png'],
        'posid_logo.ico': [f'{asset_dir}/icon.ico', f'{asset_dir}/{build_target}.ico', 'posid_logo.ico'],
        'icon.ico': [f'{asset_dir}/icon.ico', 'posid_logo.ico'],
    }
    raw_candidates = legacy_aliases.get(relative_path, [relative_path, f'{asset_dir}/{relative_path}'])
    return [os.path.join(runtime_base, candidate) for candidate in raw_candidates]


def get_resource_path(relative_path):
    for candidate in _candidate_paths(relative_path):
        if os.path.exists(candidate):
            return candidate
    return _candidate_paths(relative_path)[0]


def get_logo_path():
    build_target = SETTINGS.get('BUILD_TARGET', 'posid')
    logo_key = f'{build_target}_logo.png'
    for candidate in _candidate_paths(logo_key):
        if os.path.exists(candidate):
            return candidate
    return None


def get_icon_path():
    for candidate in _candidate_paths('icon.ico'):
        if os.path.exists(candidate):
            return candidate
    return None


def _find_common_asset(name):
    """공통 assets 폴더와 타겟 에셋 폴더에서 파일을 찾는다."""
    if not name:
        return None
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    runtime_base = _runtime_base_path()
    base_dir = str(SETTINGS['BASE_DIR'])
    asset_dir = SETTINGS['ASSET_DIR']
    candidates = [
        os.path.join(runtime_base, 'assets', name),
        os.path.join(base_dir, 'assets', name),
        os.path.join(runtime_base, asset_dir, name),
        os.path.join(base_dir, asset_dir, name),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def get_about_image_path():
    """정보 팝업 대표 이미지 경로. SETTINGS['ABOUT_IMAGE']로 파일명 변경 가능."""
    return _find_common_asset(str(SETTINGS.get('ABOUT_IMAGE') or 'AIKickOff.png'))


def get_about_icon_path():
    """헤더 정보 버튼 아이콘 경로. SETTINGS['ABOUT_ICON']로 파일명 변경 가능."""
    return _find_common_asset(str(SETTINGS.get('ABOUT_ICON') or 'about_blue.svg'))


def get_timer_gif_path():
    """시간이 걸리는 작업 표시용 GIF 경로."""
    name = "nuni_icon_orange_spin.gif"
    candidates = [
        os.path.join(_runtime_base_path(), "assets", name),
        os.path.join(SETTINGS["BASE_DIR"], "assets", name),
        os.path.join(_runtime_base_path(), SETTINGS["ASSET_DIR"], name),
        os.path.join(_runtime_base_path(), SETTINGS["ASSET_DIR"], "nuni_timer_w.gif"),
        os.path.join(SETTINGS["BASE_DIR"], "assets", "nuni_timer_w.gif"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None
