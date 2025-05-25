import sys
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
from loguru import logger

class GUIApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.window = MainWindow()
        
        # 配置日志处理器
        logger.remove()  # 移除默认处理器
        # 添加文件日志
        logger.add("logs/app.log", rotation="500 MB", level="INFO", encoding="utf-8")
    
    def run(self):
        """运行GUI应用"""
        self.window.show()
        return self.app.exec()

def start_gui():
    """启动GUI应用"""
    gui_app = GUIApp()
    return gui_app 