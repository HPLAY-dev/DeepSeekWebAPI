from deepseek_api.api import DeepSeekAPI

api = DeepSeekAPI(token=open('token.txt', 'r', encoding="utf-8").read().strip())

session_id = api.create_chat()
prompt = """
请翻译这一本epub电子书至简体中文。Markdown格式。以该格式开始
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
api.completion(session_id, prompt, model="expert", files=[file_id])