"""
PDF Compare Worker - 백그라운드 스레드에서 PDF 비교 수행

QThread + Worker 패턴을 사용하여 메인 스레드 블로킹 없이
PDF 비교 작업을 수행하고 결과를 signal로 전달합니다.
"""
import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple, Optional


class PdfCompareWorker(QObject):
    """
    PDF 비교 작업을 백그라운드 스레드에서 실행하는 Worker
    
    모든 입력 데이터는 __init__에서 복사되어 스레드 안전성 보장
    UI 접근은 signal을 통해서만 수행
    """
    
    # Signals
    started = pyqtSignal()                      # 작업 시작 알림
    progress = pyqtSignal(int, int)             # (current, total) - 100개 단위로 전송
    result_ready = pyqtSignal(dict)             # 비교 결과 데이터 전송
    finished = pyqtSignal()                     # 작업 완료
    error = pyqtSignal(str)                     # 오류 발생 시 메시지 전송
    
    def __init__(self,
                 char_data1: List[Dict],
                 char_data2: List[Dict],
                 raw_text1: str,
                 raw_text2: str,
                 pending_rect1: Optional[Tuple] = None,
                 pending_rect2: Optional[Tuple] = None):
        """
        Args:
            char_data1: PDF1의 문자 데이터 리스트 (참조 저장, 복사는 run()에서)
            char_data2: PDF2의 문자 데이터 리스트  
            raw_text1: PDF1의 원본 텍스트
            raw_text2: PDF2의 원본 텍스트
            pending_rect1: PDF1의 선택 영역 (page_num, rect)
            pending_rect2: PDF2의 선택 영역 (page_num, rect)
        """
        # 부모 없이 생성 (moveToThread를 위해 필수)
        super().__init__(None)
        
        # 참조만 저장 (복사는 run() 내부에서 스레드로 이동)
        self._char_data1_ref = char_data1
        self._char_data2_ref = char_data2
        self._raw_text1 = raw_text1 or ''
        self._raw_text2 = raw_text2 or ''
        self._pending_rect1 = pending_rect1
        self._pending_rect2 = pending_rect2
        
        # 안전한 종료을 위한 플래그
        self._is_running = False
        
    def stop(self):
        """안전한 종료 요청 (Soft Exit)"""
        self._is_running = False
        
    def run(self):
        """백그라운드에서 실행될 비교 로직 (QThread에서 호출)"""
        self._is_running = True
        
        try:
            self.started.emit()
            
            # 1. 데이터 복사 및 준비 (스레드 내부에서 수행)
            if not self._is_running:
                return  # Early exit if cancelled
                
            self.char_data1 = list(self._char_data1_ref) if self._char_data1_ref else []
            
            if not self._is_running:
                return
                
            self.char_data2 = list(self._char_data2_ref) if self._char_data2_ref else []
            self.raw_text1 = self._raw_text1
            self.raw_text2 = self._raw_text2
            self.pending_rect1 = self._pending_rect1
            self.pending_rect2 = self._pending_rect2
            
            s1_norm = ''.join([d.get('char', '') for d in self.char_data1])
            
            if not self._is_running:
                return
                
            s2_norm = ''.join([d.get('char', '') for d in self.char_data2])
            
            # 2. SequenceMatcher 실행
            matcher = SequenceMatcher(None, s1_norm, s2_norm, autojunk=False)
            opcodes = list(matcher.get_opcodes())
            total_ops = len(opcodes)
            
            # 3. 하이라이트 데이터 생성 (UI 직접 접근 금지)
            highlights1: List[Dict] = []  # PDF1 하이라이트 데이터
            highlights2: List[Dict] = []  # PDF2 하이라이트 데이터
            diff_pages1: List[Tuple[int, float]] = []  # (page, y_center)
            diff_pages2: List[Tuple[int, float]] = []
            
            # Progress signal 시간 기반 조절 (최소 0.1초 간격)
            last_progress_time = time.time()
            progress_interval = 0.1
            if total_ops <= 0:
                self.progress.emit(1, 1)
            else:
                self.progress.emit(0, total_ops)

            for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
                if not self._is_running:
                    return

                current_time = time.time()
                if current_time - last_progress_time >= progress_interval or idx + 1 == total_ops:
                    self.progress.emit(idx + 1, total_ops)
                    last_progress_time = current_time

                if tag == 'equal':
                    continue
                
                # 하이라이트 데이터 수집
                if tag in ('delete', 'replace'):
                    hl_data, pages = self._collect_highlights(self.char_data1, i1, i2)
                    highlights1.extend(hl_data)
                    diff_pages1.extend(pages)
                    
                if tag in ('insert', 'replace'):
                    hl_data, pages = self._collect_highlights(self.char_data2, j1, j2)
                    highlights2.extend(hl_data)
                    diff_pages2.extend(pages)
            
            # 4. 결과 데이터 패키징
            result = {
                'highlights1': highlights1,
                'highlights2': highlights2,
                'diff_pages1': sorted(set(diff_pages1)),
                'diff_pages2': sorted(set(diff_pages2)),
                's1_norm': s1_norm,
                's2_norm': s2_norm,
                's1_raw': self.raw_text1,
                's2_raw': self.raw_text2,
                'pending_rect1': self.pending_rect1,
                'pending_rect2': self.pending_rect2,
                'opcodes': opcodes,  # 동기화용 anchor 생성에 필요
            }
            
            self.result_ready.emit(result)
            self.finished.emit()
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
    
    def _collect_highlights(self, char_data: List[Dict], start_idx: int, end_idx: int) -> Tuple[List[Dict], List[Tuple[int, float]]]:
        """
        하이라이트 위치 데이터만 수집 (UI 미접근)
        
        Returns:
            (highlights_data, diff_pages)
            highlights_data: [{'page': int, 'bbox': tuple, 'word_id': int}, ...]
            diff_pages: [(page_num, y_center), ...]
        """
        word_ids = set()
        for i in range(start_idx, end_idx):
            if i < len(char_data):
                word_ids.add(char_data[i].get('word_id', -1))
        
        highlights = []
        diff_pages = []
        
        for char in char_data:
            wid = char.get('word_id', -1)
            if wid in word_ids and wid != -1:
                bbox = char.get('bbox')
                page = char.get('page', 0)
                if bbox:
                    highlights.append({
                        'page': page,
                        'bbox': bbox,
                        'word_id': wid
                    })
                    # y_center 계산 (동기화용)
                    y_center = (bbox[1] + bbox[3]) / 2
                    diff_pages.append((page, y_center))
        
        return highlights, diff_pages


class CompareThreadManager(QObject):
    """
    PDF 비교 Worker와 Thread를 관리하는 매니저
    
    사용 예시:
        manager = CompareThreadManager(self)
        manager.setup_worker(
            char_data1, char_data2,
            raw_text1, raw_text2
        )
        manager.start_comparison()
    """
    
    # 전달용 signals (Widget에서 연결)
    started = pyqtSignal()
    progress = pyqtSignal(int, int)
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread: Optional[QThread] = None
        self.worker: Optional[PdfCompareWorker] = None
        
    def setup_worker(self,
                     char_data1: List[Dict],
                     char_data2: List[Dict],
                     raw_text1: str,
                     raw_text2: str,
                     pending_rect1: Optional[Tuple] = None,
                     pending_rect2: Optional[Tuple] = None):
        """Worker와 Thread 설정 (start 전에 호출)"""
        # 기존 스레드 정리
        self.cleanup()
        
        # Worker 생성 (부모 없이 생성 - moveToThread 위해 필수)
        self.worker = PdfCompareWorker(
            char_data1=char_data1,
            char_data2=char_data2,
            raw_text1=raw_text1,
            raw_text2=raw_text2,
            pending_rect1=pending_rect1,
            pending_rect2=pending_rect2
            # parent=None (기본값)
        )
        
        # Thread 생성 및 설정
        self.thread = QThread(self)
        self.worker.moveToThread(self.thread)
        
        # Signal 연결
        self.worker.started.connect(self.started)
        self.worker.progress.connect(self.progress)
        self.worker.result_ready.connect(self.result_ready)
        self.worker.finished.connect(self.finished)
        self.worker.error.connect(self.error)
        
        # Thread 종료 시 정리
        self.thread.finished.connect(self._on_thread_finished)
        
        # Thread 시작 시 Worker.run() 실행
        self.thread.started.connect(self.worker.run)
    
    def start_comparison(self):
        """비교 작업 시작 (Thread 실행)"""
        if self.thread and not self.thread.isRunning():
            self.thread.start()
    
    def cancel(self):
        """작업 취소 (안전한 Soft Exit) - terminate() 대신 stop() 사용"""
        if self.worker:
            # Worker에 종료 신호 보내기 (루프 내에서 체크하여 안전하게 종료)
            self.worker.stop()
        
        if self.thread and self.thread.isRunning():
            # quit()은 이벤트 루프에 quit 이벤트를 추가 (즉시 종료 아님)
            self.thread.quit()
            # Worker가 _is_running 체크 후 자연스럽게 종료되도록 대기
            if not self.thread.wait(2000):  # 2초까지 대기
                # 여전히 실행 중이면 강제 종료 (최후의 수단)
                self.thread.terminate()
                self.thread.wait(500)
    
    def cleanup(self):
        """리소스 정리 (메모리 누수 방지를 위한 철저한 순서)"""
        # 1. Worker 먼저 정리 (Thread보다 먼저)
        if self.worker:
            # Signal 연결 해제 (메모리 누수 방지)
            try:
                self.worker.started.disconnect()
                self.worker.progress.disconnect()
                self.worker.result_ready.disconnect()
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except (TypeError, RuntimeError):
                pass  # 이미 연결이 해제되었거나 없음
            
            self.worker.deleteLater()
            self.worker = None
        
        # 2. Thread 정리 (Worker 삭제 후)
        if self.thread:
            # Signal 연결 해제
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
