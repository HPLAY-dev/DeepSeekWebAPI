#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSeek Desktop Client - Modern GUI with PySide6
"""

import sys
import json
import threading
import time
from datetime import datetime
from typing import Optional, Dict, List, Any

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QSize, QRect, QPoint,
    Property, QPropertyAnimation, QEasingCurve, Slot
)
from PySide6.QtGui import (
    QFont, QColor, QPalette, QIcon, QPixmap, QPainter,
    QTextCursor, QTextCharFormat, QSyntaxHighlighter,
    QFontDatabase, QAction, QKeySequence
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QTextEdit, QLineEdit, QScrollArea, QFrame, QMessageBox,
    QDialog, QFormLayout, QComboBox, QCheckBox, QFileDialog,
    QProgressBar, QStackedWidget, QToolButton, QMenu, QSizePolicy,
    QSpacerItem, QPlainTextEdit, QTabWidget, QGroupBox
)

# 第三方库
try:
    import markdown
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import HtmlFormatter
except ImportError:
    # 如果未安装，提供降级方案
    markdown = None
    HtmlFormatter = None

# 导入 DeepSeek API
from deepseek_api.api import DeepSeekAPI


# =============================================================================
# 辅助工具函数
# =============================================================================

def format_timestamp(ts: float) -> str:
    """将时间戳格式化为可读字符串"""
    if not ts:
        return ""
    dt = datetime.fromtimestamp(ts)
    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    elif (now - dt).days < 7:
        return dt.strftime("%m-%d %H:%M")
    else:
        return dt.strftime("%Y-%m-%d")


def markdown_to_html(text: str, enable_highlight: bool = True) -> str:
    """将 Markdown 转换为 HTML，支持代码高亮"""
    if markdown is None:
        return f"<pre>{text}</pre>"
    
    md = markdown.Markdown(extensions=['fenced_code', 'tables', 'nl2br'])
    html = md.convert(text)
    
    if enable_highlight and HtmlFormatter:
        import re
        def replace_code_block(match):
            code = match.group(2).strip()
            lang = match.group(1) or ''
            try:
                if lang:
                    lexer = get_lexer_by_name(lang, stripall=True)
                else:
                    lexer = guess_lexer(code)
            except:
                lexer = get_lexer_by_name('text', stripall=True)
            formatter = HtmlFormatter(style='monokai', noclasses=False)
            highlighted = highlight(code, lexer, formatter)
            return f'<div class="codehilite">{highlighted}</div>'
        
        html = re.sub(r'<pre><code class="language-(\w+)">(.*?)</code></pre>',
                     replace_code_block, html, flags=re.DOTALL)
        html = re.sub(r'<pre><code>(.*?)</code></pre>',
                     replace_code_block, html, flags=re.DOTALL)
    
    return html


# =============================================================================
# 登录对话框
# =============================================================================

class LoginDialog(QDialog):
    """登录对话框，支持手机/邮箱+密码或直接Token"""
    
    login_success = Signal(object, str)  # api, token
    login_failed = Signal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api: Optional[DeepSeekAPI] = None
        self.token: Optional[str] = None
        self.login_thread: Optional[threading.Thread] = None
        
        self.setWindowTitle("登录 DeepSeek")
        self.setFixedSize(400, 350)
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 标题
        title = QLabel("DeepSeek")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Arial", 24, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        # 选项卡切换登录方式
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        # 账号密码登录页
        self.account_widget = QWidget()
        account_layout = QFormLayout(self.account_widget)
        account_layout.setContentsMargins(20, 20, 20, 20)
        account_layout.setSpacing(15)

        self.account_type = QComboBox()
        self.account_type.addItems(["手机号", "邮箱"])
        self.account_type.currentIndexChanged.connect(self.on_account_type_changed)
        
        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("请输入手机号")
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("请输入密码")

        account_layout.addRow("账号类型:", self.account_type)
        account_layout.addRow("账号:", self.account_input)
        account_layout.addRow("密码:", self.password_input)

        self.tab_widget.addTab(self.account_widget, "账号密码登录")

        # Token登录页
        self.token_widget = QWidget()
        token_layout = QVBoxLayout(self.token_widget)
        token_layout.setContentsMargins(20, 20, 20, 20)
        token_label = QLabel("请输入已有的 Bearer Token:")
        self.token_input = QTextEdit()
        self.token_input.setPlaceholderText("粘贴 Token 到这里...")
        self.token_input.setMaximumHeight(100)
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_input)
        token_layout.addStretch()

        self.tab_widget.addTab(self.token_widget, "Token 登录")

        layout.addWidget(self.tab_widget)

        # 按钮
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("登录")
        self.login_btn.setDefault(True)
        self.cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.login_btn)
        layout.addLayout(btn_layout)

        # 进度条（隐藏）
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    def setup_connections(self):
        """设置信号连接"""
        self.login_btn.clicked.connect(self.do_login)
        self.cancel_btn.clicked.connect(self.reject)
        self.login_success.connect(self._on_login_success)
        self.login_failed.connect(self._on_login_failed)

    def on_account_type_changed(self, index):
        """账号类型切换时更新提示文本"""
        if index == 0:
            self.account_input.setPlaceholderText("请输入手机号")
        else:
            self.account_input.setPlaceholderText("请输入邮箱")

    def do_login(self):
        """执行登录"""
        self.login_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        def login_thread():
            try:
                if self.tab_widget.currentIndex() == 0:
                    # 账号密码登录
                    account = self.account_input.text().strip()
                    password = self.password_input.text().strip()
                    
                    if not account or not password:
                        self.login_failed.emit("账号和密码不能为空")
                        return
                    
                    if self.account_type.currentIndex() == 0:
                        mobile = account
                        email = ""
                    else:
                        mobile = ""
                        email = account
                    
                    api = DeepSeekAPI()
                    token = api.login({'mobile': mobile, 'email': email, 'password': password})
                    self.login_success.emit(api, token)
                else:
                    # Token登录
                    token = self.token_input.toPlainText().strip()
                    if not token:
                        self.login_failed.emit("Token不能为空")
                        return
                    
                    api = DeepSeekAPI(token=token)
                    # 验证token是否有效
                    try:
                        api.get_user_data()  # 会抛出异常如果无效
                        self.login_success.emit(api, token)
                    except Exception as e:
                        self.login_failed.emit(f"Token无效: {str(e)}")
                        
            except Exception as e:
                self.login_failed.emit(str(e))

        self.login_thread = threading.Thread(target=login_thread, daemon=True)
        self.login_thread.start()

    def _on_login_success(self, api, token):
        """登录成功回调（主线程）"""
        self.api = api
        self.token = token
        self.accept()

    def _on_login_failed(self, error_msg):
        """登录失败回调（主线程）"""
        QMessageBox.critical(self, "登录失败", f"错误信息：{error_msg}")
        self.login_btn.setEnabled(True)
        self.progress.setVisible(False)


# =============================================================================
# 消息气泡组件
# =============================================================================

class MessageBubble(QFrame):
    """聊天气泡，支持 Markdown 渲染"""

    def __init__(self, text: str = "", is_user: bool = True, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.full_text = text
        self.thinking_content = ""
        self.thinking_visible = False
        self.setup_ui()
        if text:
            self.set_text(text)

    def setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)

        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 思考内容折叠区域
        self.thinking_toggle = QPushButton("💭 思考过程")
        self.thinking_toggle.setFlat(True)
        self.thinking_toggle.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-weight: bold;
                padding: 4px;
                color: #888;
            }
            QPushButton:hover {
                color: #aaa;
            }
        """)
        self.thinking_toggle.clicked.connect(self.toggle_thinking)
        self.thinking_toggle.setVisible(False)

        self.thinking_text = QTextEdit()
        self.thinking_text.setReadOnly(True)
        self.thinking_text.setVisible(False)
        self.thinking_text.setMaximumHeight(200)
        self.thinking_text.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0.1);
                border: 1px solid #444;
                border-radius: 8px;
                padding: 8px;
                color: #aaa;
            }
        """)

        # 正文区域
        self.content_text = QTextEdit()
        self.content_text.setReadOnly(True)
        self.content_text.setFrameStyle(QFrame.NoFrame)
        self.content_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # 时间戳
        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignRight)
        self.time_label.setStyleSheet("color: gray; font-size: 10px;")

        layout.addWidget(self.thinking_toggle)
        layout.addWidget(self.thinking_text)
        layout.addWidget(self.content_text)
        layout.addWidget(self.time_label)

        # 根据发送者设置样式
        if self.is_user:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #007AFF;
                    border-radius: 18px;
                }
                QTextEdit {
                    color: white;
                    background: transparent;
                    border: none;
                }
            """)
        else:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #2C2C2E;
                    border-radius: 18px;
                }
                QTextEdit {
                    color: #ECECEE;
                    background: transparent;
                    border: none;
                }
            """)

    def set_text(self, text: str):
        """设置显示文本"""
        self.full_text = text
        # 检查是否包含思考标签
        if "【思考】" in text and "【/思考】" in text:
            parts = text.split("【思考】", 1)
            before = parts[0]
            rest = parts[1].split("【/思考】", 1)
            self.thinking_content = rest[0]
            display_text = before + (rest[1] if len(rest) > 1 else "")
            self.thinking_toggle.setVisible(True)
            self.thinking_text.setPlainText(self.thinking_content)
        else:
            display_text = text

        html = markdown_to_html(display_text)
        self.content_text.setHtml(html)

        # 自适应高度
        self.content_text.document().adjustSize()
        doc_height = self.content_text.document().size().height()
        self.content_text.setMinimumHeight(int(doc_height + 20))

    def append_text(self, delta: str):
        """流式追加文本"""
        self.set_text(self.full_text + delta)

    def set_thinking(self, thinking: str):
        """设置思考内容"""
        self.thinking_content = thinking
        self.thinking_text.setPlainText(thinking)
        self.thinking_toggle.setVisible(bool(thinking))

    def toggle_thinking(self):
        """切换思考内容显示"""
        self.thinking_visible = not self.thinking_visible
        self.thinking_text.setVisible(self.thinking_visible)
        self.thinking_toggle.setText("💭 思考过程 ▲" if self.thinking_visible else "💭 思考过程 ▼")

    def set_timestamp(self, ts: float):
        self.time_label.setText(format_timestamp(ts))


# =============================================================================
# 流式响应处理线程
# =============================================================================

class StreamWorker(QObject):
    """在子线程中处理流式响应"""

    text_chunk = Signal(str)
    thinking_chunk = Signal(str)
    status_update = Signal(str, dict)
    finished = Signal()
    error = Signal(str)

    def __init__(self, api: DeepSeekAPI, chat_session_id: str, prompt: str,
                 parent_message_id: Optional[int] = None,
                 thinking: bool = False, search: bool = False,
                 files: List[str] = None):
        super().__init__()
        self.api = api
        self.chat_session_id = chat_session_id
        self.prompt = prompt
        self.parent_message_id = parent_message_id
        self.thinking = thinking
        self.search = search
        self.files = files or []

    def run(self):
        try:
            response = self.api.completion(
                self.chat_session_id, self.prompt,
                parent_message_id=self.parent_message_id,
                thinking=self.thinking, search=self.search,
                files=self.files
            )
            self.parse_stream(response)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def parse_stream(self, response):
        last_event = None
        thinking_buffer = ""
        text_buffer = ""
        
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
                
            if line.startswith("event: "):
                last_event = line[7:]
            elif line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                except:
                    continue

                if last_event == "ready":
                    self.status_update.emit("ready", data)
                elif last_event == "update_session":
                    pass
                elif last_event == "close":
                    break
                else:
                    # 处理增量数据
                    if 'p' in data:
                        p = data['p']
                        v = data.get('v', '')
                        if p == 'response/content':
                            self.text_chunk.emit(str(v))
                        elif p == 'response/thinking':
                            self.thinking_chunk.emit(str(v))
                        elif p == 'response/status':
                            self.status_update.emit('status', v)
                    elif 'v' in data:
                        # 处理可能的其他格式
                        if isinstance(data['v'], str):
                            self.text_chunk.emit(data['v'])


# =============================================================================
# 主窗口
# =============================================================================

class MainWindow(QMainWindow):
    """DeepSeek 客户端主窗口"""

    def __init__(self, api: DeepSeekAPI):
        super().__init__()
        self.api = api
        self.current_chat_id: Optional[str] = None
        self.current_message_bubble: Optional[MessageBubble] = None
        self.parent_message_id: Optional[int] = None
        self.thinking_enabled = False
        self.search_enabled = False
        self.uploaded_files = []
        self.worker: Optional[StreamWorker] = None
        self.worker_thread: Optional[QThread] = None

        self.setWindowTitle("DeepSeek Client")
        self.setMinimumSize(1000, 700)
        self.setup_ui()
        self.load_chat_list()
        self.load_user_info()

    def setup_ui(self):
        # 中央分割器
        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        # 左侧边栏
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 新建对话按钮
        new_chat_btn = QPushButton("+ 新建对话")
        new_chat_btn.setFixedHeight(40)
        new_chat_btn.clicked.connect(self.create_new_chat)
        left_layout.addWidget(new_chat_btn)

        # 会话列表
        self.chat_list = QListWidget()
        self.chat_list.setFrameStyle(QFrame.NoFrame)
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        left_layout.addWidget(self.chat_list)

        # 底部用户信息
        user_frame = QFrame()
        user_frame.setFrameStyle(QFrame.StyledPanel)
        user_frame.setFixedHeight(60)
        user_layout = QHBoxLayout(user_frame)
        self.user_avatar = QLabel("👤")
        self.user_avatar.setFixedSize(40, 40)
        self.user_name_label = QLabel("加载中...")
        user_layout.addWidget(self.user_avatar)
        user_layout.addWidget(self.user_name_label)
        user_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedSize(30, 30)
        refresh_btn.clicked.connect(self.load_chat_list)
        user_layout.addWidget(refresh_btn)
        
        left_layout.addWidget(user_frame)

        splitter.addWidget(left_widget)

        # 右侧主聊天区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 消息显示区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameStyle(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignTop)
        self.message_layout.setSpacing(10)
        self.message_layout.setContentsMargins(20, 20, 20, 20)
        self.scroll_area.setWidget(self.message_container)

        right_layout.addWidget(self.scroll_area)

        # 输入区域
        input_frame = QFrame()
        input_frame.setFrameStyle(QFrame.StyledPanel)
        input_frame.setMinimumHeight(120)
        input_frame.setMaximumHeight(200)
        input_layout = QVBoxLayout(input_frame)

        # 工具栏
        toolbar = QHBoxLayout()
        
        self.think_btn = QPushButton("💭 思考")
        self.think_btn.setCheckable(True)
        self.think_btn.toggled.connect(lambda v: setattr(self, 'thinking_enabled', v))
        
        self.search_btn = QPushButton("🌐 搜索")
        self.search_btn.setCheckable(True)
        self.search_btn.toggled.connect(lambda v: setattr(self, 'search_enabled', v))
        
        self.upload_btn = QPushButton("📎 上传文件")
        self.upload_btn.clicked.connect(self.upload_files)
        
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self.stop_generation)
        self.stop_btn.setEnabled(False)
        
        toolbar.addWidget(self.think_btn)
        toolbar.addWidget(self.search_btn)
        toolbar.addWidget(self.upload_btn)
        toolbar.addWidget(self.stop_btn)
        toolbar.addStretch()
        
        # 文件标签
        self.file_label = QLabel("")
        self.file_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self.file_label)
        
        input_layout.addLayout(toolbar)

        # 文本输入框
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入消息... (Ctrl+Enter 发送)")
        self.input_edit.setMaximumHeight(100)
        input_layout.addWidget(self.input_edit)

        # 发送按钮
        send_layout = QHBoxLayout()
        send_layout.addStretch()
        self.send_btn = QPushButton("发送")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self.send_message)
        send_layout.addWidget(self.send_btn)
        input_layout.addLayout(send_layout)

        right_layout.addWidget(input_frame)
        splitter.addWidget(right_widget)

        splitter.setSizes([250, 750])
        
        # 重写输入框的键盘事件
        self.input_edit.keyPressEvent = self.input_key_press_event

    def input_key_press_event(self, event):
        """重载输入框键盘事件，实现 Ctrl+Enter 发送"""
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.ControlModifier:
            self.send_message()
        else:
            QTextEdit.keyPressEvent(self.input_edit, event)

    def load_chat_list(self):
        """加载会话列表"""
        try:
            sessions = self.api.get_chatlist()
            self.chat_list.clear()
            for session in sessions:
                title = session.get('title', '新对话')
                updated_at = session.get('updated_at', 0)
                display_text = f"{title}\n{format_timestamp(updated_at)}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, session['id'])
                self.chat_list.addItem(item)
        except Exception as e:
            QMessageBox.warning(self, "加载失败", f"无法加载会话列表：{e}")

    def load_user_info(self):
        """加载用户信息"""
        try:
            data = self.api.get_user_data()
            name = data.get('email') or data.get('mobile_number') or '用户'
            self.user_name_label.setText(name)
        except:
            self.user_name_label.setText("未登录")

    def create_new_chat(self):
        """创建新对话"""
        try:
            chat_id = self.api.create_chat()
            self.current_chat_id = chat_id
            self.parent_message_id = None
            self.clear_messages()
            self.load_chat_list()
            
            # 选中新创建的会话
            for i in range(self.chat_list.count()):
                item = self.chat_list.item(i)
                if item.data(Qt.UserRole) == chat_id:
                    self.chat_list.setCurrentItem(item)
                    break
        except Exception as e:
            QMessageBox.critical(self, "创建失败", str(e))

    def on_chat_selected(self, item: QListWidgetItem):
        """选中会话时加载历史消息"""
        chat_id = item.data(Qt.UserRole)
        self.current_chat_id = chat_id
        self.parent_message_id = None
        self.clear_messages()
        self.load_history_messages(chat_id)

    def load_history_messages(self, chat_id: str):
        """加载历史消息并显示"""
        try:
            history = self.api.get_history_messages(chat_id)
            messages = history.get('data', {}).get('biz_data', {}).get('messages', [])
            
            for msg in messages:
                role = msg.get('role')
                fragments = msg.get('fragments', [])
                content = ""
                thinking = ""
                
                for frag in fragments:
                    frag_type = frag.get('type')
                    frag_content = frag.get('content', '')
                    
                    if frag_type in ['RESPONSE', 'TEXT']:
                        content += frag_content
                    elif frag_type == 'THINK':
                        thinking += frag_content
                
                text = content
                if thinking:
                    text = f"【思考】{thinking}【/思考】{content}"
                    
                bubble = self.add_message(text, is_user=(role == 'USER'),
                                         timestamp=msg.get('inserted_at'))
                
                # 记录最后一条助手消息的ID作为parent_message_id
                if role == 'ASSISTANT':
                    self.parent_message_id = msg.get('message_id')
                    
            self.scroll_to_bottom()
        except Exception as e:
            QMessageBox.warning(self, "加载历史失败", str(e))

    def clear_messages(self):
        """清空消息区域"""
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_message(self, text: str, is_user: bool = True, timestamp: float = None):
        """添加一条消息气泡"""
        bubble = MessageBubble(text, is_user)
        if timestamp:
            bubble.set_timestamp(timestamp)
        self.message_layout.addWidget(bubble)
        return bubble

    def scroll_to_bottom(self):
        """滚动到底部"""
        QApplication.processEvents()
        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def send_message(self):
        """发送消息"""
        if not self.current_chat_id:
            QMessageBox.warning(self, "提示", "请先选择或创建一个对话")
            return

        prompt = self.input_edit.toPlainText().strip()
        if not prompt:
            return

        # 添加用户消息气泡
        self.add_message(prompt, is_user=True, timestamp=time.time())
        self.input_edit.clear()

        # 添加空的助手气泡，用于流式更新
        self.current_message_bubble = self.add_message("", is_user=False)

        # 禁用发送按钮，启用停止按钮
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 启动流式工作线程
        self.worker = StreamWorker(
            self.api, self.current_chat_id, prompt,
            parent_message_id=self.parent_message_id,
            thinking=self.thinking_enabled,
            search=self.search_enabled,
            files=self.uploaded_files
        )
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)

        # 连接信号
        self.worker.text_chunk.connect(self.on_text_chunk)
        self.worker.thinking_chunk.connect(self.on_thinking_chunk)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.finished.connect(self.on_stream_finished)
        self.worker.error.connect(self.on_stream_error)

        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()
        
        # 清空上传文件列表
        self.uploaded_files = []
        self.file_label.setText("")

    def on_text_chunk(self, text: str):
        """处理文本增量"""
        if self.current_message_bubble:
            self.current_message_bubble.append_text(text)
            self.scroll_to_bottom()

    def on_thinking_chunk(self, thinking: str):
        """处理思考增量"""
        if self.current_message_bubble:
            current = self.current_message_bubble.thinking_content
            self.current_message_bubble.set_thinking(current + thinking)

    def on_status_update(self, event: str, data: dict):
        """处理状态更新"""
        if event == "ready":
            msg_id = data.get('response_message_id')
            if msg_id:
                self.parent_message_id = msg_id

    def on_stream_finished(self):
        """流式响应完成"""
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if self.current_message_bubble:
            self.current_message_bubble.set_timestamp(time.time())
            self.current_message_bubble = None
            
        self.worker_thread.quit()
        self.worker_thread.wait()
        self.worker_thread = None
        self.worker = None
        
        # 刷新会话列表
        self.load_chat_list()

    def on_stream_error(self, error_msg: str):
        """流式响应出错"""
        QMessageBox.critical(self, "发送失败", error_msg)
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if self.current_message_bubble:
            self.current_message_bubble.set_text(f"[错误] {error_msg}")
            
        self.worker_thread.quit()
        self.worker_thread.wait()

    def stop_generation(self):
        """停止生成"""
        if self.worker and self.current_chat_id and self.parent_message_id:
            try:
                self.api.stop_completion(self.current_chat_id, self.parent_message_id)
            except:
                pass
        self.on_stream_finished()

    def upload_files(self):
        """上传文件"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if not files:
            return
            
        try:
            self.upload_btn.setEnabled(False)
            self.upload_btn.setText("上传中...")
            
            def upload_thread():
                try:
                    file_ids = self.api.upload_files(files, chat_session_id=self.current_chat_id)
                    self.uploaded_files = file_ids
                    self.file_label.setText(f"已上传 {len(file_ids)} 个文件")
                except Exception as e:
                    QMessageBox.critical(self, "上传失败", str(e))
                finally:
                    self.upload_btn.setEnabled(True)
                    self.upload_btn.setText("📎 上传文件")
            
            threading.Thread(target=upload_thread, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "上传失败", str(e))
            self.upload_btn.setEnabled(True)
            self.upload_btn.setText("📎 上传文件")


# =============================================================================
# 应用程序入口
# =============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 设置暗色主题
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.black)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    # 登录
    login_dlg = LoginDialog()
    if login_dlg.exec() != QDialog.Accepted:
        sys.exit(0)

    api = login_dlg.api
    window = MainWindow(api)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()