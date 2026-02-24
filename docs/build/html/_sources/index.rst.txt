DeepSeek API Document
=====================

This is the document of DeepSeek API for Python 3.

The API is a non-official wrapper of the web api of DeepSeek.

.. toctree::
   :maxdepth: 2
   :caption: Content:
   
   api

Quick Start
-----------

.. code-block:: python

   from deepseek_api import DeepSeekAPI
   
   # Initialize
   client = DeepSeekAPI()
   
   # Login
   token = client.login({
       "email": "your_email@example.com",
       "password": "your_password"
   })

Abilities
---------

* Login via mobile+password or email+password
* create & manage chat sessions
* streamed chat
* File upload
* PoW Solve

License
--------

This project uses GPL v3 license.