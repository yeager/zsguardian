from setuptools import setup, find_packages

setup(
    name="zscaler-guardian",
    version="1.0.0",
    description="ZSGuardian — Zero Trust Security Dashboard",
    author="Daniel Nylander",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    py_modules=["main", "dashboard", "mcp_client", "keychain", "tray"],
    python_requires=">=3.11",
    install_requires=[
        "PySide6>=6.6.0",
        "qasync>=0.27.1",
    ],
    entry_points={
        "console_scripts": [
            "zsguardian=main:main",
        ],
    },
)
