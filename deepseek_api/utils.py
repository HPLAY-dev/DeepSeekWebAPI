"""
Utils.
"""

import json
import mimetypes
from typing import Optional, Dict, Any


def parse_completion(completion_object):
    """
    解析流式补全响应
    
    Args:
        completion_object: requests.Response对象 (stream=True)
    
    Returns:
        str: 响应消息ID
    
    Example:
        >>> response = client.completion(...)
        >>> message_id = parse_completion(response)
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
        except Exception as e:
            print(f"JSON解析错误: {e}")
            continue
            
        if last_line_str and last_line_str.startswith("event: "):
            event = last_line_str[7:]
            if event == 'ready':
                return_object = json_data.get('response_message_id', '')
        elif 'p' in json_data:
            if json_data['p'] == 'response/content':
                print(json_data['v'], end='')
            elif json_data['p'] == 'response/accumulated_token_usage':
                pass
            elif json_data['p'] == 'response/status':
                pass
            else:
                print(f"{json_data['p']}: {json_data['v']}")
        else:
            v_data = json_data.get('v', None)
            if isinstance(v_data, dict):
                for fragment in v_data.get('response', {}).get('fragments', []):
                    if fragment['type'] == "THINK":
                        print('\n[思考中...]\n')
                    elif fragment['type'] == "RESPONSE":
                        print(fragment.get('content', ''), end='')
            elif isinstance(v_data, list):
                for fragment in v_data:
                    if fragment['type'] == "RESPONSE":
                        print(fragment.get('content', ''), end='')
            elif isinstance(v_data, str):
                print(v_data, end='')
        last_line_str = line_str[:]
    print()
    return return_object


def guess_mime_type(filename: str) -> str:
    """
    猜测文件的MIME类型
    
    Args:
        filename: 文件名
    
    Returns:
        str: MIME类型
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'