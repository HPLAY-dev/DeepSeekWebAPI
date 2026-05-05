from deepseek_api.api import DeepSeekAPI

api = DeepSeekAPI(token=open('token.txt', 'r', encoding="utf-8").read().strip())
TARGET_LANG = '简体中文'
session_id = api.create_chat()
prompt = f"""
请翻译这一本电子书至{TARGET_LANG}。Markdown格式。以该格式开始
'# 书名

# 第一部分（如果分部分，如果有文本内容而非数字，翻译原名称；如果有数字，更换为第n(一二三)部分）

## 第一章 (若有，如果有文本内容而非数字，翻译原名称；如果有数字，更换为第n(一二三)章)

Lorem ipsum......

正文'
- 段落之间两次换行
- 若一个角色有多个称呼，均换为原名称并翻译（Coop, Cooper统一翻译成Cooper）
- **务必完整翻译**
"""
epub_path = input("PATH (.epub): ").strip()
file_id = api.upload_file(epub_path, session_id)
api = DeepSeekAPI(token=open('token.txt',encoding='utf-8').read().strip())
with open('log', 'w', encoding='utf-8') as logfile:
    with open('translated.md', 'w', encoding='utf-8') as outputfile:
        r = api.completion(session_id, prompt, None, model="expert", thinking=False, files=[file_id], search=False, preempt=False)
        
        for line in r.iter_lines():
            incomplete = False
            if not line:
                continue
            line_str = line.decode('utf-8')
            try:
                if line_str.startswith('data: '):
                    data = line_str[6:]
                    jsondata = json.loads(data)
                    for v in jsondata.get('v', []):
                        if v.isinstance(dict):
                            key = v.get('p')
                            value = v.get('v')
                            if key == 'quasi_status' and value == 'INCOMPLETE':
                                incomplete = True
            except:
                pass
            
            v_data = json_data.get('v', None)
            if isinstance(v_data, str):
                # print(v_data,end='')
                outputfile.write(v_data,end='')
            elif isinstance(v_data, dict):
                a = v_data.get('response', {}).get('fragments', [None])[0]
                if type(a) == dict:
                    if a.get('content') is not None:
                        outputfile.write(a.get('content'),end='')
            # data: {"p":"response","o":"BATCH","v":[{"p":"accumulated_token_usage","v":371317},{"p":"quasi_status","v":"INCOMPLETE"}]}
            logfile.write(line_str+'\n')