import json
import subprocess
import time
from typing import Dict, Any, Union, List, Tuple
import urllib.parse

class ADBController:
    def __init__(self):
        """初始化ADB控制器"""
        self._check_adb_connection()
    
    def _check_adb_connection(self) -> None:
        """检查ADB连接状态"""
        try:
            subprocess.run(['adb', 'devices'], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            raise RuntimeError("ADB未正确安装或无法访问")
        except FileNotFoundError:
            raise RuntimeError("未找到ADB命令，请确保ADB已安装并添加到系统PATH中")

    def _execute_adb_command(self, command: List[str]) -> str:
        """执行ADB命令并返回输出"""
        try:
            result = subprocess.run(['adb'] + command, check=True, capture_output=True, text=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ADB命令执行失败: {e.stderr}")

    def _get_screen_size(self) -> Tuple[int, int]:
        """获取设备屏幕尺寸"""
        output = self._execute_adb_command(['shell', 'wm', 'size'])
        # 输出格式: "Physical size: 1080x2340"
        size = output.split(': ')[1].split('x')
        return int(size[0]), int(size[1])

    def _normalize_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        """将归一化坐标(0-1000)转换为实际屏幕坐标"""
        screen_width, screen_height = self._get_screen_size()
        # 计算缩放比例，保持与截图缩放一致
        max_line_res = 1120
        scale = 1.0
        if screen_height > max_line_res:
            scale = max_line_res / screen_height
        if screen_width > max_line_res:
            scale = min(scale, max_line_res / screen_width)
        
        # 先缩放到与截图相同的尺寸
        scaled_x = int(x * screen_width * scale / 1000)
        scaled_y = int(y * screen_height * scale / 1000)
        
        # 再映射回实际屏幕尺寸
        actual_x = int(scaled_x / scale)
        actual_y = int(scaled_y / scale)
        return actual_x, actual_y

    def execute_action(self, action_json: Union[str, Dict[str, Any]]) -> None:
        """执行模型输出的JSON动作"""
        if isinstance(action_json, str):
            action = json.loads(action_json)
        else:
            action = action_json

        # 处理思考过程（如果有）
        if "thought" in action:
            print(f"思考过程: {action['thought']}")

        # 处理状态（如果有）
        if "STATUS" in action:
            print(f"任务状态: {action['STATUS']}")

        # 执行具体动作
        if "POINT" in action:
            x, y = self._normalize_coordinates(action["POINT"][0], action["POINT"][1])
            
            if "to" in action:
                # 滑动操作
                if isinstance(action["to"], str):
                    # 方向滑动
                    duration = action.get("duration", 300)
                    if action["to"] == "up":
                        self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(x), str(y-300), str(duration)])
                    elif action["to"] == "down":
                        self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(x), str(y+300), str(duration)])
                    elif action["to"] == "left":
                        self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(x-300), str(y), str(duration)])
                    elif action["to"] == "right":
                        self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(x+300), str(y), str(duration)])
                else:
                    # 坐标滑动
                    to_x, to_y = self._normalize_coordinates(action["to"][0], action["to"][1])
                    duration = action.get("duration", 300)
                    self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(to_x), str(to_y), str(duration)])
            else:
                # 点击或长按操作
                duration = action.get("duration", 100)
                if duration > 200:
                    self._execute_adb_command(['shell', 'input', 'swipe', str(x), str(y), str(x), str(y), str(duration)])
                else:
                    self._execute_adb_command(['shell', 'input', 'tap', str(x), str(y)])

        elif "PRESS" in action:
            # 按键操作
            key = action["PRESS"].lower()
            self._execute_adb_command(['shell', 'input', 'keyevent', self._get_keycode(key)])

        elif "TYPE" in action:
            text = action["TYPE"]
            # 如果文本是URL编码的，先进行解码
            if '%' in text:
                text = urllib.parse.unquote(text)
            self._execute_adb_command(['shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', text])
            time.sleep(0.5)  # 等待输入完成

        elif "duration" in action and not any(key in action for key in ["POINT", "PRESS", "TYPE"]):
            # 等待操作
            time.sleep(action["duration"] / 1000.0)

    def _get_keycode(self, key: str) -> str:
        """获取按键对应的keycode"""
        keycode_map = {
            "home": "3",
            "back": "4",
            "enter": "66"
        }
        return keycode_map.get(key, "3")  # 默认返回HOME键的keycode 

if __name__ == "__main__":
    adb_controller = ADBController()
    adb_controller.execute_action({"TYPE": "123"})