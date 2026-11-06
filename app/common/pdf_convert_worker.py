"""
PDF Convert Worker - 백그라운드 스레드에서 파일→PDF 변환 수행

한글/오피스 COM 자동화 호출이 대화상자 등으로 블로킹되어도
UI 스레드가 멈추지 않도록 QThread + Worker 패턴으로 분리합니다.
COM은 스레드별 초기화가 필요하므로 run()에서 CoInitialize를 호출합니다.
"""
import os
import shutil
import tempfile
import time
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from app.common.pdf_convert import convert_to_pdf, merge_pdfs, unique_pdf_path


class PdfConvertWorker(QObject):
    """
    파일→PDF 변환 작업을 백그라운드 스레드에서 실행하는 Worker

    모든 입력 데이터는 __init__에서 확정되며 UI 접근은 signal로만 수행
    """

    # Signals
    progress = pyqtSignal(int, int)                    # (current, total)
    file_done = pyqtSignal(str, bool, str, str)        # (src, ok, dest, error)
    result_ready = pyqtSignal(dict)                    # 최종 결과 데이터
    finished = pyqtSignal()                            # 작업 완료
    error = pyqtSignal(str)                            # 예외 발생 시 메시지

    def __init__(self,
                 jobs: List[Tuple[str, str]],
                 merge: bool = False,
                 merge_dir: str = "",
                 merge_stem: str = ""):
        """
        Args:
            jobs: (변환 원본 경로, 출력 디렉터리) 목록
            merge: True면 변환된 PDF를 하나로 병합
            merge_dir: 병합 결과를 저장할 디렉터리
            merge_stem: 병합 결과 파일명(확장자 제외)
        """
        super().__init__(None)
        self._jobs = list(jobs)
        self._merge = merge
        self._merge_dir = merge_dir
        self._merge_stem = merge_stem
        self._is_running = True

    def stop(self):
        """안전한 종료 요청 (현재 파일 완료 후 중지)"""
        self._is_running = False

    def run(self):
        """백그라운드에서 실행될 변환 로직 (QThread에서 호출)"""
        com_initialized = False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                com_initialized = True
            except ImportError:
                pass
            if self._merge:
                self._run_merged()
            else:
                self._run_each()
            self.finished.emit()
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")
        finally:
            if com_initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _run_each(self):
        """파일별 개별 변환 (PDF 제외는 호출 전에 걸러져 있음)"""
        ok = 0
        failed = []
        total = len(self._jobs)
        for index, (src, target) in enumerate(self._jobs, start=1):
            if not self._is_running:
                break
            try:
                dest = convert_to_pdf(src, target)
            except Exception as error:
                failed.append(f"{Path(src).name}: {error}")
                self.file_done.emit(src, False, "", str(error))
            else:
                ok += 1
                self.file_done.emit(src, True, str(dest), "")
            self.progress.emit(index, total)
        self.result_ready.emit({
            'kind': 'files',
            'cancelled': not self._is_running,
            'ok': ok,
            'failed': failed,
        })

    def _run_merged(self):
        """체크한 파일을 변환 후 하나의 PDF로 병합"""
        failed = []
        total = len(self._jobs)
        temp_dir = self._make_merge_temp()
        try:
            pdfs = []
            for index, (src, target) in enumerate(self._jobs, start=1):
                if not self._is_running:
                    self.result_ready.emit({
                        'kind': 'merged',
                        'cancelled': True,
                        'ok': False,
                        'failed': failed,
                    })
                    return
                try:
                    if Path(src).suffix.lower() == ".pdf":
                        pdfs.append(src)
                        self.file_done.emit(src, True, src, "")
                    else:
                        pdfs.append(str(convert_to_pdf(src, temp_dir)))
                        self.file_done.emit(src, True, str(pdfs[-1]), "")
                except Exception as error:
                    failed.append(f"{Path(src).name}: {error}")
                    self.file_done.emit(src, False, "", str(error))
                    self.progress.emit(index, total)
                    self.result_ready.emit({
                        'kind': 'merged',
                        'cancelled': False,
                        'ok': False,
                        'failed': failed,
                    })
                    return
                self.progress.emit(index, total)
            dest = unique_pdf_path(self._merge_dir, self._merge_stem)
            merge_pdfs(pdfs, dest)
            self.result_ready.emit({
                'kind': 'merged',
                'cancelled': False,
                'ok': True,
                'dest': str(dest),
                'count': len(pdfs),
                'failed': failed,
            })
        finally:
            _remove_tree(temp_dir)

    def _make_merge_temp(self):
        """병합 중간 산출물용 임시 폴더를 결과 폴더 안에 숨김으로 만든다.

        시스템 TEMP가 공용 문서 폴더로 잡힌 환경(예: 알PDF CreatorTemp)에서
        변환 중간 PDF가 사용자에게 보이는 것을 막기 위함이다.
        """
        base = Path(self._merge_dir)
        base.mkdir(parents=True, exist_ok=True)
        for stale in base.glob("~pdfmerge_*"):
            if stale.is_dir():
                _remove_tree(stale)
        tmp = Path(tempfile.mkdtemp(prefix="~pdfmerge_", dir=base))
        _hide_path(tmp)
        return str(tmp)


def _hide_path(path):
    """Windows에서 폴더를 숨김 처리해 탐색기에 보이지 않게 한다."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x02)  # FILE_ATTRIBUTE_HIDDEN
    except Exception:
        pass


def _remove_tree(path):
    """백신/외부 프로그램의 잠금으로 즉시 지워지지 않는 경우를 대비해 재시도 후 삭제"""
    for _ in range(3):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
        if not Path(path).exists():
            return
        time.sleep(0.3)


class ConvertThreadManager(QObject):
    """
    변환 Worker와 Thread를 관리하는 매니저

    사용 예시:
        manager = ConvertThreadManager(self)
        manager.setup_worker(jobs, merge=True, merge_dir=..., merge_stem=...)
        manager.start()
    """

    # 전달용 signals (Widget에서 연결)
    progress = pyqtSignal(int, int)
    file_done = pyqtSignal(str, bool, str, str)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread: Optional[QThread] = None
        self.worker: Optional[PdfConvertWorker] = None

    def setup_worker(self,
                     jobs: List[Tuple[str, str]],
                     merge: bool = False,
                     merge_dir: str = "",
                     merge_stem: str = ""):
        """Worker와 Thread 설정 (start 전에 호출)"""
        self.cleanup()
        self.worker = PdfConvertWorker(
            jobs=jobs,
            merge=merge,
            merge_dir=merge_dir,
            merge_stem=merge_stem,
        )
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)

        self.worker.progress.connect(self.progress)
        self.worker.file_done.connect(self.file_done)
        self.worker.result_ready.connect(self.result_ready)
        self.worker.finished.connect(self.finished)
        self.worker.error.connect(self.error)

        self.thread.finished.connect(self._on_thread_finished)
        self.thread.started.connect(self.worker.run)

    def start(self):
        """변환 작업 시작 (Thread 실행)"""
        if self.thread and not self.thread.isRunning():
            self.thread.start()

    def cancel(self):
        """작업 취소 (Soft Exit) - COM 호출 블로킹 시 terminate까지 대기"""
        if self.worker:
            self.worker.stop()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            if not self.thread.wait(2000):
                # COM 호출이 멈춘 경우에도 앱 종료가 가능하도록 최후 수단 사용
                self.thread.terminate()
                self.thread.wait(500)

    def cleanup(self):
        """리소스 정리"""
        if self.worker:
            try:
                self.worker.progress.disconnect()
                self.worker.file_done.disconnect()
                self.worker.result_ready.disconnect()
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.worker.deleteLater()
            self.worker = None

        if self.thread:
            try:
                self.thread.finished.disconnect()
                self.thread.started.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(1000)
            self.thread.deleteLater()
            self.thread = None

    def _on_thread_finished(self):
        """Thread 종료 시 호출"""
        self.cleanup()
