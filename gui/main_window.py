from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QTextEdit, QScrollArea, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QProcess, QThread, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QFont, QTextCursor, QPalette, QColor
import sys
from PIL import Image
import io
import subprocess
import cv2
import numpy as np
import os
import tempfile
import threading
import queue
import time

class LogHandler(QObject):
    step_signal = pyqtSignal(str)
    image_signal = pyqtSignal(str)

    def emit_step(self, step_text):
        self.step_signal.emit(step_text)
    
    def emit_image(self, image_path):
        self.image_signal.emit(image_path)

class ScreenCaptureThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.adb_process = None
        self.last_frame_time = 0
        self.target_fps = 60  # 提高目标帧率到60fps
        self.frame_interval = 1.0 / self.target_fps
        self.frame_buffer = None  # 添加帧缓冲
    
    def run(self):
        while self.running:
            try:
                current_time = time.time()
                elapsed = current_time - self.last_frame_time
                
                if elapsed >= self.frame_interval:
                    self.last_frame_time = current_time
                    
                    # 使用adb exec-out命令直接获取屏幕数据
                    self.adb_process = subprocess.Popen(
                        ['adb', 'exec-out', 'screencap', '-p'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=10*1024*1024
                    )
                    
                    raw_data, _ = self.adb_process.communicate()
                    
                    if raw_data:
                        nparr = np.frombuffer(raw_data, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        
                        if frame is not None:
                            # 直接转换为RGB格式
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            # 在发送前进行缩放，减少UI线程的负担
                            height, width = frame.shape[:2]
                            new_width = int(width * 0.5)
                            new_height = int(height * 0.5)
                            frame = cv2.resize(frame, (new_width, new_height),
                                             interpolation=cv2.INTER_LINEAR)
                            self.frame_ready.emit(frame)
                
                # 使用更精确的休眠时间
                sleep_time = max(0, self.frame_interval - (time.time() - current_time))
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                print(f"捕获屏幕时出错: {str(e)}")
                time.sleep(0.01)
    
    def stop(self):
        self.running = False
        if self.adb_process:
            self.adb_process.terminate()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AgentCPM-GUI")
        self.setMinimumSize(1200, 800)
        
        # 设置全局字体
        self.setFont(QFont("Microsoft YaHei UI", 9))
        
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建主布局
        layout = QHBoxLayout(main_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧面板 - 手机屏幕显示
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)  # 移除左边距
        
        # 手机屏幕显示区域
        screen_frame = QFrame()
        screen_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 8px;
            }
        """)
        screen_layout = QVBoxLayout(screen_frame)
        screen_layout.setContentsMargins(0, 0, 0, 0)  # 移除内边距
        screen_layout.setSpacing(0)
        
        self.screen_label = QLabel()
        self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.screen_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                padding: 0px;
            }
        """)
        screen_layout.addWidget(self.screen_label)
        
        left_layout.addWidget(screen_frame)
        
        # 右侧面板 - 运行步骤显示
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 10, 10, 10)  # 设置边距
        
        # 步骤显示区域
        step_frame = QFrame()
        step_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: none;
                border-radius: 8px;
            }
        """)
        step_frame_layout = QVBoxLayout(step_frame)
        step_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        self.step_text = QTextEdit()
        self.step_text.setReadOnly(True)
        self.step_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: none;
                padding: 10px;
                font-family: 'Microsoft YaHei UI', 'Consolas', monospace;
                font-size: 13px;
                color: #d4d4d4;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background: #1e1e1e;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        
        step_frame_layout.addWidget(self.step_text)
        right_layout.addWidget(step_frame)
        
        # 设置左右面板的比例
        layout.addWidget(left_panel, 1)
        layout.addWidget(right_panel, 2)
        
        # 设置窗口样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #252526;
            }
            QWidget {
                background-color: #252526;
            }
        """)
        
        # 创建日志处理器
        self.log_handler = LogHandler()
        self.log_handler.step_signal.connect(self.update_step)
        self.log_handler.image_signal.connect(self.update_image)
        
        # 创建屏幕捕获线程
        self.capture_thread = ScreenCaptureThread()
        self.capture_thread.frame_ready.connect(self.update_phone_screen)
        self.capture_thread.start()
    
    @pyqtSlot(np.ndarray)
    def update_phone_screen(self, frame):
        """更新手机屏幕显示"""
        try:
            # 直接使用已经缩放好的frame
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line,
                            QImage.Format.Format_RGB888)
            
            pixmap = QPixmap.fromImage(qt_image)
            pixmap.setDevicePixelRatio(self.devicePixelRatio())
            
            self.screen_label.setPixmap(pixmap)
            self.screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        except Exception as e:
            print(f"更新手机屏幕时出错: {str(e)}")
    
    def update_image(self, image_path):
        """更新显示的图片"""
        pixmap = QPixmap(image_path)
        # 获取标签的实际大小
        label_size = self.screen_label.size()
        # 计算缩放比例，保持宽高比
        scaled_pixmap = pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.screen_label.setPixmap(scaled_pixmap)
    
    def update_step(self, step_text):
        """更新当前步骤"""
        cursor = self.step_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.step_text.setTextCursor(cursor)
        self.step_text.insertPlainText(step_text + "\n")
        # 滚动到底部
        self.step_text.verticalScrollBar().setValue(
            self.step_text.verticalScrollBar().maximum()
        )
    
    def closeEvent(self, event):
        """清理资源"""
        try:
            # 停止捕获线程
            if hasattr(self, 'capture_thread'):
                self.capture_thread.stop()
                self.capture_thread.wait()
            
            # 清理临时文件
            if hasattr(self, 'temp_dir'):
                import shutil
                shutil.rmtree(self.temp_dir)
        except:
            pass
        super().closeEvent(event) 