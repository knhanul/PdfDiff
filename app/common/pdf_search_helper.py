"""
PDF Search Helper - Common search functionality for PDF viewers
Provides unified search logic, result management, and highlighting
"""
from PyQt6.QtCore import QTimer, QRect
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton


class PDFSearchHelper:
    """Common search functionality for PDF viewers"""
    
    def __init__(self, viewer):
        self.viewer = viewer
        self.search_results = []
        self.current_search_index = 0
        self.search_highlights = {}
        self.current_highlight = None
        self.current_highlights = {}
        self.search_count_label = None
        
    def setup_search_ui(self, toolbar_layout):
        """Setup search UI components"""
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search...')
        self.search_input.setObjectName('toolbarSearch')
        self.search_input.setFixedWidth(150)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.find_next)
        
        # Navigation buttons
        self.find_prev_btn = QPushButton('Prev')
        self.find_prev_btn.setObjectName('toolbarBtn')
        self.find_prev_btn.setFixedSize(50, 28)
        self.find_prev_btn.setStyleSheet('font-size: 11px; padding: 0px; margin: 0px;')
        self.find_prev_btn.clicked.connect(self.find_previous)

        self.find_next_btn = QPushButton('Next')
        self.find_next_btn.setObjectName('toolbarBtn')
        self.find_next_btn.setFixedSize(50, 28)
        self.find_next_btn.setStyleSheet('font-size: 11px; padding: 0px; margin: 0px;')
        self.find_next_btn.clicked.connect(self.find_next)
        
        # Search count label
        self.search_count_label = QLabel()
        self.search_count_label.setObjectName('toolbarLabel')
        self.search_count_label.setFixedWidth(60)
        self.search_count_label.setText('0/0')
        self.search_count_label.setStyleSheet('color: #8E8E93; font-size: 11px;')
        
        # Add to toolbar
        toolbar_layout.addWidget(self.search_input)
        toolbar_layout.addWidget(self.find_prev_btn)
        toolbar_layout.addWidget(self.find_next_btn)
        toolbar_layout.addWidget(self.search_count_label)
        
        # Set default Korean text
        self.set_placeholder_text('검색어 입력')
        self.set_button_text('이전', '이후')
        
        return self.search_input, self.find_prev_btn, self.find_next_btn, self.search_count_label
        
    def on_search_text_changed(self, text):
        """Handle search text change - search in real-time as user types"""
        if not text.strip():
            self.clear_search_highlights()
            self.search_results = []
            self.current_search_index = 0
            self.update_search_count()
            return
        
        # Real-time search: search and highlight as user types
        self.clear_search_highlights()
        self.search_in_pdf(text)
            
    def search_in_pdf(self, text):
        """Search for text in PDF"""
        if not self.viewer.pdf_doc or not text.strip():
            return
            
        self.search_results = []
        for page_num in range(len(self.viewer.pdf_doc)):
            page = self.viewer.pdf_doc.load_page(page_num)
            text_instances = page.search_for(text)
            for inst in text_instances:
                self.search_results.append((page_num, inst))
                
        if self.search_results:
            self.highlight_search_results()
            self.current_search_index = -1  # Start at -1, user presses next to go to first
            
        self.update_search_count()
        
    def highlight_search_results(self):
        """Highlight all search results"""
        if not self.search_results:
            return
            
        for page_num, rect in self.search_results:
            if page_num not in self.search_highlights:
                self.search_highlights[page_num] = []
            self.search_highlights[page_num].append(rect)
            
        self.viewer.refresh_highlights()
        
    def clear_search_highlights(self):
        """Clear all search highlights"""
        self.search_highlights.clear()
        if hasattr(self, 'current_highlights'):
            self.current_highlights.clear()
        self.current_highlight = None
        self.viewer.refresh_highlights()
        
    def find_next(self):
        """Navigate to next search result"""
        if not self.search_results:
            search_text = self.search_input.text().strip()
            if search_text:
                self.clear_search_highlights()
                self.search_in_pdf(search_text)
            return
            
        if self.search_results:
            self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
            self.go_to_search_result(self.current_search_index)
            self.update_search_count()
            
    def find_previous(self):
        """Navigate to previous search result"""
        if not self.search_results:
            search_text = self.search_input.text().strip()
            if search_text:
                self.clear_search_highlights()
                self.search_in_pdf(search_text)
            return
            
        if self.search_results:
            self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
            self.go_to_search_result(self.current_search_index)
            self.update_search_count()
            
    def go_to_search_result(self, index):
        """Navigate to specific search result"""
        if 0 <= index < len(self.search_results):
            # Clear previous current highlight
            if self.current_highlight:
                self.remove_current_highlight()
                
            page_num, rect = self.search_results[index]
            # Scroll to the page
            if page_num < len(self.viewer.page_labels):
                self.viewer.ensureWidgetVisible(self.viewer.page_labels[page_num])
                # Highlight current result
                self.highlight_current_result(page_num, rect)
                
    def highlight_current_result(self, page_num, rect):
        """Highlight current search result"""
        # Store current highlight info
        self.current_highlight = (page_num, rect)
        
        # Create a separate highlight for current result
        if page_num not in self.current_highlights:
            self.current_highlights[page_num] = []
        self.current_highlights[page_num].append(rect)
        
        self.viewer.refresh_highlights()
        
    def remove_current_highlight(self):
        """Remove current search result highlight"""
        if self.current_highlight and hasattr(self, 'current_highlights'):
            page_num, rect = self.current_highlight
            if page_num in self.current_highlights:
                try:
                    self.current_highlights[page_num].remove(rect)
                    if not self.current_highlights[page_num]:
                        del self.current_highlights[page_num]
                    self.viewer.refresh_highlights()
                except ValueError:
                    pass
            self.current_highlight = None
            
    def update_search_count(self):
        """Update search result count display"""
        if self.search_count_label:
            total = len(self.search_results)
            if total == 0:
                self.search_count_label.setText('0/0')
            elif self.current_search_index < 0:
                # Results found but none selected yet
                self.search_count_label.setText(f'0/{total}')
            else:
                current = self.current_search_index + 1
                self.search_count_label.setText(f'{current}/{total}')
            
    def render_search_highlights(self, painter, page_num, scale):
        """Render search highlights for a page"""
        # Add search highlights in yellow (standard search highlight color)
        if page_num in self.search_highlights:
            for bbox in self.search_highlights[page_num]:
                rect = QRect(int(bbox[0] * scale), int(bbox[1] * scale),
                           int((bbox[2] - bbox[0]) * scale), int((bbox[3] - bbox[1]) * scale))
                # Bright yellow for all search results - more visible
                painter.fillRect(rect, QColor(255, 255, 0, 100))
                
        # Add current result highlight with orange border
        if page_num in self.current_highlights:
            for bbox in self.current_highlights[page_num]:
                rect = QRect(int(bbox[0] * scale), int(bbox[1] * scale),
                           int((bbox[2] - bbox[0]) * scale), int((bbox[3] - bbox[1]) * scale))
                # Orange highlight for current result
                painter.fillRect(rect, QColor(255, 200, 100, 120))
                # Orange border to clearly show current result
                painter.setPen(QPen(QColor(255, 140, 0), 2))
                painter.drawRect(rect)
                
    def clear_all_search_data(self):
        """Clear all search-related data"""
        self.search_results = []
        self.current_search_index = -1  # Reset to -1 (no selection)
        self.search_highlights = {}
        self.current_highlight = None
        if hasattr(self, 'current_highlights'):
            self.current_highlights.clear()
        self.update_search_count()
        
    def set_placeholder_text(self, text):
        """Set search input placeholder text"""
        if self.search_input:
            self.search_input.setPlaceholderText(text)
            
    def set_button_text(self, prev_text, next_text):
        """Set navigation button text"""
        if self.find_prev_btn:
            self.find_prev_btn.setText(prev_text)
        if self.find_next_btn:
            self.find_next_btn.setText(next_text)
