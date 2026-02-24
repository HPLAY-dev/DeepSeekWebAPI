# UNCOMPLETED!!!!!!
import requests
import time

def get_wechat_authcode_by_qrcode(dealwith):
    # auth_code if success, None if unsuccess
    params = {
        'appid': 'wx932d4fdaf46d5611',
        'scope': 'snsapi_login',
        'redirect_uri': 'https://chat.deepseek.com/api/v0/users/oauth/wechat/callback',
        'state': '',
        'login_type': 'jssdk',
        'self_redirect': 'false',
        'styletype': '',
        'sizetype': '',
        'bgcolor': '',
        'rst': '',
        'ts': int(time.time() * 1000),
        'stylelite': '1',
        'fast_login': '0',
    }
    headers = {
        'Host': 'open.weixin.qq.com',
        # 模拟一个真实的 PC 浏览器
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://open.weixin.qq.com/',
        'Connection': 'keep-alive'
    }
    response = requests.get('https://open.weixin.qq.com/connect/qrconnect', params=params, headers=headers)
    # 这是一个非常不优雅的solution，TODO:换成bs4(虽然没什么必要......)
    for ln in response.text.split('\n'):
        if not 'var fordevtool = ' in ln:
            continue

        url = ln.split('var fordevtool = ')[-1] # "https://long.open.weixin.qq.com/connect/l/qrconnect?uuid=xxx" 包含引号！
        if url.startswith('"') and url.endswith('"'):
            url = url[1:-1]
            uuid = url.split('uuid=')[-1]
            break
        
    qrcode_url = 'https://open.weixin.qq.com/connect/qrcode/'+uuid
    dealwith(qrcode_url)

    # 开始轮询
    params = {
        'uuid': uuid,
    }
    # keep_going = False
    while True:
        response = requests.get('https://lp.open.weixin.qq.com/connect/l/qrconnect', params=params, headers=headers, timeout=15)
        resp_data = response.text.split(';')
        code = None
        for i in resp_data:
            j = i.split('=')
            if j[0] == 'window.wx_errcode':
                code = int(j[1])
            if j[0] == 'window.wx_code':
                auth_code = j[1][1:-1] # 去除单引号

        if code == 402:
            print('扫描成功，请确认登录')
        elif code == 404 or code == 408:
            pass
        elif code == 405: # 用户已确认
            if auth_code != "":
                print(f"确认成功，获取到 code: {auth_code}")
                return auth_code
        elif errcode == 403:
            return
        time.sleep(1)

def test(auth_code):
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'dnt': '1',
        'priority': 'u=0, i',
        'referer': 'https://open.weixin.qq.com/',
        'sec-ch-ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'cross-site',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
    }
    session = requests.Session()
    session.headers.update(headers)
    session.get("https://chat.deepseek.com/", headers=headers)

    params = {
        'code': auth_code,
        'state': '',
    }
    response = requests.get(
        'https://chat.deepseek.com/api/v0/users/oauth/wechat/callback',
        params=params,
        headers=headers,
        allow_redirects=True
    )
    cookies = session.cookies.get_dict()
    return session

# test('011fUmFa1ZsdfL0LP3Ia14c5S72fUmFy')