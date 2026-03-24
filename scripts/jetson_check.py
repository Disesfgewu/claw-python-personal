#!/usr/bin/env python3
"""
Jetson Orin Nano Super diagnostic and optimization script.
"""
import subprocess


def check_jetpack_version():
    """Check JetPack version."""
    try:
        result = subprocess.run(['cat', '/etc/nv_tegra_release'], capture_output=True, text=True)
        print("=== JetPack Version ===")
        print(result.stdout)
    except Exception as e:
        print(f"Could not determine JetPack version: {e}")


def check_memory():
    """Check memory usage."""
    print("\n=== Memory Status ===")
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            for line in lines[:10]:
                print(line.strip())
    except Exception as e:
        print(f"Could not read memory info: {e}")


def check_disk():
    """Check disk usage."""
    print("\n=== Disk Usage ===")
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"Could not check disk: {e}")


def check_docker():
    """Check Docker installation and status."""
    print("\n=== Docker Status ===")
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        print("Docker available: OK")
        print(f"Running containers: {len(result.stdout.split(chr(10))) - 2}")
    except Exception as e:
        print(f"Docker status: ERROR ({e})")


def check_python_dependencies():
    """Check critical Python dependencies."""
    print("\n=== Python Dependencies ===")
    required = ['fastapi', 'uvicorn', 'pydantic', 'sqlalchemy', 'yfinance', 'ta', 'mplfinance']
    for pkg in required:
        try:
            __import__(pkg)
            print(f"OK {pkg}")
        except ImportError:
            print(f"MISSING {pkg}")


if __name__ == '__main__':
    check_jetpack_version()
    check_memory()
    check_disk()
    check_docker()
    check_python_dependencies()
    print("\n=== Diagnostics Complete ===")
