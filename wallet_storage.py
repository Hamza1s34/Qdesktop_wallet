"""
Wallet Storage Manager for QBitcoin Wallet
Handles saving, loading, and managing multiple wallets
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

class WalletStorageManager:
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            # Use platform-appropriate directory
            if os.name == 'nt':  # Windows
                storage_dir = os.path.join(os.environ['APPDATA'], 'QBitcoinWallet')
            else:  # Linux/Mac
                storage_dir = os.path.join(os.path.expanduser('~'), '.qbitcoin_wallet')
        
        self.storage_dir = Path(storage_dir)
        self.wallets_dir = self.storage_dir / 'wallets'
        self.config_file = self.storage_dir / 'config.json'
        
        # Create directories if they don't exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.wallets_dir.mkdir(parents=True, exist_ok=True)
        
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load wallet configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        return {
            'last_used_wallet': None,
            'wallets': {},
            'version': '1.0',
            # Persist configured nodes for multi-node connectivity
            # Each node: {"host": str, "public_port": int, "wallet_port": int, "enabled": bool}
            'nodes': [
                {
                    'host': '134.122.79.166',
                    'public_port': 19009,
                    'wallet_port': 19010,
                    'enabled': True
                }
            ]
        }
    
    def _save_config(self):
        """Save wallet configuration"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def save_wallet(self, wallet_data: Dict, wallet_name: str = None) -> str:
        """Save wallet to storage and return wallet path"""
        if wallet_name is None:
            wallet_name = wallet_data.get('name', f'wallet_{int(datetime.now().timestamp())}')
        
        # Ensure unique wallet name
        original_name = wallet_name
        counter = 1
        while self.wallet_exists(wallet_name):
            wallet_name = f"{original_name}_{counter}"
            counter += 1
        
        wallet_file = self.wallets_dir / f"{wallet_name}.json"
        
        try:
            with open(wallet_file, 'w') as f:
                json.dump(wallet_data, f, indent=2)
            
            # Update config
            self.config['wallets'][wallet_name] = {
                'path': str(wallet_file),
                'address': wallet_data.get('address', ''),
                'created_at': wallet_data.get('created_at', datetime.now().timestamp()),
                'last_accessed': datetime.now().timestamp(),
                'encrypted': wallet_data.get('encrypted', False)
            }
            self.config['last_used_wallet'] = wallet_name
            self._save_config()
            
            return str(wallet_file)
            
        except Exception as e:
            raise Exception(f"Failed to save wallet: {e}")
    
    def load_wallet(self, wallet_name: str) -> Dict:
        """Load wallet data from storage"""
        if not self.wallet_exists(wallet_name):
            raise Exception(f"Wallet '{wallet_name}' not found")
        
        wallet_info = self.config['wallets'][wallet_name]
        wallet_path = wallet_info['path']
        
        try:
            with open(wallet_path, 'r') as f:
                wallet_data = json.load(f)
            
            # Update last accessed time
            self.config['wallets'][wallet_name]['last_accessed'] = datetime.now().timestamp()
            self.config['last_used_wallet'] = wallet_name
            self._save_config()
            
            return wallet_data
            
        except Exception as e:
            raise Exception(f"Failed to load wallet: {e}")
    
    def wallet_exists(self, wallet_name: str) -> bool:
        """Check if wallet exists"""
        return wallet_name in self.config['wallets']
    
    def get_wallet_list(self) -> List[Dict]:
        """Get list of all wallets"""
        wallets = []
        for name, info in self.config['wallets'].items():
            wallets.append({
                'name': name,
                'address': info['address'],
                'created_at': info['created_at'],
                'last_accessed': info['last_accessed'],
                'encrypted': info['encrypted'],
                'path': info['path']
            })
        
        # Sort by last accessed time (most recent first)
        wallets.sort(key=lambda x: x['last_accessed'], reverse=True)
        return wallets
    
    def get_last_used_wallet(self) -> Optional[str]:
        """Get the name of the last used wallet"""
        return self.config.get('last_used_wallet')
    
    def delete_wallet(self, wallet_name: str) -> bool:
        """Delete wallet from storage"""
        if not self.wallet_exists(wallet_name):
            return False
        
        try:
            wallet_info = self.config['wallets'][wallet_name]
            wallet_path = Path(wallet_info['path'])
            
            # Delete wallet file
            if wallet_path.exists():
                wallet_path.unlink()
            
            # Remove from config
            del self.config['wallets'][wallet_name]
            
            # Update last used wallet if it was the deleted one
            if self.config['last_used_wallet'] == wallet_name:
                remaining_wallets = list(self.config['wallets'].keys())
                self.config['last_used_wallet'] = remaining_wallets[0] if remaining_wallets else None
            
            self._save_config()
            return True
            
        except Exception as e:
            print(f"Error deleting wallet: {e}")
            return False
    
    def import_wallet_file(self, file_path: str, wallet_name: str = None) -> str:
        """Import wallet from external file"""
        try:
            with open(file_path, 'r') as f:
                wallet_data = json.load(f)
            
            # Validate wallet data structure
            required_fields = ['address', 'public_key', 'private_key_encrypted']
            for field in required_fields:
                if field not in wallet_data:
                    raise Exception(f"Invalid wallet file: missing field '{field}'")
            
            return self.save_wallet(wallet_data, wallet_name)
            
        except Exception as e:
            raise Exception(f"Failed to import wallet: {e}")
    
    def export_wallet(self, wallet_name: str, export_path: str) -> bool:
        """Export wallet to external file"""
        try:
            wallet_data = self.load_wallet(wallet_name)
            
            with open(export_path, 'w') as f:
                json.dump(wallet_data, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting wallet: {e}")
            return False
    
    def get_storage_info(self) -> Dict:
        """Get storage information"""
        return {
            'storage_dir': str(self.storage_dir),
            'wallets_dir': str(self.wallets_dir),
            'config_file': str(self.config_file),
            'total_wallets': len(self.config['wallets']),
            'last_used_wallet': self.config['last_used_wallet']
        }

    # =====================
    # Node configuration
    # =====================

    def get_nodes(self) -> List[Dict]:
        """Return configured nodes (list of dicts)."""
        nodes = self.config.get('nodes')
        if nodes is None or not isinstance(nodes, list):
            nodes = []
            self.config['nodes'] = nodes
            self._save_config()
        # Seed a default public node if list is empty
        if len(nodes) == 0:
            default_node = {
                'host': '134.122.79.166',
                'public_port': 19009,
                'wallet_port': 19010,
                'enabled': True
            }
            self.config['nodes'] = [default_node]
            nodes = self.config['nodes']
            self._save_config()
        return nodes

    def add_node(self, host: str, public_port: int = 19009, wallet_port: int = 19010, enabled: bool = True) -> None:
        """Add a new node configuration if not already present."""
        nodes = self.get_nodes()
        exists = any(n.get('host') == host and int(n.get('public_port', 19009)) == int(public_port) for n in nodes)
        if not exists:
            nodes.append({
                'host': host,
                'public_port': int(public_port),
                'wallet_port': int(wallet_port),
                'enabled': bool(enabled)
            })
            self._save_config()

    def remove_node(self, host: str, public_port: int = 19009) -> None:
        """Remove a node by host and public_port."""
        nodes = self.get_nodes()
        new_nodes = [n for n in nodes if not (n.get('host') == host and int(n.get('public_port', 19009)) == int(public_port))]
        if len(new_nodes) != len(nodes):
            self.config['nodes'] = new_nodes
            self._save_config()

    def set_node_enabled(self, host: str, public_port: int, enabled: bool) -> None:
        """Enable/disable a node."""
        nodes = self.get_nodes()
        changed = False
        for n in nodes:
            if n.get('host') == host and int(n.get('public_port', 19009)) == int(public_port):
                n['enabled'] = bool(enabled)
                changed = True
                break
        if changed:
            self._save_config()

    def replace_nodes(self, nodes: List[Dict]) -> None:
        """Replace full node list and save."""
        # Minimal validation
        sanitized = []
        for n in nodes:
            if 'host' in n:
                sanitized.append({
                    'host': n['host'],
                    'public_port': int(n.get('public_port', 19009)),
                    'wallet_port': int(n.get('wallet_port', 19010)),
                    'enabled': bool(n.get('enabled', True))
                })
        self.config['nodes'] = sanitized
        self._save_config()
