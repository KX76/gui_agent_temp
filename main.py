import torch
import os
import warnings
import threading
import time
import subprocess
import tempfile
from datetime import datetime
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

from transformers import AutoTokenizer, AutoModelForCausalLM
from PIL import Image
import json
from loguru import logger
from gui.app import start_gui, GUIApp
import sys
from adb_controller import ADBController

logger.add("logs/app.log", rotation="500 MB", level="INFO", encoding="utf-8")

warnings.filterwarnings("ignore", category=FutureWarning)
logger.warning("已忽略 FutureWarning 警告，这些警告与图像处理器相关，不影响模型功能")

def get_screen_shot():
    """使用ADB获取屏幕截图"""
    try:
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(temp_dir, f"screen_{timestamp}.png")
        
        subprocess.run(["adb", "shell", "screencap", "-p", "/sdcard/screen.png"], check=True)
        subprocess.run(["adb", "pull", "/sdcard/screen.png", screenshot_path], check=True)
        subprocess.run(["adb", "shell", "rm", "/sdcard/screen.png"], check=True)
        
        logger.info(f"截图已保存到: {screenshot_path}")
        return screenshot_path
    except subprocess.CalledProcessError as e:
        logger.error(f"ADB截图失败: {str(e)}")
        raise Exception("无法获取屏幕截图，请确保ADB已连接并正常工作")

def main(gui_app):
    try:
        # 1. Load the model and tokenizer
        model_path = "model/AgentCPM-GUI"  # model path
        logger.info(f"开始加载模型和分词器，模型路径: {model_path}")
        gui_app.window.log_handler.emit_step("正在加载模型和分词器...")
        
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
            low_cpu_mem_usage=True,
            load_in_8bit=True
        )
        logger.success("模型和分词器加载完成")

        # 2. Build the input
        instruction = "请在李子柒的店里买一件东西"
        logger.info(f"处理指令: {instruction}")
        gui_app.window.log_handler.emit_step(f"初始指令: {instruction}")
        
        logger.info("正在获取屏幕截图...")
        gui_app.window.log_handler.emit_step("正在获取屏幕截图...")
        image_path = get_screen_shot()
        gui_app.window.log_handler.emit_image(image_path)
        
        image = Image.open(image_path).convert("RGB")

        # 3. Resize the longer side to 1120 px to save compute & memory
        def __resize__(origin_img):
            resolution = origin_img.size
            w,h = resolution
            max_line_res = 1120
            if max_line_res is not None:
                max_line = max_line_res
                if h > max_line:
                    w = int(w * max_line / h)
                    h = max_line
                if w > max_line:
                    h = int(h * max_line / w)
                    w = max_line
            img = origin_img.resize((w,h),resample=Image.Resampling.LANCZOS)
            logger.debug(f"图片调整大小: {resolution} -> {(w,h)}")
            return img
        image = __resize__(image)

        # 4. Build the message format
        messages = [{
            "role": "user",
            "content": [
                f"<Question>{instruction}</Question>\n当前屏幕截图：",
                image
            ]
        }]
        logger.debug("消息格式构建完成")

        # 5. Inference
        ACTION_SCHEMA = json.load(open('eval/utils/schema/schema.json', encoding="utf-8"))
        items = list(ACTION_SCHEMA.items())
        insert_index = 3
        items.insert(insert_index, ("required", ["thought"])) # enable/disable thought by setting it to "required"/"optional"
        ACTION_SCHEMA = dict(items)
        SYSTEM_PROMPT = f'''# Role
你是一名熟悉安卓系统触屏GUI操作的智能体，将根据用户的问题，分析当前界面的GUI元素和布局，生成相应的操作。

# Task
针对用户问题，根据输入的当前屏幕截图，输出下一步的操作。你需要将复杂任务分解成多个步骤，并逐步执行。

# Rule
- 以紧凑JSON格式输出
- 输出操作必须遵循Schema约束
- 每一步执行后，需要等待界面更新
- 如果任务完成，在输出中添加 "task_completed": true
- 如果任务未完成，继续执行下一步

# Schema
{json.dumps(ACTION_SCHEMA, indent=None, ensure_ascii=False, separators=(',', ':'))}'''

        execution_history = []
        max_steps = 10
        current_step = 0
        
        adb_controller = ADBController()
        
        while current_step < max_steps:
            logger.info(f"执行第 {current_step + 1} 步")
            gui_app.window.log_handler.emit_step(f"执行第 {current_step + 1} 步")
            
            image_path = get_screen_shot()
            image = Image.open(image_path).convert("RGB")
            image = __resize__(image)
            gui_app.window.log_handler.emit_image(image_path)
            
            if execution_history:
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(execution_history[-1], ensure_ascii=False)
                })
            
            messages.append({
                "role": "user",
                "content": [
                    f"<Question>{instruction}</Question>\n当前屏幕截图：",
                    image
                ]
            })
            
            outputs = model.chat(
                image=None,
                msgs=messages,
                system_prompt=SYSTEM_PROMPT,
                tokenizer=tokenizer,
                temperature=0.1,
                top_p=0.3,
                n=1,
            )
            
            if isinstance(outputs, str):
                try:
                    outputs = json.loads(outputs)
                except json.JSONDecodeError:
                    logger.error(f"无法解析模型输出为JSON: {outputs}")
                    outputs = {"error": "输出格式错误"}
            
            execution_history.append(outputs)
            logger.info(f"第 {current_step + 1} 步执行结果: {outputs}")
            gui_app.window.log_handler.emit_step(f"执行结果:\n{json.dumps(outputs, ensure_ascii=False, indent=2)}")
            
            if isinstance(outputs, dict) and outputs.get("task_completed", False):
                logger.success("任务执行完成")
                gui_app.window.log_handler.emit_step("任务执行完成")
                break
                
            current_step += 1
            
            if "POINT" in outputs:
                x, y = outputs["POINT"]
                logger.info(f"执行点击/滑动操作，归一化坐标: ({x}, {y})")
                if "to" in outputs:
                    if isinstance(outputs["to"], str):
                        logger.info(f"方向滑动: {outputs['to']}")
                    else:
                        to_x, to_y = outputs["to"]
                        logger.info(f"滑动到坐标: ({to_x}, {to_y})")
            elif "PRESS" in outputs:
                logger.info(f"执行按键操作: {outputs['PRESS']}")
            elif "TYPE" in outputs:
                logger.info(f"执行文本输入: {outputs['TYPE']}")
            elif "duration" in outputs:
                logger.info(f"等待 {outputs['duration']}ms")
            
            adb_controller.execute_action(outputs)
            
            time.sleep(1)
        
        if current_step >= max_steps:
            logger.warning("达到最大执行步数限制")
            gui_app.window.log_handler.emit_step("达到最大执行步数限制")
        
    except Exception as e:
        logger.error(f"程序执行出错: {str(e)}")
        gui_app.window.log_handler.emit_step(f"执行出错: {str(e)}")

if __name__ == "__main__":
    gui_app = start_gui()
    
    main_thread = threading.Thread(target=main, args=(gui_app,), daemon=True)
    main_thread.start()
    
    sys.exit(gui_app.run())