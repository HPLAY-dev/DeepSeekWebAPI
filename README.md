# DeepSeek API
This API is based on the [official deepseek website](https://chat.deepseek.com), and can be used in Python 3 directly.
Most function of the web version of DeepSeek is implemented.

## Specialty
- **FREE!**
- Basic functions in the web version of DeepSeek
- Thread Safe

## Quick Start

### Install Dependencies

```bash
pip install requirements.txt -r
```

### Example
```python
from deepseek_api import DeepSeekAPI

# Instantiate API
client = DeepSeekAPI()

# Login
token = client.login({
    "email": "your_email@example.com",
    "password": "your_password"
})

# Create a new session
chat_id = client.create_chat()

# Send a message
response = client.completion(
    chat_session_id=chat_id,
    chat_text="Hello, who are you?"
)

# Deal with stream response
for line in response.iter_lines():
    if line:
        print(line.decode())
```

### Docs
See [docs/](docs/).

## Login
This API fakes requests from the web version of DeepSeek, so it only needs a **phone number** or **email** with **password** to login.

There should also be a way to implement login function of Wechat(scan QR) and SMS login(Hard, needs captcha) while I didn't figure it out yet.

## Usage
You can see the comments in the source code. It should be simple enough.

We also provides [a API.md in docs/](docs/API.md)

![License](https://img.shields.io/badge/License-GPL_v3-blue.svg)