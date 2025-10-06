# QBitcoin Desktop Wallet

<div align="center">

![QBitcoin Logo](asessts/icon/icon(u).png)

**A Quantum-Resistant Desktop Wallet for QBitcoin**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey.svg)](https://github.com/Hamza1s34/Qdesktop_wallet)

[Website](https://qbitcoin.live) | [Download](https://github.com/Hamza1s34/Qdesktop_wallet/releases) | [Documentation](BUILD.md)

</div>

---

## 🌟 Features

- ✅ **Quantum-Resistant Security** - Uses Falcon-512 post-quantum signatures
- ✅ **Multi-Wallet Support** - Create and manage multiple wallets
- ✅ **Encrypted Storage** - AES-256 encryption for private keys
- ✅ **Transaction Management** - Send and receive QBitcoin with ease
- ✅ **QR Code Support** - Generate and scan wallet addresses
- ✅ **Real-time Balance** - Track your QBitcoin balance
- ✅ **Transaction History** - View all your transactions
- ✅ **Network Stats** - Monitor blockchain network status
- ✅ **Cross-Platform** - Available for Linux and Windows
- ✅ **Standalone Builds** - No Python or dependencies needed!

---

## 🖼️ Screenshots

### Main Wallet Interface
![Wallet Tab](docs/screenshots/wallet.png)

### Send Transaction
![Send Tab](docs/screenshots/send.png)

### Receive QBitcoin
![Receive Tab](docs/screenshots/receive.png)

---

## 📥 Download

### Pre-built Binaries (Recommended)

Download the latest standalone executables - **no installation or dependencies required**:

| Platform | Download | Size | Requirements |
|----------|----------|------|--------------|
| **Linux (AppImage)** | [qbitcoin_wallet_v1.0.0-x86_64.AppImage](https://github.com/Hamza1s34/Qdesktop_wallet/releases) | ~150MB | Any Linux distribution |
| **Windows (EXE)** | [qbitcoin_wallet_v1.0.0.exe](https://github.com/Hamza1s34/Qdesktop_wallet/releases) | ~100MB | Windows 10/11 (64-bit) |

#### Linux Quick Start
```bash
chmod +x qbitcoin_wallet_v1.0.0-x86_64.AppImage
./qbitcoin_wallet_v1.0.0-x86_64.AppImage
```

#### Windows Quick Start
Just double-click `qbitcoin_wallet_v1.0.0.exe`

---

## 🚀 Running from Source

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/Hamza1s34/Qdesktop_wallet.git
cd Qdesktop_wallet
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run the wallet**
```bash
python qbitcoin_wallet.py
```

---

## 🔧 Building from Source

### Linux AppImage

```bash
cd appimage
chmod +x build_appimage.sh
./build_appimage.sh
```

Output: `qbitcoin_wallet_v1.0.0-x86_64.AppImage` in project root

### Windows EXE

On Windows:
```bash
python build_windows.py
```

Output: `dist/qbitcoin_wallet_v1.0.0.exe`

For detailed build instructions, see [BUILD.md](BUILD.md)

---

## 📚 Documentation

- **[Build Instructions](BUILD.md)** - How to build AppImage and Windows EXE
- **[Distribution Guide](DISTRIBUTION.md)** - Standalone builds explained
- **[API Documentation](docs/API.md)** - QBitcoin API reference
- **[Security](docs/SECURITY.md)** - Security features and best practices

---

## 🛡️ Security Features

### Quantum-Resistant Cryptography
- **Falcon-512** - NIST-approved post-quantum signature scheme
- Protects against both classical and quantum computer attacks

### Wallet Security
- **AES-256 Encryption** - Military-grade encryption for private keys
- **Password Protection** - All wallets require strong passwords
- **Secure Key Storage** - Private keys never leave your device
- **Local Signing** - Transactions signed locally on your computer

### Network Security
- **gRPC Communication** - Encrypted communication with blockchain nodes
- **Address Validation** - Prevents sending to invalid addresses
- **Transaction Verification** - All transactions verified before broadcast

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         QBitcoin Desktop Wallet         │
├─────────────────────────────────────────┤
│  GUI Layer (PyQt6)                      │
│  ├── Wallet Management                  │
│  ├── Transaction Interface              │
│  └── Settings & Configuration           │
├─────────────────────────────────────────┤
│  Core Layer                             │
│  ├── Falcon-512 Signatures              │
│  ├── Wallet Encryption (AES-256)        │
│  ├── Key Management                     │
│  └── Transaction Building               │
├─────────────────────────────────────────┤
│  Network Layer                          │
│  ├── gRPC API Client                    │
│  ├── Node Communication                 │
│  └── Blockchain Queries                 │
└─────────────────────────────────────────┘
```

---

## 📋 Requirements

### Runtime (Standalone Builds)
- **Linux**: Any modern distribution with kernel 2.6.32+
- **Windows**: Windows 10 or 11 (64-bit)
- **No Python or libraries required!**

### Development
- Python 3.8+
- PyQt6 >= 6.5.0
- grpcio >= 1.60.0
- cryptography >= 41.0.0
- qrcode >= 7.4.2
- Pillow >= 10.0.0

See [requirements.txt](requirements.txt) for complete list.

---

## 🗂️ Project Structure

```
Qdesktop_wallet/
├── qbitcoin_wallet.py       # Main application
├── wallet_creator.py        # Wallet creation logic
├── wallet_encryption.py     # Encryption/decryption
├── wallet_storage.py        # Wallet storage management
├── api_client.py            # QBitcoin API client
├── falcon.py                # Falcon-512 implementation
├── generated/               # gRPC generated code
├── asessts/                 # Icons and images
├── appimage/                # Linux AppImage build
├── build_windows.py         # Windows build script
└── requirements.txt         # Python dependencies
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 🐛 Bug Reports

Found a bug? Please open an issue with:
- Description of the problem
- Steps to reproduce
- Expected behavior
- Screenshots (if applicable)
- System information (OS, version, etc.)

---

## 📞 Support

- **Website**: [https://qbitcoin.live](https://qbitcoin.live)
- **Issues**: [GitHub Issues](https://github.com/Hamza1s34/Qdesktop_wallet/issues)
- **Email**: support@qbitcoin.live

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

This software is provided "as is", without warranty of any kind. Always backup your wallet files and never share your private keys or passwords.

---

## 🙏 Acknowledgments

- **QBitcoin Team** - For the quantum-resistant blockchain
- **PyQt6** - For the excellent GUI framework
- **Falcon Team** - For the post-quantum cryptography
- **Community** - For testing and feedback

---

## 🔮 Future Roadmap

- [ ] Multi-signature wallet support
- [ ] Hardware wallet integration
- [ ] Mobile app (Android/iOS)
- [ ] Built-in exchange integration
- [ ] Advanced transaction features
- [ ] Staking interface
- [ ] Multi-language support

---

<div align="center">

**Made with ❤️ for the QBitcoin Community**

[⬆ Back to Top](#qbitcoin-desktop-wallet)

</div>
