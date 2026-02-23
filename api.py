from threading import Lock
from curl_cffi import requests
import json
import wasmtime
import ctypes
import struct
import base64

DEFAULT_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "DeepSeek/1.0.13 Android/35",
    "Accept": "application/json",
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "x-client-platform": "android",
    "x-client-version": "1.3.0-auto-resume",
    "x-client-locale": "zh_CN",
    "accept-charset": "UTF-8",
    "referer": "https://chat.deepseek.com/"
}

# URL_ENDPOINTS = [
#     '/api/v0/client/settings',
#     '/api/v0/users/create_guest_challenge',
#     '/api/v0/users/logout_all_sessions',
#     '/api/v0/users/set_birthday',
#     '/api/v0/client/wechat_js_sdk_signature',
#     '/api/v0/users/register',
#     '/api/v0/users/register_by_mobile',
#     '/api/v0/users/login_by_mobile_sms',
#     '/api/v0/users/create_sms_verification_code',
#     '/api/v0/users/create_email_verification_code',
#     '/api/v0/chat_session/delete_all',
#     '/api/v0/chat/create_pow_challenge', # IMPORTANT
#     '/api/v0/chat/completion',
#     '/api/v0/file/upload_file',
#     '/api/v0/client/span',
#     '/api/v0/file/fetch_files',
#     '/api/v0/chat_session/create', # 创建新对话
#     '/api/v0/chat/regenerate',
#     '/api/v0/chat/continue',
#     '/api/v0/chat/edit_message',
#     '/api/v0/chat/resume_stream',
#     '/api/v0/chat/stop_stream',
#     '/api/v0/chat_session/delete',
#     '/api/v0/chat/message_feedback',
#     '/api/v0/file/preview',
#     '/api/v0/users/settings',
#     '/api/v0/users/update_settings',
#     '/api/v0/chat/history_messages',
#     '/api/v0/chat_session/update_pinned',
#     '/api/v0/chat_session/fetch_page', # 获取对话列表
#     '/api/v0/chat_session/update_title',
#     '/api/v0/share/create',
#     '/api/v0/share/content',
#     '/api/v0/share/list',
#     '/api/v0/share/delete',
#     '/api/v0/share/fork',
#     '/api/v0/users/login' # 登录（获取token）
#     # https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback
# ]
URL_API_BASE = 'https://chat.deepseek.com'
URL_API_LOGIN = URL_API_BASE+'/api/v0/users/login'
URL_API_CREATE_POW = URL_API_BASE+'/api/v0/chat/create_pow_challenge'
URL_API_CREATE_CHAT = URL_API_BASE+'/api/v0/chat_session/create'
URL_API_COMPLETION = URL_API_BASE+'/api/v0/chat/completion'

class DeepSeekHashV1Solver:
    _instance = None
    _lock = Lock()

    def __new__(cls, wasm_path):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DeepSeekHashV1Solver, cls).__new__(cls)
                # 初始化引擎（全局只需一次）
                cls.engine = wasmtime.Engine()
                cls.module = wasmtime.Module.from_file(cls.engine, wasm_path)
                cls.linker = wasmtime.Linker(cls.engine)
            return cls._instance

    def solve(self, challenge: dict) -> int:
        challenge_str = challenge['challenge']
        salt = challenge['salt']
        # signature = challenge['signature']
        difficulty = challenge['difficulty']
        expire_at = challenge['expire_at']
        # 为每次计算创建独立的 Store，确保线程安全
        store = wasmtime.Store(self.engine)
        instance = self.linker.instantiate(store, self.module)
        exports = instance.exports(store)
        
        memory = exports["memory"]
        alloc = exports["__wbindgen_export_0"]
        add_to_stack = exports["__wbindgen_add_to_stack_pointer"]
        wasm_solve = exports["wasm_solve"]

        prefix = f"{salt}_{expire_at}_"
        
        def write_string(text: str):
            data = text.encode("utf-8")
            ptr = alloc(store, len(data), 1)
            # 获取内存指针
            base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
            ctypes.memmove(base_addr + ptr, data, len(data))
            return ptr, len(data)

        # 1. 分配返回值的栈空间
        retptr = add_to_stack(store, -16)
        
        # 2. 写入参数
        p_ch, l_ch = write_string(challenge_str)
        p_pre, l_pre = write_string(prefix)

        # 3. 求解
        wasm_solve(store, retptr, p_ch, l_ch, p_pre, l_pre, float(difficulty))

        # 4. 读取结果
        base_addr = ctypes.cast(memory.data_ptr(store), ctypes.c_void_p).value
        status = struct.unpack("<i", ctypes.string_at(base_addr + retptr, 4))[0]
        
        answer = None
        if status != 0:
            value_bytes = ctypes.string_at(base_addr + retptr + 8, 8)
            answer = int(struct.unpack("<d", value_bytes)[0])

        # 5. 清理栈（重要：防止内存泄漏）
        add_to_stack(store, 16)
        return answer

class DeepSeekAPI:
    def __init__(self, token=None, cookies={}):
        # self.token = token
        self.solver = DeepSeekHashV1Solver('sha3.wasm')
        self.cookies = cookies
        self.headers = DEFAULT_HEADERS.copy()
        if token is not None:
            self.headers['authorization'] = 'bearer '+token

    def is_logined(self):
        if 'authorization' in self.headers:
            return True
        else:
            return False

    def login(self, account: dict):
        # Parse Arguments
        email = account.get('email', '').strip()
        mobile = account.get('mobile', '').strip()
        password = account.get('password', '').strip()
        if not password or not (email or mobile):
            raise TypeError('0')
        
        # Login Main
        if email:
            payload = {
                "email": email,
                "password": password,
                "device_id": "deepseek_to_api",
                "os": "android",
            }
        else:
            payload = {
                "mobile": mobile,
                "area_code": None,
                "password": password,
                "device_id": "deepseek_to_api",
                "os": "android",
            }
        
        # try:
        #     response = requests.post(URL_API_LOGIN, headers=self.headers, json=payload)
        #     response.raise_for_status()
        #     login_response = response.json()
        #     new_token = login_response["data"]["biz_data"]["user"].get("token")
        #     self.headers['authorization'] = 'bearer '+new_token
        # except Exception as e:
        #     raise Exception('1')
        response = requests.post(URL_API_LOGIN, headers=self.headers, json=payload)
        response.raise_for_status()
        login_response = response.json()
        new_token = login_response["data"]["biz_data"]["user"].get("token")
        self.headers['authorization'] = 'bearer '+new_token
    
    def do_pow(self, target_path):
        json_data = {
            'target_path': target_path,
        }

        response = requests.post(
            URL_API_CREATE_POW,
            cookies=self.cookies,
            headers=self.headers,
            json=json_data,
        )
        challenge = response.json() \
            .get('data', {}) \
            .get('biz_data', {}) \
            .get('challenge')
        if challenge is None:
            return
        else:
            answer = self.solver.solve(challenge)
            pow_dict = {
                "algorithm": "DeepSeekHashV1",
                "challenge": challenge['challenge'],
                "salt": challenge['salt'],
                "answer": answer,
                "signature": challenge['signature'],
                "target_path": "/api/v0/chat/completion"
            }
            # 必须转成 JSON 并 Base64 编码
            return base64.b64encode(json.dumps(pow_dict, separators=(',', ':')).encode()).decode()
        
    def create_chat(self):
        params = {
            'lte_cursor.pinned': 'false',
        }
        response = requests.post(
            url=URL_API_CREATE_CHAT,
            headers=self.headers,
            cookies=self.cookies
        )
        return response.json().get('data', {}).get('biz_data', {}).get('id')
    
    def completion(self, chat_session_id, chat_text, parent_message_id=None, thinking=False, search=False, preempt=False, ref_file_ids=[]):
        json_data = {
            'chat_session_id': chat_session_id,
            'parent_message_id': parent_message_id,
            'prompt': chat_text,
            'ref_file_ids': [],
            'thinking_enabled': thinking,
            'search_enabled': search,
            'preempt': preempt,
        }
        headers_extend = {
            'x-ds-pow-response': self.do_pow(target_path='/api/v0/chat/completion')
        }
        open('123.json', 'w', encoding='utf-8').write(json.dumps(json_data, indent=4, ensure_ascii=False))
        
        headers = self.headers.copy()
        headers.update(headers_extend)

        response = requests.post('https://chat.deepseek.com/api/v0/chat/completion', stream=True, cookies=self.cookies, headers=headers, json=json_data)
        return response

def parse_completion(completion_object):
    # returns the message_id
    last_line_str = None
    return_object = None
    for line in completion_object.iter_lines():
        if not line:
            continue
        line_str = line.decode('utf-8')
        if not line_str.startswith("data: "):
            last_line_str = line_str[:]
            continue
    
        content = line_str[6:]
        try:
            json_data = json.loads(content)
        except Exception as E:
            print(E)
        if last_line_str.startswith("event: "):
            event = last_line_str[7:] # update_session close ready ...
            if event == 'update_session':
                pass
            elif event == 'close':
                pass
            elif event == 'ready':
                return_object = json_data.get('response_message_id', '')
        elif 'p' in json_data: # p can be: response/content
            if json_data['p'] == 'response/content':
                print(json_data['v'], end='')
            elif json_data['p'] == 'response/accumulated_token_usage':
                # print('\n\nAccumulated token usage: '+json_data['v'])
                pass
            elif json_data['p'] == 'response/status':
                pass
            else: # uncaught "P"
                print(json_data['p'], end=' ')
                print(json_data['v'])
        else: # append or what
            v_data = json_data.get('v', None)
            if isinstance(v_data, dict):
                for fragment in v_data.get('response', {}).get('fragments', []):
                    if fragment['type'] == "THINK": # equals to "id" == 2,
                        print('- THINKING ----------')
            elif isinstance(v_data, list):
                for fragment in v_data:
                    if fragment['type'] == "RESPONSE": # equals to "id" == 2,
                        print('- RESPONSE ----------')
                        print(fragment['content'],end='')
            elif isinstance(v_data, str):
                print(v_data,end='')
            else:
                raise Exception(6)
        last_line_str = line_str[:]
    print()
    return return_object

# -----------------------------------------
# 
# 1. 登录账号
# 
# -----------------------------------------
# # 登录
# api = DeepSeekAPI()
# api.login({'mobile': '手机号', 'password': '密码'})
# # 使用已有Token
# api = DeepSeekAPI('...................................')

# -----------------------------------------
# 
# 2. 主要逻辑 (这里以CLI方式呈现)
# 
# -----------------------------------------
keep_going = True
current_chat = ''
parent_message_id = None
enable_thinking = False
enable_search = False
while keep_going:
    r = input('>')
    x = r.split(' ', 2)
    if x[0] == '!n':
        current_chat = api.create_chat()
        print(current_chat)
    elif x[0] == '!thinking':
        enable_thinking = not enable_thinking
        print(enable_thinking)
    elif x[0] == '!search':
        enable_search = not enable_search
        print(enable_search)
    elif x[0] == '!chat':
        current_chat = x[1]
    elif x[0] == '!brk':
        print('set a breakpoint in your ide here.')
    else:
        if current_chat == '':
            print('Not defined current_chat, type "n" or "chat ID" to select a chat.')
            continue
        
        parent_message_id = parse_completion(api.completion(current_chat, r, parent_message_id, thinking=enable_thinking, search=enable_search, preempt=False))
        print(parent_message_id)