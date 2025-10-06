#!/usr/bin/env python3
"""
QBitcoin Wallet Launcher
========================

This script installs dependencies and launches the QBitcoin wallet application.
"""

import subprocess
import sys
import os
from pathlib import Path

def install_dependencies():
    """Install required dependencies"""
    print("Installing dependencies...")
    
    requirements_file = Path(__file__).parent / "requirements.txt"
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
        ])
        print("Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        return False

def launch_wallet():
    """Launch the wallet application"""
    print("Launching QBitcoin Wallet...")
    
    wallet_script = Path(__file__).parent / "qbitcoin_wallet.py"
    
    try:
        subprocess.run([sys.executable, str(wallet_script)])
    except Exception as e:
        print(f"Failed to launch wallet: {e}")

def main():
    """Main launcher function"""
    print("QBitcoin Wallet Launcher")
    print("========================")
    
    # Check if PyQt6 is installed
    try:
        import PyQt6
        print("PyQt6 is already installed.")
    except ImportError:
        print("PyQt6 not found. Installing dependencies...")
        if not install_dependencies():
            print("Failed to install dependencies. Please install manually:")
            print("pip install -r requirements.txt")
            return
    
    # Launch the wallet
    launch_wallet()

if __name__ == "__main__":
    main()
