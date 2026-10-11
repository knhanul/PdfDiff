import os
from PyQt6.QtCore import Qt, QEventLoop
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication
from app.common.resources import get_timer_gif_path
from app.common.styles import COLOR_PRIMARY


def make_overlay_progress(parent):
    """로딩 오버레이 안의 진행률 막대."""
    bar = QProgressBar(parent)
    bar.setGeometry(36, 248, 328, 18)
    bar.setTextVisible(True)
    bar.setFormat("%p%")
    bar.setRange(0, 0)
    bar.setStyleSheet(f"""
        QProgressBar {{
            border: 1px solid #E5E5EA;
            border-radius: 6px;
            background: #F2F2F7;
            text-align: center;
            color: #1C1C1E;
            font-size: 11px;
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_PRIMARY};
            border-radius: 5px;
        }}
    """)
    return bar


def update_overlay_progress(bar, current, total):
    if total <= 0:
        bar.setRange(0, 0)
        return 0
    percent = max(0, min(100, int(current * 100 / total)))
    bar.setRange(0, 100)
    bar.setFormat("%p%")
    bar.setValue(percent)
    return percent


def style_task_progress(bar):
    bar.setTextVisible(True)
    bar.setFormat("%p%")
    bar.setStyleSheet(f"""
        QProgressBar {{
            border: 1px solid #E5E5EA;
            border-radius: 6px;
            background: #F2F2F7;
            text-align: center;
            color: #1C1C1E;
            font-size: 11px;
            min-height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_PRIMARY};
            border-radius: 5px;
        }}
    """)


def note_progress(bar, value):
    bar.setValue(value)
    QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


class LoadingDialog(QDialog):
    """작업 진행 중을 표시하는 로딩 다이얼로그
    
    assets/nuni_icon_orange_spin.gif 애니메이션을 사용하여 시간이 걸리는 작업 수행 중
    사용자에게 현재 작업 진행 중임을 알립니다.
    """
    
    def __init__(self, parent=None, message="작업 진행 중...", show_progress=False):
        super().__init__(parent)
        self.setWindowTitle("처리 중")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        
        # 진행률 표시 여부에 따라 크기 조정
        if show_progress:
            self.setFixedSize(300, 240)
        else:
            self.setFixedSize(300, 200)
        
        # 레이아웃 설정
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # GIF 애니메이션 레이블
        self.gif_label = QLabel()
        self.gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gif_label.setFixedSize(120, 120)
        
        # GIF 로드
        gif_path = get_timer_gif_path()
        if gif_path and os.path.exists(gif_path):
            self.movie = QMovie(gif_path)
            self.movie.setScaledSize(self.gif_label.size())
            self.gif_label.setMovie(self.movie)
        else:
            # GIF 파일이 없는 경우 대체 텍스트
            self.gif_label.setText("⏳")
            self.gif_label.setStyleSheet("font-size: 48px;")
        
        layout.addWidget(self.gif_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 메시지 레이블
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                color: #333333;
                font-weight: 500;
            }
        """)
        layout.addWidget(self.message_label)
        
        # 진행률 바 (선택적)
        if show_progress:
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #E0E0E0;
                    border-radius: 4px;
                    text-align: center;
                    height: 20px;
                }
                QProgressBar::chunk {
                    background-color: #007AFF;
                    border-radius: 4px;
                }
            """)
            layout.addWidget(self.progress_bar)
        else:
            self.progress_bar = None
        
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #E0E0E0;
            }
        """)
    
    def set_message(self, message):
        """메시지 텍스트 변경"""
        self.message_label.setText(message)
    
    def set_progress(self, current, total):
        """진행률 업데이트 (Worker의 progress signal에 연결)"""
        if self.progress_bar and total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.message_label.setText(f"처리 중... ({current}/{total})")
    
    def showEvent(self, event):
        """다이얼로그가 표시될 때 GIF 애니메이션 시작"""
        super().showEvent(event)
        if hasattr(self, 'movie') and self.movie:
            self.movie.start()
    
    def hideEvent(self, event):
        """다이얼로그가 숨겨질 때 GIF 애니메이션 정지"""
        super().hideEvent(event)
        if hasattr(self, 'movie') and self.movie:
            self.movie.stop()
    
    def closeEvent(self, event):
        """다이얼로그가 닫힐 때 GIF 애니메이션 정지"""
        super().closeEvent(event)
        if hasattr(self, 'movie') and self.movie:
            self.movie.stop()


class LoadingManager:
    """작업 진행 중 로딩 표시 관리 클래스 (동기 방식용)
    
    사용 예시:
        with LoadingManager(parent_widget, "PDF 비교 중..."):
            # 간단한 작업 수행 (무거운 작업은 Async 방식 권장)
            result = do_simple_operation()
    """
    
    def __init__(self, parent=None, message="작업 진행 중...", show_progress=False):
        self.dialog = LoadingDialog(parent, message, show_progress)
    
    def __enter__(self):
        self.dialog.show()
        return self.dialog
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dialog.close()
        self.dialog.deleteLater()
        return False
    
    def update_message(self, message):
        """메시지 업데이트"""
        self.dialog.set_message(message)
    
    def set_progress(self, current, total):
        """진행률 업데이트"""
        self.dialog.set_progress(current, total)
