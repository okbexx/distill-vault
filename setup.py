from setuptools import setup, find_packages

setup(
    name="distill-vault",
    version="1.2.0",
    description="Graph-powered knowledge base runtime for Obsidian-compatible vaults",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Jarl",
    author_email="okbexx@gmail.com",
    url="https://github.com/okbexx/distill-vault",
    packages=find_packages(),
    package_data={"distill": ["web_static/*"]},
    install_requires=[
        "click>=8.0",
        "python-frontmatter>=1.0",
        "pyyaml>=6.0",
        "tomlkit>=0.12",
        "jsonschema>=4.23,<5",
        "mcp>=1.12.4,<2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-xdist>=3.0",
        ],
        "web": [
            # Web UI uses stdlib http.server — no extra deps
        ],
        "watch": [
            "watchdog>=3.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "distill=distill.cli:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Knowledge Management",
        "Topic :: Text Processing",
    ],
)
