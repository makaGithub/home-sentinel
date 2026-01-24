# c_silence.py
"""
Модуль для полного подавления C-level stdout/stderr (OpenBLAS/MKL/LAPACK).
Импортируется ПЕРВЫМ в main.py, чтобы до импорта numpy/torch и т.п.
"""

import os
import sys

# Подавляем вывод Ultralytics (YOLO) - должно быть ДО импорта
os.environ["YOLO_VERBOSE"] = "False"
os.environ["ULTRALYTICS_SETTINGS"] = "False"

try:
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    # Сохраняем настоящие stdout/stderr Python
    py_stdout_fd = os.dup(1)
    py_stderr_fd = os.dup(2)

    # Перенаправляем C stdout/stderr → /dev/null
    os.dup2(devnull_fd, 1)   # fd=1 C stdout
    os.dup2(devnull_fd, 2)   # fd=2 C stderr

    # Восстанавливаем Python stdout/stderr в отдельные объекты
    sys.stdout = os.fdopen(py_stdout_fd, "w", buffering=1)
    sys.stderr = os.fdopen(py_stderr_fd, "w", buffering=1)

    os.close(devnull_fd)
except Exception:
    # Если что-то пошло не так — просто не глушим
    pass
