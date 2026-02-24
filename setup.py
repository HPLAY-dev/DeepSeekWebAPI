from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="deepseek-api",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Unofficial DeepSeek Web API Python Wrapper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/deepseek-api",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests",
        "wasmtime",
    ],
    include_package_data=True,
    package_data={
        "deepseek_api": ["sha3.wasm"],
    },
)