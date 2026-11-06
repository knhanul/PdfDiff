import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from app.shell.theme import THEMES, build_shell_qss
from app.shell.sidebar_icons import ICON_PAINTERS, line_icon


def test_active_sidebar_is_soft_tint_with_left_bar_for_all_themes():
    for tid in THEMES:
        qss = build_shell_qss(tid)
        rule = qss[qss.index("QPushButton#sidebarBtn[active='true']"):].split('}')[0]
        assert 'border-left: 2px solid' in rule
        assert THEMES[tid]['sidebar_active_bg'] in rule
        assert 'on_accent' not in rule
        feat_rule = qss[qss.index("QPushButton#sidebarFeatureBtn"):].split('}')[0]
        assert THEMES[tid]['feature_bg'] in feat_rule
        assert THEMES[tid]['feature_border'] in feat_rule
        assert 'border-left: 3px solid' in feat_rule


def test_default_matches_quiet_brand_tokens():
    t = THEMES['default']
    assert t['sidebar_bg'] == '#F3F0ED' and t['sidebar_border'] == '#E2DED9'


def test_line_icons_render():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    for key in ICON_PAINTERS:
        assert not line_icon(key, '#8A827A').isNull()
