# app.py
from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
import os, sys
current_dir = os.path.dirname(os.path.abspath(__file__))
api_path = os.path.join(current_dir, "..", "deepseek_api")
sys.path.append(os.path.abspath(api_path))
# from deepseek_api.api import DeepSeekAPI, parse_completion
from api import DeepSeekAPI, parse_completion
import json
import uuid
import time
from functools import wraps

app = Flask(__name__)

# 存储用户会话和聊天实例
user_sessions = {}
app.secret_key = 'welcome-from-slime-soup'
TOKEN = open(current_dir+'\\..\\token.txt','r').read()

def get_api_instance():
    """获取或创建用户专属的DeepSeekAPI实例"""
    user_id = session.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'api': DeepSeekAPI(TOKEN, wasm_path=current_dir+'\\..\\deepseek_api\\sha3.wasm'),
            'chats': {},
            'current_chat': None
        }
    return user_sessions[user_id]['api']

def login_required(f):
    """检查是否已登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api = get_api_instance()
        if not api.is_logined():
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """渲染主页面"""
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    """登录接口"""
    data = request.json
    api = get_api_instance()
    
    try:
        account = {}
        if 'email' in data:
            account['email'] = data['email']
        if 'mobile' in data:
            account['mobile'] = data['mobile']
        if 'password' in data:
            account['password'] = data['password']
        if 'token' in data and data['token']:
            api.set_token(data['token'])
            return jsonify({'status': 'success', 'message': 'Token set successfully'})
        
        token = api.login(account)
        return jsonify({'status': 'success', 'token': token})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    """退出登录"""
    user_id = session.get('user_id')
    if user_id in user_sessions:
        del user_sessions[user_id]
    session.clear()
    return jsonify({'status': 'success'})

@app.route('/api/chats', methods=['GET'])
@login_required
def get_chats():
    """获取聊天列表"""
    api = get_api_instance()
    try:
        chats = api.get_chatlist()
        return jsonify({'status': 'success', 'chats': chats})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/chats', methods=['POST'])
@login_required
def create_chat():
    """创建新聊天"""
    api = get_api_instance()
    try:
        chat_id = api.create_chat()
        user_data = user_sessions[session['user_id']]
        user_data['current_chat'] = chat_id
        return jsonify({'status': 'success', 'chat_id': chat_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/chats/<chat_id>/history', methods=['GET'])
@login_required
def get_chat_history(chat_id):
    """获取聊天历史"""
    api = get_api_instance()
    try:
        print(f"Attempting to get history for chat_id: {chat_id}")  # 调试日志
        history_response = api.get_history_messages(chat_id)
        print(f"History response: {history_response}")  # 调试日志
        
        # 处理嵌套的响应格式
        formatted_messages = []
        
        # 检查是否是列表（多个消息对象）
        if isinstance(history_response, list):
            for message_obj in history_response:
                # 提取消息数据
                if isinstance(message_obj, dict):
                    # 尝试从不同的可能路径提取消息
                    message_data = None
                    
                    # 路径1: data.biz_data.chat_messages
                    if 'data' in message_obj and isinstance(message_obj['data'], dict):
                        biz_data = message_obj['data'].get('biz_data', {})
                        if isinstance(biz_data, dict):
                            chat_messages = biz_data.get('chat_messages', [])
                            if chat_messages:
                                # 如果找到了消息列表，添加到结果中
                                formatted_messages.extend(chat_messages)
                                continue
                    
                    # 路径2: 直接是消息对象
                    if 'content' in message_obj or 'role' in message_obj:
                        formatted_messages.append(message_obj)
        
        # 如果是字典，尝试直接提取
        elif isinstance(history_response, dict):
            if 'data' in history_response and isinstance(history_response['data'], dict):
                biz_data = history_response['data'].get('biz_data', {})
                if isinstance(biz_data, dict):
                    chat_messages = biz_data.get('chat_messages', [])
                    if chat_messages:
                        formatted_messages = chat_messages
        
        # 如果没有提取到消息，返回原始响应
        if not formatted_messages:
            formatted_messages = history_response
        
        print(f"Formatted messages: {formatted_messages}")  # 调试日志
        return jsonify({'status': 'success', 'history': formatted_messages})
        
    except Exception as e:
        print(f"Error getting chat history: {str(e)}")  # 错误日志
        import traceback
        traceback.print_exc()  # 打印完整堆栈
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/chats/<chat_id>/messages', methods=['POST'])
@login_required
def send_message(chat_id):
    """发送消息（流式响应）"""
    data = request.json
    message = data.get('message', '')
    parent_message_id = data.get('parent_message_id')
    thinking = data.get('thinking', False)
    search = data.get('search', False)
    files = data.get('files', [])
    
    api = get_api_instance()
    
    def generate():
        try:
            response = api.completion(
                chat_session_id=chat_id,
                chat_text=message,
                parent_message_id=parent_message_id,
                thinking=thinking,
                search=search,
                preempt=False,
                files=files
            )
            
            collected_content = []
            message_id = None
            
            for line in response.iter_lines():
                if not line:
                    continue
                    
                line_str = line.decode('utf-8')
                
                # 处理SSE格式
                if line_str.startswith('event: '):
                    event = line_str[7:]
                    yield f"event: {event}\n"
                elif line_str.startswith('data: '):
                    content = line_str[6:]
                    try:
                        json_data = json.loads(content)
                        
                        # 提取消息ID
                        if 'response_message_id' in json_data:
                            message_id = json_data['response_message_id']
                        
                        # 提取内容
                        if 'v' in json_data:
                            if isinstance(json_data['v'], str):
                                collected_content.append(json_data['v'])
                            elif isinstance(json_data['v'], dict):
                                fragments = json_data['v'].get('response', {}).get('fragments', [])
                                for fragment in fragments:
                                    if fragment.get('type') == 'RESPONSE':
                                        collected_content.append(fragment.get('content', ''))
                        
                        yield f"data: {json.dumps(json_data)}\n"
                    except json.JSONDecodeError:
                        yield f"data: {content}\n"
                else:
                    # 其他类型的数据
                    yield f"data: {line_str}\n"
            
            # 保存消息ID到会话
            if message_id:
                user_data = user_sessions.get(session['user_id'], {})
                if 'last_message_ids' not in user_data:
                    user_data['last_message_ids'] = {}
                user_data['last_message_ids'][chat_id] = message_id
            
            yield "event: done\ndata: {}\n\n"
            
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/api/chat/<chat_id>/message', methods=['POST'])
@login_required
def send_message_sync(chat_id):
    """发送消息（同步响应）"""
    data = request.json
    message = data.get('message', '')
    parent_message_id = data.get('parent_message_id')
    thinking = data.get('thinking', False)
    search = data.get('search', False)
    files = data.get('files', [])
    
    api = get_api_instance()
    
    try:
        response = api.completion(
            chat_session_id=chat_id,
            chat_text=message,
            parent_message_id=parent_message_id,
            thinking=thinking,
            search=search,
            preempt=False,
            files=files
        )
        
        # 收集完整响应
        full_response = ""
        message_id = None
        
        for line in response.iter_lines():
            if not line:
                continue
                
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                content = line_str[6:]
                try:
                    json_data = json.loads(content)
                    
                    if 'response_message_id' in json_data:
                        message_id = json_data['response_message_id']
                    
                    if 'v' in json_data:
                        if isinstance(json_data['v'], str):
                            full_response += json_data['v']
                        elif isinstance(json_data['v'], dict):
                            fragments = json_data['v'].get('response', {}).get('fragments', [])
                            for fragment in fragments:
                                if fragment.get('type') == 'RESPONSE':
                                    full_response += fragment.get('content', '')
                except:
                    pass
        
        return jsonify({
            'status': 'success',
            'message_id': message_id,
            'response': full_response
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/files/upload', methods=['POST'])
@login_required
def upload_file():
    """上传文件"""
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file provided'}), 400
    
    file = request.files['file']
    chat_id = request.form.get('chat_id')
    
    # 保存临时文件
    temp_path = f'/tmp/{uuid.uuid4()}_{file.filename}'
    file.save(temp_path)
    
    api = get_api_instance()
    
    try:
        file_ids = api.upload_files([temp_path], chat_session_id=chat_id)
        # 清理临时文件
        import os
        os.remove(temp_path)
        
        return jsonify({
            'status': 'success',
            'file_ids': file_ids
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """获取或更新设置"""
    user_data = user_sessions.get(session['user_id'], {})
    
    if request.method == 'POST':
        data = request.json
        user_data['settings'] = data.get('settings', {})
        return jsonify({'status': 'success'})
    
    return jsonify({
        'status': 'success',
        'settings': user_data.get('settings', {
            'thinking': False,
            'search': False
        })
    })

@app.route('/api/status', methods=['GET'])
def status():
    """获取登录状态"""
    api = get_api_instance()
    return jsonify({
        'status': 'success',
        'logged_in': api.is_logined()
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)