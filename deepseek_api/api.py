import mimetypes # 仅上传需要
from threading import Lock
# from curl_cffi import requests
import requests
import time
import json
import wasmtime
import ctypes
import struct
import base64
import os

# from wechat_login import get_wechat_authcode_by_qrcode, test
# from qrtool import qr_print
mimetypes.init()

DEFAULT_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-GB;q=0.6,zh-HK;q=0.5',
    'cache-control': 'no-cache',
    'content-type': 'application/json',
    'dnt': '1',
    'origin': 'https://chat.deepseek.com',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://chat.deepseek.com',
    'sec-ch-ua': '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0',
    'x-app-version': '20241129.1',
    'x-client-locale': 'zh_CN',
    'x-client-platform': 'web',
    'x-client-timezone-offset': '28800',
    'x-client-version': '1.8.0',
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
#     # https://open.weixin.qq.com/connect/qrconnect
# ]
URL_API_BASE = 'https://chat.deepseek.com'
URL_API_LOGIN = URL_API_BASE+'/api/v0/users/login'
URL_API_CREATE_POW = URL_API_BASE+'/api/v0/chat/create_pow_challenge'
URL_API_CREATE_CHAT = URL_API_BASE+'/api/v0/chat_session/create'
URL_API_COMPLETION = URL_API_BASE+'/api/v0/chat/completion'
URL_API_CHATLIST = URL_API_BASE+'/api/v0/chat_session/fetch_page'
URL_API_SETTINGS = URL_API_BASE+'/api/v0/client/settings'

class DeepSeekHashV1Solver:
    """
    A solver for DeepSeek's Proof of Work (PoW) hash challenges.
    
    This class uses a WASM module to solve PoW challenges required by the DeepSeek API.
    It is implemented as a thread-safe singleton to reuse the WASM engine across multiple
    solve operations.
    """
    _instance = None
    _lock = Lock()

    def __new__(cls, wasm_path):
        """
        Create or return the singleton instance of the solver.
        
        Args:
            wasm_path (str): Path to the WASM module file containing the solving algorithm.
            
        Returns:
            DeepSeekHashV1Solver: The singleton solver instance.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DeepSeekHashV1Solver, cls).__new__(cls)
                # 初始化引擎（全局只需一次）
                cls.engine = wasmtime.Engine()
                cls.module = wasmtime.Module.from_file(cls.engine, wasm_path)
                cls.linker = wasmtime.Linker(cls.engine)
            return cls._instance

    def solve(self, challenge: dict) -> int:
        """
        Solve a PoW challenge and return the answer.
        
        Args:
            challenge (dict): Challenge data containing:
                - challenge (str): The challenge string
                - salt (str): Salt value
                - difficulty (float): Difficulty level
                - expire_at (int): Expiration timestamp
                - signature (str): Challenge signature
                
        Returns:
            int: The solved answer value, or None if solving failed
        """
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
    """
    Main client for interacting with the DeepSeek API.
    
    This class provides methods for authentication, chat session management,
    message completion, file uploads, and other DeepSeek API functionalities.
    """
    def __init__(self, token=None, cookies={}, wasm_path='sha3.wasm'):
        """
        Initialize the DeepSeek API client.
        
        Args:
            token (str, optional): Existing authentication token.
            cookies (dict, optional): Cookie dictionary for session persistence.
        """
        self.solver = DeepSeekHashV1Solver(wasm_path)
        self.cookies = cookies
        self.headers = DEFAULT_HEADERS.copy()
        self.session = requests.Session()
        if token is not None:
            self.headers['authorization'] = 'bearer '+token
    
    def set_token(self, token):
        """
        Set or update the authentication token.
        
        Args:
            token (str): New authentication token to use for API requests.
        """
        self.headers['authorization'] = 'bearer '+token

    def is_logined(self):
        """
        Check if the client is currently authenticated.
        
        Returns:
            bool: True if authenticated, False otherwise.
        """
        if 'authorization' in self.headers:
            return True
        else:
            return False

    def login(self, account: dict):
        """
        Authenticate with DeepSeek using email/mobile and password.
        
        Args:
            account (dict): Account credentials containing either:
                - email (str): Email address
                - mobile (str): Mobile number
                - password (str): Account password
                
        Returns:
            str: Authentication token for subsequent API calls.
            
        Raises:
            TypeError: If neither email nor mobile is provided.
            requests.HTTPError: If the login request fails.
        """
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
        #     response = self.session.post(URL_API_LOGIN, headers=self.headers, json=payload)
        #     response.raise_for_status()
        #     login_response = response.json()
        #     new_token = login_response["data"]["biz_data"]["user"].get("token")
        #     self.headers['authorization'] = 'bearer '+new_token
        # except Exception as e:
        #     raise Exception('1')
        response = self.session.post(URL_API_LOGIN, headers=self.headers, json=payload)
        response.raise_for_status()
        login_response = response.json()
        new_token = login_response["data"]["biz_data"]["user"].get("token")
        self.headers['authorization'] = 'bearer '+new_token
        return new_token
    
    def do_pow(self, target_path):
        """
        Generate and solve a Proof of Work challenge for an API endpoint.
        
        Args:
            target_path (str): API path that requires PoW verification.
            
        Returns:
            str: Base64 encoded PoW response that can be used in the 
                 'x-ds-pow-response' header.
        """
        json_data = {
            'target_path': target_path,
        }

        response = self.session.post(
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
        """
        Create a new chat session.
        
        Returns:
            str: ID of the newly created chat session.
        """
        params = {
            'lte_cursor.pinned': 'false',
        }
        response = self.session.post(
            url=URL_API_CREATE_CHAT,
            headers=self.headers,
            cookies=self.cookies
        )
        raw = response.json()
        return raw.get('data', {}).get('biz_data', {}).get('chat_session', {}).get('id')
        
    def get_chatlist(self, update=False):
        """
        Retrieve the list of chat sessions.
        
        Args:
            update (bool): If True, include updated_at parameter for pagination.
            
        Returns:
            dict: List of chat sessions with their metadata:
                - id (str): Session ID
                - title (str): Session title
                - title_type (str): Title type (SYSTEM/USER)
                - pinned (bool): Whether session is pinned
                - updated_at (float): Last update timestamp
        """
        params = {
            'lte_cursor.pinned': 'false',
        }
        if update: params['lte_cursor.updated_at'] = str(time.time())
        response = self.session.get(
            url=URL_API_CHATLIST,
            headers=self.headers,
            cookies=self.cookies
        )
        # print(response.text)
        return response.json().get('data', {}).get('biz_data', {}).get('chat_sessions')
    
    def get_history_messages(self, chat_session_id):
        """
        Retrieve message history for a specific chat session.
        
        Args:
            chat_session_id (str): ID of the chat session.
            
        Returns:
            dict: Message history containing:
                - message_id (int): Message identifier
                - role (str): USER or ASSISTANT
                - fragments (list): Message content fragments
                - files (list): Attached files
                - status (str): Message status
                - inserted_at (float): Timestamp
        """
        params = {
            'chat_session_id': chat_session_id,
        }
        response = self.session.get(
            URL_API_BASE+'/api/v0/chat/history_messages',
            params=params,
            headers=self.headers,
            cookies=self.cookies
        )
        return response.json()

    def get_models(self):
        """
        Retrieve models.
            
        Returns:
            list: Models List, every element is dict. See deepseek_api/responds/query_models.json
        """
        params = {
            'scope': 'model',
        }
        response = self.session.get(
            URL_API_SETTINGS,
            params=params,
            headers=self.headers,
            cookies=self.cookies
        ).json().get('data', {}).get('biz_data', {})

        
    def completion(self, chat_session_id, chat_text, parent_message_id=None, thinking=False, search=False, preempt=False, model='default', files=[]):
        """
        Send a message and get a streaming completion response.
        
        Args:
            chat_session_id (str): Target chat session ID.
            chat_text (str): Message text to send.
            parent_message_id (int, optional): Parent message ID for context.
            thinking (bool): Enable thinking mode.
            search (bool): Enable web search capability.
            preempt (bool): Enable preemptive response. (cannot be True in web version.)
            files (list): List of uploaded file IDs to attach.
            models (str): Using which model to respond. (recently added. ['default', 'expert'] at 2026/4/12)
            
        Returns:
            requests.Response: Streaming response object containing the AI's reply.
        """
        json_data = {
            'chat_session_id': chat_session_id,
            'parent_message_id': parent_message_id,
            'prompt': chat_text,
            'ref_file_ids': files,
            'thinking_enabled': thinking,
            'search_enabled': search,
            'preempt': preempt,
        }
        headers_extend = {
            'x-ds-pow-response': self.do_pow(target_path='/api/v0/chat/completion')
        }
        # open('123.json', 'w', encoding='utf-8').write(json.dumps(json_data, indent=4, ensure_ascii=False))
        
        headers = self.headers.copy()
        headers.update(headers_extend)

        response = self.session.post(URL_API_BASE+'/api/v0/chat/completion', stream=True, cookies=self.cookies, headers=headers, json=json_data)
        return response

    def continue_completion(self, chat_session_id, message_id, fallback_to_resume=True):
        """
        Continue a stopped completion request.
        
        Args:
            chat_session_id (str): Chat session ID of the message.
            message_id (int): The message to continue.
            fallback_to_resume (bool): unknown.
            
        Returns:
            requests.Response: Streaming response object containing the AI's reply.
        """
        json_data = {
            'chat_session_id': chat_session_id,
            'message_id': message_id,
            'fallback_to_resume': fallback_to_resume,
        }

        response = self.session.post(URL_API_BASE+'/api/v0/chat/continue', cookies=self.cookies, headers=self.headers, json=json_data, stream=True)
        return response

    def stop_completion(self, chat_session_id, message_id):
        """
        Stop a stopped completion request.
        
        Args:
            chat_session_id (str): Chat session ID of the message.
            message_id (int): The message to stop.
            
        Returns:
            requests.Response: Streaming response object. (Possibly no usable data)
        """
        json_data = {
            'chat_session_id': chat_session_id,
            'message_id': message_id,
        }

        response = self.session.post(URL_API_BASE+'/api/v0/chat/stop_stream', cookies=self.cookies, headers=self.headers, json=json_data)
        return response

    def get_user_data(self):
        """
        Stop a stopped completion request.
        
        Args:
            chat_session_id (str): Chat session ID of the message.
            message_id (int): The message to stop.
            
        Returns:
            dict: data of the user(in biz_data)
        
        Examples:
            >>> api = DeepSeekAPI('******************...')
            >>> print(api.get_user_data)
            {
                "code": 0,
                "msg": "",
                "data": {
                    "biz_code": 0,
                    "biz_msg": "",
                    "biz_data": {
                        "id": "********-****-****-****-************", (each * is a char from 0-9 or a-f(lower))
                        "token": "****************************************************************",
                        "email": "",
                        "mobile_number": "abc******jk", (abcjk is number(0-9), * is the symbol itself)
                        "area_code": "+86",
                        "status": 0,
                        "id_profile": null,
                        "id_profiles": [],
                        "chat": {
                            "is_muted": 0,
                            "mute_until": null
                        },
                        "has_legacy_chat_history": false,
                        "need_birthday": false
                    }
                }
            }
        """

        response = self.session.get(URL_API_BASE+'/api/v0/users/current', cookies=self.cookies, headers=self.headers)
        return response.json().get('data',{}).get('biz_data',{})

    def set_chat_session_title(self, chat_session_id, new_title):
        """
        Set new title for a chat session.
        
        Args:
            chat_session_id (str): Chat session ID of the message.
            new_title (str): The title to change.
            
        Returns:
            dict: data
        
        Examples:
            >>> api = DeepSeekAPI('******************...')
            >>> print(api.set_chat_session_title('...', 'Test123'))
            {
                "code": 0,
                "msg": "",
                "data": {
                    "biz_code": 0,
                    "biz_msg": "",
                    "biz_data": {
                        "chat_session_updated_at": 1771992655.738931, (timestamp)
                        "title": "Test123"
                    }
                }
            }
        """
        json_data = {
            'chat_session_id': chat_session_id,
            'title': new_title,
        }

        response = self.session.post(
            'https://chat.deepseek.com/api/v0/chat_session/update_title',
            cookies=self.cookies,
            headers=self.headers,
            json=self.json_data,
        )
        return response.json()

    def upload_file(self, file: str, chat_session_id: str=None, dealwith=None) -> list:
        """
        Upload files to the DeepSeek server.
        
        Args:
            file (str): File path to upload.
            chat_session_id (str, optional): Chat session ID for Referer header.
            dealwith (callable, optional): Callback function for status updates.
            
        Returns:
            str: ID of uploaded file that can be used in completions.
        """
        # 发送 upload_file 请求
        headers = self.headers.copy()
        del headers['content-type']
        if chat_session_id is not None:
            headers['Referer'] = 'https://chat.deepseek.com/a/chat/s/'+chat_session_id
        else:
            headers['Referer'] = 'https://chat.deepseek.com'
            
        headers_extend = {
            'x-ds-pow-response': self.do_pow(target_path='/api/v0/file/upload_file')
        }
        headers.update(headers_extend)

        # 遍历上传的文件，发送uplaod_file请求
        file_ids = []
        mime_type, _ = mimetypes.guess_type(os.path.basename(file))
        files = {
            'file': (file, open(file, 'rb'), mime_type),
        }
        response = self.session.post(URL_API_BASE+'/api/v0/file/upload_file', cookies=self.cookies, headers=headers, files=files)
        jsondata = response.json()
        file_id = jsondata["data"]["biz_data"]["id"]
        file_ids.append(file_id)

        # 开始轮询
        while True:
            params = {
                'file_ids': file_id,
            }
            response = self.session.get(URL_API_BASE+'/api/v0/file/fetch_files', cookies=self.cookies, headers=headers, params=params)
            data = response.json()["data"]

            if data['biz_code'] != 0:
                raise Exception(data['biz_msg'])
            elif data["biz_data"]["files"][0]['status'] == 'SUCCESS':
                # print('SUCCESS: '+file_status['file_name'])
                return file_id

def parse_completion(completion_object):
    """
    Parse a streaming completion response and print the content.
    
    This is a utility function for testing and debugging purposes.
    
    Args:
        completion_object (requests.Response): Streaming response from completion().
        
    Returns:
        str: Response message ID if available.
        
    Note:
        This function prints the response content in real-time and is
        intended for testing only, not as part of the main API.
    """
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
                continue
            else: # uncaught "P"
                pass
        v_data = json_data.get('v', None)
        if isinstance(v_data, str):
            print(v_data,end='')
        elif isinstance(v_data, dict):
            a = v_data.get('response', {}).get('fragments', [None])[0]
            if type(a) == dict:
                if a.get('content') is not None:
                    print(a.get('content'), end='')
        last_line_str = line_str[:]
    print()
    return return_object


if __name__ == '__main__':
    # -----------------------------------------
    # 
    # 1. 登录账号
    # 
    # -----------------------------------------
    # # 登录
    api = DeepSeekAPI()
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
    cl = None

    token = input('token(blank if login): ')
    if token == '':
        mobile = input('mobile(blank if using mail): ')
        mail = input('mail(blank if using mobile): ')
        passwd = input('passwd: ')
        print(api.login({'email':mail, 'password':passwd, 'mobile':mobile}))
    else:
        api.set_token(token)
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
        elif x[0] == '!cl':
            cl = api.get_chatlist()
            print(cl)
        elif x[0] == '!u':
            cl = api.upload_files(x[1])
            print(cl)
        elif x[0] == '!x':
            sys.exit()
        else:
            if current_chat == '':
                print('Not defined current_chat, type "!n" or "!chat ID" to select a chat.')
                continue
            
            parse_completion(api.completion(current_chat, r, parent_message_id, thinking=enable_thinking, files=[] if cl is None else [cl], search=enable_search, preempt=False))
            