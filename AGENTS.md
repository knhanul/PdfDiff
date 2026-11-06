# Project verification

- Run the unittest suite from the repository root in PowerShell: `.\.venv\Scripts\python.exe -m unittest discover -s tests`.
- Run PDF comparison regression tests: `.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pdf_compare_multipage.py`.
- PDF comparison UI tests use Qt's offscreen platform and generated temporary PDFs; no interactive desktop is required.
