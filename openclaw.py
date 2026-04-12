# implements OpenAI style web api.
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import requests
import json
import uuid
from deepseek_api.api import DeepSeekAPI
import hashlib

app = FastAPI()
api = DeepSeekAPI(open('token.txt','r').read(), wasm_path='./deepseek_api/sha3.wasm')
chat_session = api.create_chat()
# 使用字典存储每个会话的最后消息ID
last_message_ids = {}
context_map = {}

# 你本地模型的真实地址
LOCAL_MODEL_URL = "http://localhost:8080/v1/generate"

@app.post("/chat/completions")
async def chat_proxy(request: Request):
    global context_map, last_message_ids
    
    openai_data = await request.json()
    messages = openai_data.get("messages", [])
    user_prompt = messages[-1]["content"]
    print(user_prompt)
    user_prompt = str(user_prompt).split('```\\n\\n',2)[-1]
    if user_prompt.endswith("'}]"):
        user_prompt = user_prompt[:-3]
        
        
    print('U: ', end="")
    print(user_prompt)

    # 识别是否为“起标题”请求（Continue 的典型行为）
    is_summary_request = "3-4 words" in user_prompt and len(messages) > 1

    # 为当前对话生成一个简单的 key（基于前文内容）
    # 或者简单起见，如果不是摘要请求，我们就正常迭代
    context_key = "default_session" 
    parent_id = context_map.get(context_key)

    if len(messages) <= 1:
        parent_id = None
        context_map = {} # 重置
        # 重置最后消息ID
        last_message_ids[context_key] = None

    # 获取当前会话的最后消息ID
    current_last_message_id = last_message_ids.get(context_key)

    def generate_openai_sse():
        nonlocal current_last_message_id  # 使用nonlocal声明修改外部变量
        current_last_line = ""
        new_id = None
        
        with api.completion(
            chat_session, 
            user_prompt, 
            parent_message_id=current_last_message_id  # 使用从字典获取的值
        ) as completion_object:
            
            for line in completion_object.iter_lines():
                if not line: continue
                line_str = line.decode('utf-8')
                
                if not line_str.startswith("data: "):
                    current_last_line = line_str
                    continue
                
                try:
                    json_data = json.loads(line_str[6:])
                    text_to_send = ""
                    # print(json_data)

                    # 1. 状态与 ID 提取逻辑
                    if current_last_line.startswith("event: "):
                        event = current_last_line[7:]
                        if event == 'ready':
                            # 关键点：捕获 response_message_id 用于下一轮
                            captured_id = json_data.get('response_message_id')
                            if captured_id:
                                # 更新字典中的值
                                last_message_ids[context_key] = captured_id
                                current_last_message_id = captured_id  # 同时更新当前变量
                        v_data = json_data.get('v', None)
                        # print(json_data)
                        if isinstance(v_data, dict):
                            print(1)
                            text_to_send = v_data.get('response', {}).get('content', '')
                    
                    # 2. 文本内容提取
                    elif json_data.get('p'):
                        continue
                    else:
                        v_data = json_data.get('v', None)
                        if isinstance(v_data, list):
                            for frag in v_data:
                                if frag.get('type') == "RESPONSE":
                                    text_to_send = frag.get('content', '')
                        elif isinstance(v_data, str):
                            text_to_send = v_data
                        elif isinstance(v_data, dict):
                            text_to_send = v_data.get('response', {}).get('content', '')
                    
                        if text_to_send:
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': text_to_send}}]}, ensure_ascii=False)}\n\n"
                        
                    current_last_line = line_str
                except: continue

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_openai_sse(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)