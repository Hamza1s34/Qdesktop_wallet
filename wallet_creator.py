"""
Wallet creator module for Qbitcoin using Falcon 512 post-quantum signature algorithm.
This module provides functionality for generating wallets with key pairs and addresses.
"""


import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import os
import hashlib
import json
import time
import base64
from pathlib import Path
from typing import Dict, Tuple, Any, Optional 


# Import the Falcon 512 module from pqcrypto
from pqcrypto.sign.falcon_512 import (
    generate_keypair,
    sign,
    verify,
    PUBLIC_KEY_SIZE,
    SECRET_KEY_SIZE,
    SIGNATURE_SIZE
)

WALLET_DIR = Path(__file__).parent / "wallets"
class WalletCreator:
    """
    Wallet creation and management class using Falcon 512 post-quantum signatures.
    Provides methods for generating key pairs, creating addresses, and managing wallets.
    """
    
    DEFAULT_WALLET_DIR = WALLET_DIR
    @staticmethod
    def generate_seed() -> bytes:
        """Generate a random seed for key generation"""
        return os.urandom(32)  # 256-bit seed
    
    @staticmethod
    def create_keypair() -> Tuple[bytes, bytes]:
        """
        Generate a new Falcon 512 key pair for a wallet
        
        Returns:
            Tuple[bytes, bytes]: A tuple containing the private and public keys as bytes
        """
        # Generate the keypair using pqcrypto library
        key1, key2 = generate_keypair()
        
        # Check key sizes to determine which is which
        # In Falcon 512, SECRET_KEY_SIZE is 1281 and PUBLIC_KEY_SIZE is 897
        if len(key1) == SECRET_KEY_SIZE and len(key2) == PUBLIC_KEY_SIZE:
            # Keys are in correct order (secret_key, public_key)
            return key1, key2
        elif len(key1) == PUBLIC_KEY_SIZE and len(key2) == SECRET_KEY_SIZE:
            # Keys are in reverse order (public_key, secret_key)
            return key2, key1
        else:
            # If sizes don't match expected values, raise an error
            raise ValueError(f"Invalid key sizes: {len(key1)}, {len(key2)}. Expected: {SECRET_KEY_SIZE}, {PUBLIC_KEY_SIZE}")
    
    @staticmethod
    def generate_address(public_key: bytes) -> str:
        """
        Generate a wallet address from a public key using the QBitcoin address format
        
        Flow:
        Public Key (897 bytes) 
            ↓ 
        SHA-256 Hash (32 bytes)
            ↓
        RIPEMD-160 Hash (20 bytes)
            ↓
        Add Address Type Prefix (0x01) → 21 bytes total
            ↓
        Calculate Checksum (double SHA-256, first 4 bytes)
            ↓
        Final Binary Address (25 bytes total)
            ↓
        Convert to Hex and add 'Q' prefix
        
        Args:
            public_key (bytes): The public key to generate an address from
            
        Returns:
            str: Hex encoded wallet address with Q prefix
        """
        # Step 1: Perform SHA-256 hash on public key
        sha256_hash = hashlib.sha256(public_key).digest()
        
        # Step 2: Perform RIPEMD-160 hash on the SHA-256 hash
        # Try multiple fallback methods to ensure compatibility
        ripemd160_hash = None
        last_error = None
        
        # Fallback 1: Try standard hashlib
        try:
            ripemd160_hash = hashlib.new('ripemd160')
        except ValueError as e:
            last_error = f"hashlib failed: {e}"
        
        # Fallback 2: Try pycryptodome if hashlib failed
        if ripemd160_hash is None:
            try:
                from Crypto.Hash import RIPEMD160
                
                class Ripemd160Wrapper:
                    def __init__(self):
                        self._hash = RIPEMD160.new()
                    
                    def update(self, data):
                        self._hash.update(data)
                    
                    def digest(self):
                        return self._hash.digest()
                    
                    def hexdigest(self):
                        return self._hash.hexdigest()
                
                ripemd160_hash = Ripemd160Wrapper()
            except ImportError as e:
                last_error = f"pycryptodome failed: {e}"
        
        # Fallback 3: Try compatibility module if both failed
        if ripemd160_hash is None:
            try:
                from koyeb_crypto_compat import get_ripemd160_hash
                ripemd160_hash = get_ripemd160_hash()
            except (ImportError, Exception) as e:
                last_error = f"compatibility module failed: {e}"
        
        # If all fallbacks failed, raise error
        if ripemd160_hash is None:
            raise RuntimeError(f"ripemd160 hash not supported in this environment. Last error: {last_error}")
            
        ripemd160_hash.update(sha256_hash)
        hash160 = ripemd160_hash.digest()  # 20 bytes
        
        # Step 3: Add address type prefix (0x01 for QBitcoin addresses)
        versioned_hash = b'\x01' + hash160  # 21 bytes total
        
        # Step 4: Calculate checksum (double SHA-256, first 4 bytes)
        checksum = hashlib.sha256(hashlib.sha256(versioned_hash).digest()).digest()[:4]
        
        # Step 5: Combine versioned hash and checksum
        binary_address = versioned_hash + checksum  # 25 bytes total
        
        # Step 6: Convert to hex and add Q prefix
        return "Q" + binary_address.hex()
    
    @classmethod
    def create_wallet(cls, wallet_name: str = None) -> Dict[str, Any]:
        """
        Create a new wallet with a Falcon 512 key pair and address
        
        Args:
            wallet_name (str, optional): Name of the wallet. If None, uses a timestamp.
            
        Returns:
            Dict[str, Any]: Wallet information including keys and address
        """
        # Generate key pair
        # secret_key should be 1281 bytes, public_key should be 897 bytes
        secret_key, public_key = cls.create_keypair()
        
        # Validate key sizes
        if len(secret_key) != SECRET_KEY_SIZE:
            raise ValueError(f"Secret key size mismatch: {len(secret_key)} != {SECRET_KEY_SIZE}")
        if len(public_key) != PUBLIC_KEY_SIZE:
            raise ValueError(f"Public key size mismatch: {len(public_key)} != {PUBLIC_KEY_SIZE}")
        
        # Generate address from public key
        address = cls.generate_address(public_key)
        
        # Create wallet name if not provided - use only 4 digits
        if wallet_name is None:
            import random
            wallet_id = random.randint(1000, 9999)  # Generate 4-digit number
            wallet_name = f"wallet_{wallet_id}"
        
        # Create wallet data structure
        wallet_data = {
            "name": wallet_name,
            "created_at": time.time(),
            "address": address,
            "public_key": public_key.hex(),
            "public_key_size": len(public_key),
            "private_key": secret_key.hex(),
            "private_key_size": len(secret_key),
            "algorithm": "falcon-512"
        }
        
        return wallet_data
    
    @classmethod
    def save_wallet(cls, wallet_data: Dict[str, Any], password: str, 
                    directory: Optional[Path] = None) -> Path:
        """
        Encrypt and save a wallet to disk
        
        Args:
            wallet_data (Dict[str, Any]): Wallet data to save
            password (str): Password to encrypt the wallet
            directory (Path, optional): Directory to save wallet. Defaults to DEFAULT_WALLET_DIR.
            
        Returns:
            Path: Path to the saved wallet file
        """
        # Create wallet directory if it doesn't exist
        if directory is None:
            directory = cls.DEFAULT_WALLET_DIR
        
        directory.mkdir(parents=True, exist_ok=True)
        
        # Encrypt sensitive wallet data
        salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        
        # TODO: Implement proper encryption with the derived key
        # For now, we'll just store the salt with the wallet data
        encrypted_wallet = wallet_data.copy()
        encrypted_wallet["salt"] = salt.hex()
        
        # Create wallet file
        wallet_file = directory / f"{wallet_data['name']}.wallet"
        with open(wallet_file, 'w') as f:
            json.dump(encrypted_wallet, f, indent=2)
        
        return wallet_file
    
    @classmethod
    def load_wallet(cls, wallet_path: Path, password: str) -> Dict[str, Any]:
        """
        Load and decrypt a wallet from disk
        
        Args:
            wallet_path (Path): Path to the wallet file
            password (str): Password to decrypt the wallet
            
        Returns:
            Dict[str, Any]: Loaded wallet data
        """
        # Load encrypted wallet data
        with open(wallet_path, 'r') as f:
            encrypted_wallet = json.load(f)
        
        # TODO: Implement proper decryption using the password and salt
        # For now, just return the wallet without decryption
        
        return encrypted_wallet
    
    @staticmethod
    def sign_message(message: bytes, secret_key: bytes) -> bytes:
        """
        Sign a message using the wallet's private key
        
        Args:
            message (bytes): Message to sign
            secret_key (bytes): Private key for signing
            
        Returns:
            bytes: Signature
        """
        # Ensure the secret key is the correct length
        if len(secret_key) != SECRET_KEY_SIZE:
            raise ValueError(f"Private key must be exactly {SECRET_KEY_SIZE} bytes, got {len(secret_key)}")
            
        return sign(message, secret_key)
    
    @staticmethod
    def verify_signature(message: bytes, signature: bytes, 
                         public_key: bytes) -> bool:
        """
        Verify a signature using the wallet's public key
        
        Args:
            message (bytes): Original message
            signature (bytes): Signature to verify
            public_key (bytes): Public key for verification
            
        Returns:
            bool: True if signature is valid, False otherwise
        """
        # Ensure the public key is the correct length
        if len(public_key) != PUBLIC_KEY_SIZE:
            raise ValueError(f"Public key must be exactly {PUBLIC_KEY_SIZE} bytes, got {len(public_key)}")
            
        try:
            verify(message, signature, public_key)
            return True
        except Exception:
            return False


# Helper function to create a new wallet
def create_new_wallet(wallet_name: str = None, save: bool = False, 
                     password: str = None) -> Dict[str, Any]:
    """
    Create a new wallet with optional saving to disk
    
    Args:
        wallet_name (str, optional): Name for the wallet
        save (bool, optional): Whether to save the wallet to disk
        password (str, optional): Password for wallet encryption if saving
        
    Returns:
        Dict[str, Any]: Wallet information
    """
    wallet = WalletCreator.create_wallet(wallet_name)
    
    if save and password:
        wallet_file = WalletCreator.save_wallet(wallet, password)
        print(f"Wallet saved to: {wallet_file}")
    
    return wallet


# Helper function to convert keys between formats
def hex_to_keys(public_key_hex, private_key_hex=None):
    """
    Convert hex-encoded keys back to bytes format
    
    Args:
        public_key_hex (str or bytes): Hex-encoded public key or bytes
        private_key_hex (str or bytes, optional): Hex-encoded private key or bytes
        
    Returns:
        Tuple[bytes, Optional[bytes]]: Tuple of key byte objects (private key may be None)
    """
    # Handle both string and bytes input for public key
    if isinstance(public_key_hex, bytes):
        public_key = public_key_hex
    else:
        public_key = bytes.fromhex(public_key_hex)
    
    # Verify the public key length matches the expected value
    if len(public_key) != PUBLIC_KEY_SIZE:
        raise ValueError(f"Public key must be exactly {PUBLIC_KEY_SIZE} bytes, got {len(public_key)}")
    
    private_key = None
    if private_key_hex:
        # Handle both string and bytes input for private key
        if isinstance(private_key_hex, bytes):
            private_key = private_key_hex
        else:
            private_key = bytes.fromhex(private_key_hex)
        
        # Verify the private key length matches the expected value
        if len(private_key) != SECRET_KEY_SIZE:
            raise ValueError(f"Private key must be exactly {SECRET_KEY_SIZE} bytes, got {len(private_key)}")
    
    return public_key, private_key


# Helper function to get address from public key (for use in test.py)
def address_from_public_key(public_key: str) -> str:
    """
    Generate address from public key (for convenience in tests)
    
    Args:
        public_key: Base64-encoded public key
        
    Returns:
        Wallet address
    """
    # Decode public key from base64
    try:
        if isinstance(public_key, str):
            # If it's a base64 string
            public_key_bytes = base64.b64decode(public_key)
        else:
            # If it's already bytes
            public_key_bytes = public_key
            
        # Generate address using WalletCreator method
        return WalletCreator.generate_address(public_key_bytes)
    except Exception as e:
        print(f"Error generating address from public key: {e}")
        return "ERROR_ADDRESS"