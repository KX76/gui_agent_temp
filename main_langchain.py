import torch
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

from langchain_huggingface import HuggingFacePipeline
from langchain.prompts import PromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from PIL import Image
import json

# 1. 加载模型和分词器
model_path = "model/AgentCPM-GUI"
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    trust_remote_code=True,
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
    load_in_8bit=True
)

# 2. 创建 HuggingFace pipeline
pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_length=2048,
    temperature=0.1,
    top_p=0.3,
    repetition_penalty=1.1
)

# 3. 创建 LangChain 模型
llm = HuggingFacePipeline(pipeline=pipe)

# 4. 加载 Schema
ACTION_SCHEMA = json.load(open('eval/utils/schema/schema.json', encoding="utf-8"))
items = list(ACTION_SCHEMA.items())
insert_index = 3
items.insert(insert_index, ("required", ["thought"]))
ACTION_SCHEMA = dict(items)

# 5. 创建系统提示模板
SYSTEM_PROMPT = f'''# Role
你是一名熟悉安卓系统触屏GUI操作的智能体，将根据用户的问题，分析当前界面的GUI元素和布局，生成相应的操作。

# Task
针对用户问题，根据输入的当前屏幕截图，输出下一步的操作。

# Rule
- 以紧凑JSON格式输出
- 输出操作必须遵循Schema约束

# Schema
{json.dumps(ACTION_SCHEMA, indent=None, ensure_ascii=False, separators=(',', ':'))}'''

# 6. 创建提示模板
prompt = PromptTemplate(
    input_variables=["instruction", "image", "type"],
    template=f"{SYSTEM_PROMPT}\n<Question>{{instruction}}</Question>\n当前屏幕截图：{{image}}"
)

# 7. 创建 LangChain chain
chain = prompt.partial(type="gui_operation") | llm

# 8. 处理输入图片
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
    return img

# 9. 主函数
def main():
    instruction = "请点击屏幕上的'会员'按钮"
    image_path = "assets/test.jpeg"
    image = Image.open(image_path).convert("RGB")
    image = __resize__(image)
    
    # 10. 运行推理
    inputs = {
        "instruction": instruction,
        "image": image
    }
    result = chain.invoke(inputs)
    print(result)

if __name__ == "__main__":
    main() 