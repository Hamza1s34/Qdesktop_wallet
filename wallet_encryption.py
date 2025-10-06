"""
Wallet encryption module for QBitcoin wallets.
Provides AES-256-GCM encryption for private keys with password-based key derivation.
"""

import os
import base64
from typing import Dict, Any 
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


class WalletEncryption:
    """
    Handles encryption and decryption of wallet private keys using AES-256-GCM
    with PBKDF2 key derivation from user passwords.
    """
    
    # Constants for encryption
    SALT_LENGTH = 32  # 256 bits
    KEY_LENGTH = 32   # 256 bits for AES-256
    NONCE_LENGTH = 12 # 96 bits for GCM
    ITERATIONS = 100000  # PBKDF2 iterations
    
    @staticmethod
    def generate_salt() -> bytes:
        """Generate a random salt for key derivation"""
        return os.urandom(WalletEncryption.SALT_LENGTH)
    
    @staticmethod
    def generate_nonce() -> bytes:
        """Generate a random nonce for AES-GCM"""
        return os.urandom(WalletEncryption.NONCE_LENGTH)
    
    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2
        
        Args:
            password (str): User password
            salt (bytes): Random salt
            
        Returns:
            bytes: Derived encryption key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=WalletEncryption.KEY_LENGTH,
            salt=salt,
            iterations=WalletEncryption.ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    @staticmethod
    def encrypt_private_key(private_key_hex, password: str) -> Dict[str, str]:
        """
        Encrypt private key with password
        
        Args:
            private_key_hex (str or bytes): Private key in hexadecimal format or as bytes
            password (str): User password
            
        Returns:
            Dict[str, str]: Encrypted data with salt, nonce, and ciphertext
        """
        try:
            # Generate salt and nonce
            salt = WalletEncryption.generate_salt()
            nonce = WalletEncryption.generate_nonce()
            
            # Derive key from password
            key = WalletEncryption.derive_key(password, salt)
            
            # Initialize AES-GCM cipher
            aesgcm = AESGCM(key)
            
            # Encrypt the private key
            # Handle both string and bytes input
            if isinstance(private_key_hex, bytes):
                private_key_bytes = private_key_hex
            else:
                private_key_bytes = bytes.fromhex(private_key_hex)
            ciphertext = aesgcm.encrypt(nonce, private_key_bytes, None)
            
            # Return encrypted data as base64 strings
            return {
                'salt': base64.b64encode(salt).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
                'encrypted': True
            }
            
        except Exception as e:
            raise Exception(f"Encryption failed: {str(e)}")
    
    @staticmethod
    def decrypt_private_key(encrypted_data: Dict[str, str], password: str) -> str:
        """
        Decrypt private key with password
        
        Args:
            encrypted_data (Dict[str, str]): Encrypted data containing salt, nonce, and ciphertext
            password (str): User password
            
        Returns:
            str: Decrypted private key in hexadecimal format
            
        Raises:
            Exception: If decryption fails (wrong password or corrupted data)
        """
        try:
            # Extract encrypted components
            salt = base64.b64decode(encrypted_data['salt'])
            nonce = base64.b64decode(encrypted_data['nonce'])
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            
            # Derive key from password
            key = WalletEncryption.derive_key(password, salt)
            
            # Initialize AES-GCM cipher
            aesgcm = AESGCM(key)
            
            # Decrypt the private key
            private_key_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            
            # Return as hex string
            return private_key_bytes.hex()
            
        except Exception as e:
            raise Exception(f"Decryption failed: Invalid password or corrupted data")
    
    @staticmethod
    def encrypt_wallet_data(wallet_data: Dict[str, Any], password: str) -> Dict[str, Any]:
        """
        Encrypt only the private key in wallet data
        
        Args:
            wallet_data (Dict[str, Any]): Original wallet data
            password (str): User password
            
        Returns:
            Dict[str, Any]: Wallet data with encrypted private key
        """
        # Create a copy of wallet data
        encrypted_wallet = wallet_data.copy()
        
        # Check if private key exists and is not already encrypted
        if 'private_key' in wallet_data and not wallet_data.get('encrypted', False):
            # Encrypt the private key
            encrypted_private_key = WalletEncryption.encrypt_private_key(
                wallet_data['private_key'], 
                password
            )
            
            # Replace private key with encrypted data
            encrypted_wallet['private_key_encrypted'] = encrypted_private_key
            
            # Remove the plain private key
            del encrypted_wallet['private_key']
            
            # Mark as encrypted
            encrypted_wallet['encrypted'] = True
            encrypted_wallet['encryption_version'] = '1.0'
            
        return encrypted_wallet
    
    @staticmethod
    def decrypt_wallet_data(wallet_data: Dict[str, Any], password: str) -> Dict[str, Any]:
        """
        Decrypt private key in wallet data
        
        Args:
            wallet_data (Dict[str, Any]): Encrypted wallet data
            password (str): User password
            
        Returns:
            Dict[str, Any]: Wallet data with decrypted private key
        """
        # Create a copy of wallet data
        decrypted_wallet = wallet_data.copy()
        
        # Check if wallet is encrypted
        if wallet_data.get('encrypted', False) and 'private_key_encrypted' in wallet_data:
            # Decrypt the private key
            private_key_hex = WalletEncryption.decrypt_private_key(
                wallet_data['private_key_encrypted'], 
                password
            )
            
            # Add decrypted private key
            decrypted_wallet['private_key'] = private_key_hex
            
            # Remove encrypted private key data (but keep it for re-encryption)
            # del decrypted_wallet['private_key_encrypted']
            
        return decrypted_wallet
    
    @staticmethod
    def is_wallet_encrypted(wallet_data: Dict[str, Any]) -> bool:
        """
        Check if wallet data is encrypted
        
        Args:
            wallet_data (Dict[str, Any]): Wallet data to check
            
        Returns:
            bool: True if wallet is encrypted, False otherwise
        """
        return wallet_data.get('encrypted', False) and 'private_key_encrypted' in wallet_data
    
    @staticmethod
    def verify_password(wallet_data: Dict[str, Any], password: str) -> bool:
        """
        Verify if password is correct for encrypted wallet
        
        Args:
            wallet_data (Dict[str, Any]): Encrypted wallet data
            password (str): Password to verify
            
        Returns:
            bool: True if password is correct, False otherwise
        """
        try:
            if not WalletEncryption.is_wallet_encrypted(wallet_data):
                return True  # Wallet is not encrypted
            
            # Try to decrypt the private key
            WalletEncryption.decrypt_private_key(
                wallet_data['private_key_encrypted'], 
                password
            )
            return True
            
        except Exception:
            return False
