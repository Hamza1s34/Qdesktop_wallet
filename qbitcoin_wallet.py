#!/usr/bin/env python3
"""
QBitcoin Wallet - Main GUI Application
=====================================

A quantum-resistant wallet application using Falcon-512 signatures.
Features:
- Create and import wallets
- Multiple tabs for different functions
- Dark blue theme
- Encrypted wallet storage
- Local transaction signing
- Balance checking via API
"""

import sys
import os
import json
import logging
import time
from pathlib import Path
import qrcode
from io import BytesIO
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QMessageBox, QDialog, QFormLayout, QProgressBar,
    QSplashScreen,  QGridLayout,  QCheckBox, QSpacerItem,
    QSizePolicy, QFileDialog, QInputDialog,  QGroupBox, 
    QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal 
from PyQt6.QtGui import QPixmap, QFont, QIcon, QColor

# Import wallet modules
from wallet_creator import WalletCreator
from wallet_encryption import WalletEncryption
from wallet_storage import WalletStorageManager
from api_client import QBitcoinAPIClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SplashScreen(QSplashScreen):
    """Custom splash screen for the application"""
    
    def __init__(self):
        # Load splash screen image
        splash_path = Path(__file__).parent / "asessts" / "splash_screen" / "image.png"
        if splash_path.exists():
            pixmap = QPixmap(str(splash_path))
            # Scale to fit screen if needed
            if pixmap.width() > 800 or pixmap.height() > 600:
                pixmap = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, 
                                     Qt.TransformationMode.SmoothTransformation)
        else:
            # Create a default splash screen if image not found
            pixmap = QPixmap(800, 600)
            pixmap.fill(QColor("#1e3a5f"))
        
        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        
        # Add loading text
        self.showMessage("Loading QBitcoin Wallet...", 
                        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                        QColor("#ffffff"))


class BalanceWorker(QThread):
    """Worker thread for fetching balance and transaction history"""
    balance_ready = pyqtSignal(dict)
    transactions_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, api_client, address):
        super().__init__()
        self.api_client = api_client
        self.address = address
        
    def run(self):
        """Fetch balance and transaction history"""
        try:
            # Get balance
            balance_result = self.api_client.get_balance(self.address)
            logger.debug(f"Balance response: {balance_result}")
            
            balance_info = {
                'balance': '0.00000000',
                'success': False
            }
            
            if isinstance(balance_result, dict):
                if balance_result.get('success'):
                    balance_data = balance_result.get('data', {})
                    balance_quarks = balance_data.get('balance', 0)
                elif 'balance' in balance_result:
                    # Direct balance field in quarks
                    balance_quarks = balance_result.get('balance', 0)
                else:
                    balance_quarks = 0
                
                # Convert quarks to QBC (1 QBC = 1,000,000,000 quarks = 10^9 quarks)
                balance_qbc = float(balance_quarks) / 1_000_000_000
                balance_info['balance'] = f"{balance_qbc:.9f}"
                balance_info['success'] = True
            
            self.balance_ready.emit(balance_info)
            
            # Get transaction history
            try:
                transactions_result = self.api_client.get_transactions_by_address(self.address, page=1, per_page=50)
                logger.debug(f"Transactions response: {transactions_result}")
                
                transactions = []
                if isinstance(transactions_result, dict):
                    # Handle the actual API response format
                    if 'transactions' in transactions_result:
                        tx_data = transactions_result.get('transactions', [])
                        if isinstance(tx_data, list):
                            transactions = tx_data
                    elif transactions_result.get('success'):
                        tx_data = transactions_result.get('data', [])
                        if isinstance(tx_data, list):
                            transactions = tx_data
                elif isinstance(transactions_result, list):
                    transactions = transactions_result
                
                logger.info(f"Found {len(transactions)} transactions in API response")
                self.transactions_ready.emit(transactions)
                
            except Exception as e:
                logger.error(f"Error fetching transactions: {e}")
                self.transactions_ready.emit([])
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            self.error_occurred.emit(f"Failed to fetch balance: {str(e)}")


class ApiWorker(QThread):
    """Worker thread for API calls to prevent UI freezing"""
    network_info_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, api_client):
        super().__init__()
        self.api_client = api_client
        
    def run(self):
        """Run API calls in background thread"""
        try:
            network_info = {
                'node_status': 'Disconnected',
                'block_height': 'Unknown',
                'peer_count': 'Unknown',
                'network_hashrate': 'Unknown',
                'last_block': 'Unknown'
            }
            
            # Get node status with timeout
            try:
                node_status = self.api_client.get_node_status()
                logger.debug(f"Node status response: {node_status}")
                
                if isinstance(node_status, dict):
                    if node_status.get('connected') or node_status.get('success'):
                        network_info['node_status'] = 'Connected'
                        
                        # Extract node info if available
                        node_info = node_status.get('node_info', {})
                        if node_info:
                            height = node_info.get('height', 'Unknown')
                            network_info['block_height'] = str(height)
                            
                            peers = node_info.get('peers', 'Unknown')
                            network_info['peer_count'] = str(peers)
                    else:
                        network_info['node_status'] = 'Disconnected'
                else:
                    network_info['node_status'] = 'Error'
            except Exception as e:
                network_info['node_status'] = 'Error'
                logger.debug(f"Node status error: {e}")
            
            # Get chain stats with timeout
            try:
                chain_stats = self.api_client.get_chain_stats()
                logger.debug(f"Chain stats response: {chain_stats}")
                
                if isinstance(chain_stats, dict):
                    # Handle various possible response formats
                    if 'success' in chain_stats and chain_stats.get('success'):
                        stats = chain_stats.get('data', {})
                    else:
                        stats = chain_stats
                    
                    # Update block height if not already set
                    if network_info['block_height'] == 'Unknown':
                        height = stats.get('block_height') or stats.get('height', 'Unknown')
                        network_info['block_height'] = str(height)
                    
                    # Update network hashrate
                    hashrate = stats.get('network_hashrate') or stats.get('hash_power', 'Unknown')
                    if hashrate != 'Unknown' and hashrate != 0:
                        if isinstance(hashrate, (int, float)):
                            if hashrate > 1e12:
                                network_info['network_hashrate'] = f"{hashrate/1e12:.2f} TH/s"
                            elif hashrate > 1e9:
                                network_info['network_hashrate'] = f"{hashrate/1e9:.2f} GH/s"
                            elif hashrate > 1e6:
                                network_info['network_hashrate'] = f"{hashrate/1e6:.2f} MH/s"
                            else:
                                network_info['network_hashrate'] = f"{hashrate} H/s"
                        else:
                            network_info['network_hashrate'] = str(hashrate)
                    
                    # Update last block time
                    last_block_time = stats.get('last_block_timestamp') or stats.get('timestamp', 0)
                    if last_block_time and last_block_time > 0:
                        last_block_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_block_time))
                        network_info['last_block'] = last_block_str
                        
            except Exception as e:
                logger.debug(f"Chain stats error: {e}")
            
            # Get peer count if not already set
            if network_info['peer_count'] == 'Unknown':
                try:
                    peers_stat = self.api_client.get_peers_stat()
                    logger.debug(f"Peers stat response: {peers_stat}")
                    
                    if isinstance(peers_stat, list):
                        peer_count = len(peers_stat)
                        network_info['peer_count'] = str(peer_count)
                    elif isinstance(peers_stat, dict) and 'success' in peers_stat and peers_stat.get('success'):
                        peer_data = peers_stat.get('data', [])
                        peer_count = len(peer_data)
                        network_info['peer_count'] = str(peer_count)
                except Exception as e:
                    logger.debug(f"Peers stat error: {e}")
            
            self.network_info_ready.emit(network_info)
            
        except Exception as e:
            self.error_occurred.emit(f"Network update failed: {str(e)}")


class TransactionWorker(QThread):
    """Worker thread for sending transactions"""
    transaction_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    progress_update = pyqtSignal(str)
    
    def __init__(self, api_client, wallet_data, recipient, amount_quarks, fee_quarks, message, password):
        super().__init__()
        self.api_client = api_client
        self.wallet_data = wallet_data
        self.recipient = recipient
        self.amount_quarks = amount_quarks
        self.fee_quarks = fee_quarks
        self.message = message
        self.password = password
        
    def run(self):
        """Create, sign and submit transaction"""
        try:
            from falcon import FalconSignature
            
            # Step 1: Decrypt private key
            self.progress_update.emit("Decrypting wallet...")
            encrypted_private_key = self.wallet_data.get('private_key_encrypted', {})
            if not encrypted_private_key:
                raise Exception("No encrypted private key found in wallet")
            
            decrypted_private_key = WalletEncryption.decrypt_private_key(encrypted_private_key, self.password)
            private_key_bytes = bytes.fromhex(decrypted_private_key)
            
            # Step 2: Create unsigned transaction
            self.progress_update.emit("Creating transaction...")
            from_address = self.wallet_data.get('address')
            public_key_hex = self.wallet_data.get('public_key')
            
            result = self.api_client.create_unsigned_transaction(
                from_address=from_address,
                to_address=self.recipient,
                amount=self.amount_quarks,
                fee=self.fee_quarks,
                public_key_hex=public_key_hex,
                message=self.message
            )
            
            tx_hash = result['tx_hash']
            tx_data = result['tx_data']
            
            logger.info(f"Transaction created with hash: {tx_hash}")
            
            # Step 3: Sign transaction
            self.progress_update.emit("Signing transaction...")
            falcon = FalconSignature()
            signature_bytes = falcon.sign(private_key_bytes, bytes.fromhex(tx_hash))
            signature_hex = signature_bytes.hex()
            
            logger.info(f"Transaction signed, signature length: {len(signature_bytes)} bytes")
            
            # Step 4: Submit transaction
            self.progress_update.emit("Submitting transaction...")
            submit_result = self.api_client.submit_signed_transaction(
                transaction_data=tx_data,
                signature=signature_hex,
                public_key_hex=public_key_hex
            )
            
            logger.info(f"Transaction submitted: {submit_result}")
            
            self.transaction_complete.emit({
                'success': True,
                'tx_hash': submit_result.get('tx_hash'),
                'status': submit_result.get('status')
            })
            
        except Exception as e:
            logger.error(f"Transaction error: {e}")
            self.error_occurred.emit(str(e))


class WalletWorker(QThread):
    """Worker thread for wallet operations"""
    
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    
    def __init__(self, operation, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs
    
    def run(self):
        try:
            if self.operation == "create_wallet":
                result = self.create_wallet()
            elif self.operation == "import_wallet":
                result = self.import_wallet()
            elif self.operation == "get_balance":
                result = self.get_balance()
            else:
                raise ValueError(f"Unknown operation: {self.operation}")
            
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
    
    def create_wallet(self):
        """Create a new wallet"""
        self.progress.emit(10)
        
        wallet_name = self.kwargs.get('name')
        password = self.kwargs.get('password')
        
        self.progress.emit(30)
        
        # Create new keypair
        private_key, public_key = WalletCreator.create_keypair()
        
        self.progress.emit(50)
        
        # Generate address
        address = WalletCreator.generate_address(public_key)
        
        self.progress.emit(70)
        
        # Encrypt private key
        encrypted_data = WalletEncryption.encrypt_private_key(private_key, password)
        
        self.progress.emit(90)
        
        # Create wallet data
        wallet_data = {
            "name": wallet_name,
            "address": address,
            "public_key": public_key.hex(),
            "public_key_size": len(public_key),
            "private_key_size": len(private_key),
            "private_key_encrypted": encrypted_data,
            "algorithm": "falcon-512",
            "encrypted": True,
            "encryption_version": "1.0",
            "created_at": time.time()
        }
        
        self.progress.emit(100)
        return wallet_data
    
    def import_wallet(self):
        """Import an existing wallet"""
        file_path = self.kwargs.get('file_path')
        
        with open(file_path, 'r') as f:
            wallet_data = json.load(f)
        
        return wallet_data
    
    def get_balance(self):
        """Get wallet balance via API"""
        address = self.kwargs.get('address')
        # This would call the actual API
        # For now, return a placeholder
        return {"balance": "0.00000000", "confirmed": "0.00000000", "unconfirmed": "0.00000000"}


class TransactionWorker(QThread):
    """Worker thread for sending transactions"""
    transaction_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    progress_update = pyqtSignal(str)
    
    def __init__(self, api_client, wallet_data, recipient, amount_quarks, fee_quarks, message, password):
        super().__init__()
        self.api_client = api_client
        self.wallet_data = wallet_data
        self.recipient = recipient
        self.amount_quarks = amount_quarks
        self.fee_quarks = fee_quarks
        self.message = message
        self.password = password
        
    def run(self):
        """Create, sign and submit transaction"""
        try:
            from falcon import FalconSignature
            
            # Step 1: Decrypt private key
            self.progress_update.emit("Decrypting wallet...")
            encrypted_private_key = self.wallet_data.get('private_key_encrypted', {})
            if not encrypted_private_key:
                raise Exception("No encrypted private key found in wallet")
            
            decrypted_private_key = WalletEncryption.decrypt_private_key(encrypted_private_key, self.password)
            private_key_bytes = bytes.fromhex(decrypted_private_key)
            
            # Step 2: Create unsigned transaction
            self.progress_update.emit("Creating transaction...")
            from_address = self.wallet_data.get('address')
            public_key_hex = self.wallet_data.get('public_key')
            
            result = self.api_client.create_unsigned_transaction(
                from_address=from_address,
                to_address=self.recipient,
                amount=self.amount_quarks,
                fee=self.fee_quarks,
                public_key_hex=public_key_hex,
                message=self.message
            )
            
            tx_hash = result['tx_hash']
            tx_data = result['tx_data']
            
            logger.info(f"Transaction created with hash: {tx_hash}")
            
            # Step 3: Sign transaction
            self.progress_update.emit("Signing transaction...")
            falcon = FalconSignature()
            signature_bytes = falcon.sign(private_key_bytes, bytes.fromhex(tx_hash))
            signature_hex = signature_bytes.hex()
            
            logger.info(f"Transaction signed, signature length: {len(signature_bytes)} bytes")
            
            # Step 4: Submit transaction
            self.progress_update.emit("Submitting transaction...")
            submit_result = self.api_client.submit_signed_transaction(
                transaction_data=tx_data,
                signature=signature_hex,
                public_key_hex=public_key_hex
            )
            
            logger.info(f"Transaction submitted: {submit_result}")
            
            self.transaction_complete.emit({
                'success': True,
                'tx_hash': submit_result.get('tx_hash'),
                'status': submit_result.get('status')
            })
            
        except Exception as e:
            logger.error(f"Transaction error: {e}")
            self.error_occurred.emit(str(e))


class WalletTab(QWidget):
    """Main wallet tab containing balance and transaction history"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)  # Reduce overall spacing
        
        # Wallet info section
        info_group = QGroupBox("Wallet Information")
        info_layout = QGridLayout()
        info_layout.setVerticalSpacing(5)  # Reduce vertical spacing
        info_layout.setHorizontalSpacing(10)
        
        self.address_label = QLabel("Address:")
        self.address_value = QLineEdit()
        self.address_value.setReadOnly(True)
        self.address_value.setMaximumHeight(30)  # Reduce height
        
        self.balance_label = QLabel("Balance:")
        self.balance_value = QLabel("0.000000000 QBC")
        self.balance_value.setStyleSheet("font-size: 16px; font-weight: bold; color: #4CAF50;")  # Slightly smaller font
        
        self.refresh_btn = QPushButton("Refresh Balance")
        self.refresh_btn.clicked.connect(self.refresh_balance)
        self.refresh_btn.setMaximumHeight(30)  # Reduce height
        self.refresh_btn.setMaximumWidth(120)  # Reduce width
        
        info_layout.addWidget(self.address_label, 0, 0)
        info_layout.addWidget(self.address_value, 0, 1, 1, 2)
        info_layout.addWidget(self.balance_label, 1, 0)
        info_layout.addWidget(self.balance_value, 1, 1)
        info_layout.addWidget(self.refresh_btn, 1, 2)
        
        info_group.setLayout(info_layout)
        info_group.setMaximumHeight(100)  # Limit the height of info section
        layout.addWidget(info_group)
        
        # Transaction history
        history_group = QGroupBox("Transaction History")
        history_layout = QVBoxLayout()
        
        # Transaction controls
        tx_controls = QHBoxLayout()
        self.refresh_tx_btn = QPushButton("Refresh Transactions")
        self.refresh_tx_btn.clicked.connect(self.refresh_transactions)
        self.refresh_tx_btn.setMaximumHeight(30)
        self.refresh_tx_btn.setMaximumWidth(150)
        tx_controls.addWidget(self.refresh_tx_btn)
        tx_controls.addStretch()
        
        history_layout.addLayout(tx_controls)
        
        # Transaction table with more columns
        self.transaction_table = QTableWidget()
        self.transaction_table.setColumnCount(7)
        self.transaction_table.setHorizontalHeaderLabels(
            ["Date", "Direction", "Amount (QBC)", "Fee (QBC)", "Status", "Hash", "Block"]
        )
        self.transaction_table.setAlternatingRowColors(True)
        self.transaction_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # Make table fill full width with proper column sizing
        header = self.transaction_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Direction
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Amount
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Fee
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)          # Hash (takes remaining space)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Block
        
        history_layout.addWidget(self.transaction_table)
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
        
        self.setLayout(layout)
    
    def update_wallet_info(self, wallet_data):
        """Update wallet information display"""
        if wallet_data:
            self.address_value.setText(wallet_data.get("address", ""))
            # Auto-refresh balance when wallet is loaded
            self.refresh_balance()
    
    def refresh_balance(self):
        """Refresh wallet balance and transaction history"""
        if hasattr(self.main_window, 'current_wallet') and self.main_window.current_wallet:
            address = self.main_window.current_wallet.get("address")
            if address:
                # Show loading
                self.balance_value.setText("Loading...")
                self.refresh_btn.setEnabled(False)
                
                # Start worker thread to fetch balance and transactions
                self.balance_worker = BalanceWorker(self.main_window.api_client, address)
                self.balance_worker.balance_ready.connect(self.on_balance_ready)
                self.balance_worker.transactions_ready.connect(self.on_transactions_ready)
                self.balance_worker.error_occurred.connect(self.on_balance_error)
                self.balance_worker.start()
    
    def refresh_transactions(self):
        """Refresh only transaction history"""
        if hasattr(self.main_window, 'current_wallet') and self.main_window.current_wallet:
            address = self.main_window.current_wallet.get("address")
            if address:
                self.refresh_tx_btn.setEnabled(False)
                
                # Start worker thread to fetch only transactions
                self.tx_worker = BalanceWorker(self.main_window.api_client, address)
                self.tx_worker.transactions_ready.connect(self.on_transactions_ready)
                self.tx_worker.error_occurred.connect(lambda error: self.refresh_tx_btn.setEnabled(True))
                self.tx_worker.start()
    
    def on_balance_ready(self, balance_info):
        """Handle balance info from worker thread"""
        if balance_info['success']:
            self.balance_value.setText(f"{balance_info['balance']} QBC")
            self.balance_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #4CAF50;")
        else:
            self.balance_value.setText("Error fetching balance")
            self.balance_value.setStyleSheet("font-size: 18px; font-weight: bold; color: #f44336;")
        
        self.refresh_btn.setEnabled(True)
    
    def on_transactions_ready(self, transactions):
        """Handle transaction history from worker thread"""
        logger.info(f"Processing {len(transactions)} transactions for display")
        
        if not hasattr(self.main_window, 'current_wallet') or not self.main_window.current_wallet:
            logger.warning("No current wallet loaded")
            return
        
        wallet_address = self.main_window.current_wallet.get("address", "").lower()
        logger.info(f"Wallet address: {wallet_address}")
        
        self.transaction_data = transactions  # Store for reference
        self.transaction_table.setRowCount(len(transactions))
        
        for row, tx in enumerate(transactions):
            # Parse transaction data from the actual API structure
            date_str = "Unknown"
            if 'timestamp' in tx:
                timestamp = tx['timestamp']
                date_str = time.strftime('%m-%d %H:%M', time.localtime(timestamp))
            
            # Transaction type
            tx_type = tx.get('type', 'Unknown')
            
            # Determine direction based on from_address and to_address
            direction = "Unknown"
            from_addr = tx.get('from_address', '').lower()
            to_addr = tx.get('to_address', '').lower()
            
            if from_addr == wallet_address and to_addr == wallet_address:
                direction = "Self"
            elif from_addr == wallet_address:
                direction = "Send"
            elif to_addr == wallet_address:
                direction = "Receive"
            else:
                # Check outputs to see if we received anything
                received_amount = 0
                outputs = tx.get('outputs', [])
                for output in outputs:
                    output_addr = output.get('address', '').lower()
                    if output_addr == wallet_address:
                        received_amount += output.get('amount', 0)
                
                if received_amount > 0:
                    direction = "Receive"
                else:
                    direction = "Other"
            
            # Use address_amount (the amount specifically for our address) instead of total amount
            amount_quarks = tx.get('address_amount', 0)
            amount_qbc = float(amount_quarks) / 1_000_000_000
            
            # Add direction indicator to amount
            if direction == "Send":
                amount_display = f"-{amount_qbc:.9f}"
            elif direction == "Receive":
                amount_display = f"+{amount_qbc:.9f}"
            else:
                amount_display = f"{amount_qbc:.9f}"
            
            # Convert fee from quarks to QBC
            fee_quarks = tx.get('fee', 0)
            fee_qbc = f"{float(fee_quarks) / 1_000_000_000:.9f}"
            
            # Transaction hash
            tx_hash = tx.get('tx_hash', 'Unknown')
            
            # Status based on confirmations
            confirmations = tx.get('confirmations', 0)
            if confirmations >= 1:
                status = "Confirmed"
            else:
                status = "Pending"
            
            # Block number
            block_num = str(tx.get('block_number', 'Unknown'))
            
            # Add to table
            self.transaction_table.setItem(row, 0, QTableWidgetItem(date_str))
            
            # Color code direction
            direction_item = QTableWidgetItem(direction)
            if direction == "Receive":
                direction_item.setForeground(QColor("#4CAF50"))  # Green
            elif direction == "Send":
                direction_item.setForeground(QColor("#f44336"))  # Red
            else:
                direction_item.setForeground(QColor("#FF9800"))  # Orange
            self.transaction_table.setItem(row, 1, direction_item)
            
            # Color code amount
            amount_item = QTableWidgetItem(amount_display)
            if direction == "Receive":
                amount_item.setForeground(QColor("#4CAF50"))  # Green
            elif direction == "Send":
                amount_item.setForeground(QColor("#f44336"))  # Red
            self.transaction_table.setItem(row, 2, amount_item)
            
            self.transaction_table.setItem(row, 3, QTableWidgetItem(fee_qbc))
            self.transaction_table.setItem(row, 4, QTableWidgetItem(status))
            self.transaction_table.setItem(row, 5, QTableWidgetItem(tx_hash))
            self.transaction_table.setItem(row, 6, QTableWidgetItem(block_num))
        
        # Resize columns to content
        self.transaction_table.resizeColumnsToContents()
        
        # Re-enable refresh button
        if hasattr(self, 'refresh_tx_btn'):
            self.refresh_tx_btn.setEnabled(True)
        
        if not transactions:
            # Show message if no transactions
            self.transaction_table.setRowCount(1)
            self.transaction_table.setItem(0, 0, QTableWidgetItem("No transactions found"))
            for col in range(1, 7):
                self.transaction_table.setItem(0, col, QTableWidgetItem(""))
            self.transaction_data = []
        
        logger.info(f"Displayed {len(transactions)} transactions")
    
    def on_balance_error(self, error_message):
        """Handle balance fetch errors"""
        self.balance_value.setText("Error")
        self.balance_value.setStyleSheet("font-size: 16px; font-weight: bold; color: #f44336;")
        self.refresh_btn.setEnabled(True)
        logger.error(f"Balance error: {error_message}")


class SendTab(QWidget):
    """Tab for sending transactions"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        send_group = QGroupBox("Send QBitcoin")
        form_layout = QFormLayout()
        
        self.recipient_input = QLineEdit()
        self.recipient_input.setPlaceholderText("Enter recipient address...")
        
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00000000")
        
        self.fee_input = QLineEdit()
        self.fee_input.setPlaceholderText("0.00100000")
        self.fee_input.setText("0.00100000")  # Default fee: 0.001 QBC
        
        self.message_input = QTextEdit()
        self.message_input.setMaximumHeight(80)
        self.message_input.setPlaceholderText("Optional message...")
        
        self.send_btn = QPushButton("Send Transaction")
        self.send_btn.clicked.connect(self.send_transaction)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        
        form_layout.addRow("Recipient:", self.recipient_input)
        form_layout.addRow("Amount:", self.amount_input)
        form_layout.addRow("Fee:", self.fee_input)
        form_layout.addRow("Message:", self.message_input)
        form_layout.addRow("", self.send_btn)
        
        send_group.setLayout(form_layout)
        layout.addWidget(send_group)
        
        # Add spacer
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        self.setLayout(layout)
    
    def send_transaction(self):
        """Send a transaction"""
        # Check if wallet is loaded
        if not hasattr(self.main_window, 'current_wallet') or not self.main_window.current_wallet:
            QMessageBox.warning(self, "Error", "No wallet loaded. Please open a wallet first.")
            return
        
        recipient = self.recipient_input.text().strip()
        amount = self.amount_input.text().strip()
        fee = self.fee_input.text().strip()
        message = self.message_input.toPlainText().strip()
        
        if not recipient or not amount:
            QMessageBox.warning(self, "Error", "Please enter recipient and amount.")
            return
        
        # Validate recipient address format
        if not recipient.startswith('Q'):
            QMessageBox.warning(self, "Error", "Recipient address must start with 'Q'.")
            return
        
        try:
            amount_float = float(amount)
            fee_float = float(fee) if fee else 0.001
            
            if amount_float <= 0:
                QMessageBox.warning(self, "Error", "Amount must be greater than 0.")
                return
            
            if fee_float <= 0:
                QMessageBox.warning(self, "Error", "Fee must be greater than 0.")
                return
            
            # Convert to quarks (1 QBC = 1,000,000,000 quarks)
            amount_quarks = int(amount_float * 1_000_000_000)
            fee_quarks = int(fee_float * 1_000_000_000)
                
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid numeric values.")
            return
        
        # Show confirmation dialog
        recipient_display = recipient if len(recipient) <= 30 else f"{recipient[:30]}..."
        reply = QMessageBox.question(
            self, "Confirm Transaction",
            f"Send {amount} QBC to\n{recipient_display}?\n\nFee: {fee} QBC",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Request password to decrypt private key
            password, ok = QInputDialog.getText(
                self, 
                "Enter Password", 
                "Enter your wallet password to sign the transaction:",
                QLineEdit.EchoMode.Password
            )
            
            if not ok:
                return
            
            if not password:
                QMessageBox.warning(self, "Error", "Please enter a password.")
                return
            
            # Disable send button during transaction
            self.send_btn.setEnabled(False)
            self.send_btn.setText("Sending...")
            
            # Start transaction worker
            self.tx_worker = TransactionWorker(
                api_client=self.main_window.api_client,
                wallet_data=self.main_window.current_wallet,
                recipient=recipient,
                amount_quarks=amount_quarks,
                fee_quarks=fee_quarks,
                message=message,
                password=password
            )
            
            self.tx_worker.transaction_complete.connect(self.on_transaction_complete)
            self.tx_worker.error_occurred.connect(self.on_transaction_error)
            self.tx_worker.progress_update.connect(self.on_progress_update)
            self.tx_worker.start()
    
    def on_progress_update(self, message):
        """Handle progress updates"""
        self.send_btn.setText(message)
        self.main_window.statusBar().showMessage(message)
    
    def on_transaction_complete(self, result):
        """Handle successful transaction"""
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send Transaction")
        
        if result.get('success'):
            tx_hash = result.get('tx_hash', 'Unknown')
            QMessageBox.information(
                self, 
                "Transaction Sent!", 
                f"Transaction submitted successfully!\n\nTransaction Hash:\n{tx_hash}\n\nStatus: {result.get('status', 'submitted')}"
            )
            
            # Clear form
            self.recipient_input.clear()
            self.amount_input.clear()
            self.message_input.clear()
            
            # Refresh wallet balance
            if hasattr(self.main_window, 'wallet_tab'):
                self.main_window.wallet_tab.refresh_balance()
        else:
            QMessageBox.critical(self, "Error", "Transaction failed!")
    
    def on_transaction_error(self, error_message):
        """Handle transaction error"""
        self.send_btn.setEnabled(True)
        self.send_btn.setText("Send Transaction")
        
        QMessageBox.critical(
            self, 
            "Transaction Error", 
            f"Failed to send transaction:\n\n{error_message}"
        )
        
        self.main_window.statusBar().showMessage("Transaction failed")


class ReceiveTab(QWidget):
    """Tab for receiving transactions"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        receive_group = QGroupBox("Receive QBitcoin")
        receive_layout = QVBoxLayout()
        
        self.address_label = QLabel("Your Address:")
        self.address_display = QTextEdit()
        self.address_display.setMaximumHeight(100)
        self.address_display.setReadOnly(True)
        self.address_display.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                font-size: 12px;
                background-color: #34495e;
                color: #ecf0f1;
                border: 2px solid #3498db;
                border-radius: 5px;
                padding: 8px;
            }
        """)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton("Copy Address")
        self.copy_btn.clicked.connect(self.copy_address)
        
        self.generate_qr_btn = QPushButton("Generate QR Code")
        self.generate_qr_btn.clicked.connect(self.generate_qr_code)
        
        button_layout.addWidget(self.copy_btn)
        button_layout.addWidget(self.generate_qr_btn)
        button_layout.addStretch()
        
        # QR Code display
        qr_layout = QHBoxLayout()
        
        # Left side - QR Code
        qr_left = QVBoxLayout()
        qr_left.addWidget(QLabel("QR Code:"))
        
        self.qr_label = QLabel()
        self.qr_label.setMinimumSize(200, 200)
        self.qr_label.setMaximumSize(300, 300)
        self.qr_label.setStyleSheet("""
            QLabel {
                border: 2px solid #3498db;
                border-radius: 5px;
                background-color: white;
                padding: 10px;
            }
        """)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setText("No QR Code\nGenerated")
        self.qr_label.setScaledContents(True)
        
        qr_left.addWidget(self.qr_label)
        
        # Right side - Instructions
        instructions = QVBoxLayout()
        instructions.addWidget(QLabel("Instructions:"))
        
        instruction_text = QLabel("""
        1. Share this address to receive QBitcoin
        2. Use the QR code for easy sharing
        3. Always verify the address before sharing
        4. This address is unique to your wallet
        
        QR Code includes:
        • Your wallet address
        • Easy scanning for mobile wallets
        • Error correction for reliability
        """)
        instruction_text.setWordWrap(True)
        instruction_text.setStyleSheet("""
            QLabel {
                background-color: #34495e;
                color: #ecf0f1;
                border: 1px solid #3498db;
                border-radius: 5px;
                padding: 10px;
                font-size: 11px;
            }
        """)
        
        instructions.addWidget(instruction_text)
        instructions.addStretch()
        
        qr_layout.addLayout(qr_left)
        qr_layout.addLayout(instructions)
        
        receive_layout.addWidget(self.address_label)
        receive_layout.addWidget(self.address_display)
        receive_layout.addLayout(button_layout)
        receive_layout.addLayout(qr_layout)
        
        receive_group.setLayout(receive_layout)
        layout.addWidget(receive_group)
        
        # Add spacer
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        self.setLayout(layout)
    
    def update_address(self, address):
        """Update the displayed address and generate QR code"""
        self.address_display.setText(address)
        # Auto-generate QR code when address is set
        if address:
            self.generate_qr_code()
    
    def generate_qr_code(self):
        """Generate QR code for the wallet address"""
        address = self.address_display.toPlainText().strip()
        if not address:
            QMessageBox.warning(self, "Warning", "No address available to generate QR code.")
            return
        
        try:
            # Create QR code
            qr = qrcode.QRCode(
                version=1,  # Controls the size of the QR Code
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(address)
            qr.make(fit=True)
            
            # Create QR code image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert PIL image to QPixmap
            buffer = BytesIO()
            qr_img.save(buffer, format='PNG')
            buffer.seek(0)
            
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            
            # Scale the pixmap to fit the label
            scaled_pixmap = pixmap.scaled(
                self.qr_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.qr_label.setPixmap(scaled_pixmap)
            
            # Update button text
            self.generate_qr_btn.setText("Regenerate QR Code")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate QR code: {str(e)}")
            logger.error(f"QR code generation error: {e}")
    
    def copy_address(self):
        """Copy address to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.address_display.toPlainText())
        QMessageBox.information(self, "Copied", "Address copied to clipboard!")


class SettingsTab(QWidget):
    """Settings and configuration tab"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Wallet settings
        wallet_group = QGroupBox("Wallet Settings")
        wallet_layout = QFormLayout()
        
        self.backup_wallet_btn = QPushButton("Backup Wallet")
        self.backup_wallet_btn.clicked.connect(self.backup_wallet)
        wallet_layout.addRow("Backup:", self.backup_wallet_btn)
        
        wallet_group.setLayout(wallet_layout)
        layout.addWidget(wallet_group)
        
        # Network settings
        network_group = QGroupBox("Network Settings")
        network_layout = QVBoxLayout()
        
        # Nodes table
        self.nodes_table = QTableWidget()
        self.nodes_table.setColumnCount(7)
        self.nodes_table.setHorizontalHeaderLabels(["Host", "Public Port", "Wallet Port", "Enabled", "Status", "Height", "Peers"])
        self.nodes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.nodes_table.setAlternatingRowColors(True)
        self.nodes_table.horizontalHeader().setStretchLastSection(True)
        network_layout.addWidget(self.nodes_table)

        # Add/remove controls
        controls_layout = QHBoxLayout()
        self.new_node_input = QLineEdit()
        self.new_node_input.setPlaceholderText("IP or host (e.g. 134.122.79.166)")
        self.new_node_port = QLineEdit()
        self.new_node_port.setPlaceholderText("Public port (default 19009)")
        self.add_node_btn = QPushButton("Add Node")
        self.remove_node_btn = QPushButton("Remove Selected")
        self.refresh_nodes_btn = QPushButton("Refresh Status")

        controls_layout.addWidget(self.new_node_input)
        controls_layout.addWidget(self.new_node_port)
        controls_layout.addWidget(self.add_node_btn)
        controls_layout.addWidget(self.remove_node_btn)
        controls_layout.addWidget(self.refresh_nodes_btn)
        controls_layout.addStretch()
        network_layout.addLayout(controls_layout)

        # Options
        options_layout = QHBoxLayout()
        self.auto_refresh_check = QCheckBox("Auto-refresh balance")
        self.auto_refresh_check.setChecked(True)
        options_layout.addWidget(self.auto_refresh_check)
        options_layout.addStretch()
        network_layout.addLayout(options_layout)

        network_group.setLayout(network_layout)
        layout.addWidget(network_group)

        # Load nodes and populate table
        self._node_refresh_in_progress = False
        self.load_nodes_into_table()

        # Wire buttons
        self.add_node_btn.clicked.connect(self.add_node_clicked)
        self.remove_node_btn.clicked.connect(self.remove_selected_node)
        self.refresh_nodes_btn.clicked.connect(self.refresh_nodes_status)
        
        # Add spacer
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        self.setLayout(layout)
        # Auto-refresh node statuses shortly after loading
        QTimer.singleShot(500, self.refresh_nodes_status)
        # Periodically retry saved nodes every 2 minutes
        self.nodes_retry_timer = QTimer(self)
        self.nodes_retry_timer.timeout.connect(self.refresh_nodes_status)
        self.nodes_retry_timer.start(120000)

    def load_nodes_into_table(self):
        nodes = self.main_window.wallet_storage.get_nodes()
        self.nodes_table.setRowCount(len(nodes))
        for row, n in enumerate(nodes):
            self.nodes_table.setItem(row, 0, QTableWidgetItem(str(n.get('host', ''))))
            self.nodes_table.setItem(row, 1, QTableWidgetItem(str(n.get('public_port', 19009))))
            self.nodes_table.setItem(row, 2, QTableWidgetItem(str(n.get('wallet_port', 19010))))
            self.nodes_table.setItem(row, 3, QTableWidgetItem('Yes' if n.get('enabled', True) else 'No'))
            # Status placeholders
            self.nodes_table.setItem(row, 4, QTableWidgetItem('Checking...'))
            self.nodes_table.setItem(row, 5, QTableWidgetItem(''))
            self.nodes_table.setItem(row, 6, QTableWidgetItem(''))

    def add_node_clicked(self):
        host = self.new_node_input.text().strip()
        port_text = self.new_node_port.text().strip()
        if not host:
            QMessageBox.warning(self, "Input Error", "Please enter a node IP or host.")
            return
        try:
            public_port = int(port_text) if port_text else 19009
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Port must be a number.")
            return
        # Validate connectivity before saving
        try:
            test_client = QBitcoinAPIClient(nodes=[{
                'host': host,
                'public_port': public_port,
                'wallet_port': 19010,
                'enabled': True
            }])
            # Use a shorter timeout for responsiveness
            test_client.connection_timeout = 3
            status = test_client.get_node_status()
            if isinstance(status, dict) and status.get('connected'):
                # Persist and update api client
                self.main_window.wallet_storage.add_node(host, public_port=public_port)
                nodes = self.main_window.wallet_storage.get_nodes()
                self.main_window.api_client.set_nodes(nodes)
                self.load_nodes_into_table()
                QMessageBox.information(self, "Success", f"Connected to {host}:{public_port}. Node added.")
                self.refresh_nodes_status()
                self.new_node_input.clear()
                self.new_node_port.clear()
            else:
                error_msg = status.get('error', 'Unable to connect') if isinstance(status, dict) else 'Unable to connect'
                QMessageBox.critical(self, "Connection Failed", f"Could not connect to {host}:{public_port}.\n{error_msg}")
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Could not connect to {host}:{public_port}.\n{str(e)}")

    def remove_selected_node(self):
        row = self.nodes_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Selection", "Please select a node to remove.")
            return
        host = self.nodes_table.item(row, 0).text()
        port = int(self.nodes_table.item(row, 1).text())
        self.main_window.wallet_storage.remove_node(host, public_port=port)
        nodes = self.main_window.wallet_storage.get_nodes()
        self.main_window.api_client.set_nodes(nodes)
        self.load_nodes_into_table()

    def refresh_nodes_status(self):
        if self._node_refresh_in_progress:
            return
        self._node_refresh_in_progress = True

        class NodeStatusWorker(QThread):
            result_ready = pyqtSignal(list)

            def __init__(self, nodes):
                super().__init__()
                self.nodes = nodes

            def run(self):
                results = []  # list of dicts per node: {index, status, height, peers}
                for idx, n in enumerate(self.nodes):
                    host = n.get('host')
                    public_port = int(n.get('public_port', 19009))
                    wallet_port = int(n.get('wallet_port', 19010))
                    status_text = 'Offline'
                    height = ''
                    peers = ''
                    try:
                        probe = QBitcoinAPIClient(nodes=[{
                            'host': host,
                            'public_port': public_port,
                            'wallet_port': wallet_port,
                            'enabled': True
                        }])
                        probe.connection_timeout = 3
                        status = probe.get_node_status()
                        if isinstance(status, dict) and status.get('connected'):
                            info = status.get('node_info', {})
                            height = info.get('height', '')
                            peers = info.get('peers', '')
                            status_text = 'Connected'
                    except Exception:
                        status_text = 'Offline'
                    results.append({'index': idx, 'status': status_text, 'height': height, 'peers': peers})
                self.result_ready.emit(results)

        # Start worker
        nodes = self.main_window.wallet_storage.get_nodes()
        self._node_worker = NodeStatusWorker(nodes)
        self._node_worker.result_ready.connect(self._on_nodes_status_ready)
        self._node_worker.finished.connect(lambda: setattr(self, '_node_refresh_in_progress', False))
        self._node_worker.start()

    def _on_nodes_status_ready(self, results):
        # Ensure table has all saved nodes loaded
        self.load_nodes_into_table()
        for r in results:
            row = r['index']
            if row < self.nodes_table.rowCount():
                self.nodes_table.setItem(row, 4, QTableWidgetItem(str(r.get('status', 'Offline'))))
                self.nodes_table.setItem(row, 5, QTableWidgetItem(str(r.get('height', ''))))
                self.nodes_table.setItem(row, 6, QTableWidgetItem(str(r.get('peers', ''))))
    
    def backup_wallet(self):
        """Backup wallet file"""
        if hasattr(self.main_window, 'current_wallet') and self.main_window.current_wallet:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Wallet Backup", 
                f"{self.main_window.current_wallet.get('name', 'wallet')}_backup.json",
                "JSON Files (*.json)"
            )
            
            if file_path:
                try:
                    with open(file_path, 'w') as f:
                        json.dump(self.main_window.current_wallet, f, indent=2)
                    QMessageBox.information(self, "Success", "Wallet backed up successfully!")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to backup wallet: {str(e)}")
        else:
            QMessageBox.warning(self, "No Wallet", "Please open or create a wallet to back up.")


class CreateWalletDialog(QDialog):
    """Dialog for creating a new wallet"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Wallet")
        self.setModal(True)
        self.setFixedSize(400, 200)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter wallet name...")
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Enter password...")
        
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input.setPlaceholderText("Confirm password...")
        
        self.create_btn = QPushButton("Create Wallet")
        self.create_btn.clicked.connect(self.create_wallet)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        layout.addRow("Name:", self.name_input)
        layout.addRow("Password:", self.password_input)
        layout.addRow("Confirm:", self.confirm_password_input)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addRow("", button_layout)
        self.setLayout(layout)
    
    def create_wallet(self):
        """Validate and create wallet"""
        name = self.name_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_password_input.text()
        
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a wallet name.")
            return
        
        if not password:
            QMessageBox.warning(self, "Error", "Please enter a password.")
            return
        
        if password != confirm:
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            return
        
        if len(password) < 8:
            QMessageBox.warning(self, "Error", "Password must be at least 8 characters.")
            return
        
        self.wallet_data = {"name": name, "password": password}
        self.accept()


class QBitcoinWallet(QMainWindow):
    """Main wallet application window"""
    
    def __init__(self):
        super().__init__()
        self.current_wallet = None
        self.wallet_storage = WalletStorageManager()
        # Initialize API client with nodes from storage
        nodes = self.wallet_storage.config.get('nodes', [])
        self.api_client = QBitcoinAPIClient(nodes=nodes)
        self._pending_last_wallet = None
        
        # Check for existing wallets and prompt for password if needed
        self.setup_ui()
        self.apply_theme()
        
        # Load icon if available
        icon_path = Path(__file__).parent / "asessts" / "icon" / "icon(u).png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        
        # Cache last used wallet (no prompt on startup)
        QTimer.singleShot(100, self.check_for_existing_wallets)
    
    def setup_ui(self):
        """Setup the main UI"""
        self.setWindowTitle("QBitcoin Wallet - Quantum Resistant")
        self.setGeometry(100, 100, 1000, 700)
        
        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.create_wallet_btn = QPushButton("Create Wallet")
        self.create_wallet_btn.clicked.connect(self.create_wallet)
        
        self.import_wallet_btn = QPushButton("Import Wallet")
        self.import_wallet_btn.clicked.connect(self.import_wallet)
        
        self.open_wallet_btn = QPushButton("Open Wallet")
        self.open_wallet_btn.clicked.connect(self.show_wallet_selector)
        
        self.wallet_info_label = QLabel("No wallet loaded")
        self.wallet_info_label.setStyleSheet("font-weight: bold; color: #ffffff;")
        
        toolbar_layout.addWidget(self.create_wallet_btn)
        toolbar_layout.addWidget(self.import_wallet_btn)
        toolbar_layout.addWidget(self.open_wallet_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.wallet_info_label)
        
        layout.addLayout(toolbar_layout)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.info_tab = InfoTab(self)
        self.wallet_tab = WalletTab(self)
        self.send_tab = SendTab(self)
        self.receive_tab = ReceiveTab(self)
        self.settings_tab = SettingsTab(self)
        
        self.tab_widget.addTab(self.info_tab, "Info")
        self.tab_widget.addTab(self.wallet_tab, "Wallet")
        self.tab_widget.addTab(self.send_tab, "Send")
        self.tab_widget.addTab(self.receive_tab, "Receive")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        
        layout.addWidget(self.tab_widget)
        
        # Disable Send/Receive tabs until a wallet is loaded
        try:
            send_index = self.tab_widget.indexOf(self.send_tab)
            recv_index = self.tab_widget.indexOf(self.receive_tab)
            if send_index != -1:
                self.tab_widget.setTabEnabled(send_index, False)
            if recv_index != -1:
                self.tab_widget.setTabEnabled(recv_index, False)
        except Exception:
            pass
        
        # Prompt for last wallet only when user opens the Wallet tab
        try:
            self.tab_widget.currentChanged.connect(self.on_tab_changed)
        except Exception:
            pass
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def apply_theme(self):
        """Apply dark blue theme"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e3a5f;
                color: #ffffff;
            }
            
            QWidget {
                background-color: #1e3a5f;
                color: #ffffff;
            }
            
            QTabWidget::pane {
                border: 1px solid #2a4a6b;
                background-color: #2a4a6b;
            }
            
            QTabBar::tab {
                background-color: #1e3a5f;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            
            QTabBar::tab:selected {
                background-color: #2a4a6b;
                border-bottom: 2px solid #4CAF50;
            }
            
            QTabBar::tab:hover {
                background-color: #3a5a7b;
            }
            
            QPushButton {
                background-color: #2a4a6b;
                color: #ffffff;
                border: 1px solid #4a6a8b;
                padding: 8px 16px;
                border-radius: 5px;
                font-weight: bold;
            }
            
            QPushButton:hover {
                background-color: #3a5a7b;
            }
            
            QPushButton:pressed {
                background-color: #1a3a5b;
            }
            
            QLineEdit, QTextEdit {
                background-color: #2a4a6b;
                color: #ffffff;
                border: 1px solid #4a6a8b;
                padding: 5px;
                border-radius: 3px;
            }
            
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #4CAF50;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4a6a8b;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
            
            QTableWidget {
                background-color: #2a4a6b;
                color: #ffffff;
                gridline-color: #4a6a8b;
                border: 1px solid #4a6a8b;
            }
            
            QHeaderView::section {
                background-color: #1e3a5f;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #4a6a8b;
                font-weight: bold;
            }
            
            QProgressBar {
                background-color: #2a4a6b;
                border: 1px solid #4a6a8b;
                border-radius: 5px;
                text-align: center;
            }
            
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 5px;
            }
            
            QCheckBox {
                color: #ffffff;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            
            QCheckBox::indicator:unchecked {
                background-color: #2a4a6b;
                border: 1px solid #4a6a8b;
            }
            
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
        """)
    
    def create_wallet(self):
        """Create a new wallet"""
        dialog = CreateWalletDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            wallet_data = dialog.wallet_data
            
            # Show progress
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # Create worker thread
            self.worker = WalletWorker("create_wallet", **wallet_data)
            self.worker.progress.connect(self.progress_bar.setValue)
            self.worker.finished.connect(self.on_wallet_created)
            self.worker.error.connect(self.on_error)
            self.worker.start()
    
    def import_wallet(self):
        """Import an existing wallet"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Wallet", "", "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                # Ask for password
                password, ok = QInputDialog.getText(
                    self, "Enter Password", "Enter wallet password:",
                    QLineEdit.EchoMode.Password
                )
                
                if ok and password:
                    with open(file_path, 'r') as f:
                        wallet_data = json.load(f)
                    
                    # Verify password by trying to decrypt
                    try:
                        encryption = WalletEncryption()
                        # Get the encrypted private key data
                        encrypted_private_key = wallet_data.get('private_key_encrypted', {})
                        if not encrypted_private_key:
                            raise Exception("No encrypted private key found in wallet")
                        
                        # Try to decrypt to verify password
                        decrypted_private_key = encryption.decrypt_private_key(encrypted_private_key, password)
                        
                        # Password is correct, import wallet to storage
                        wallet_path = self.wallet_storage.import_wallet_file(file_path)
                        
                        self.current_wallet = wallet_data
                        self.update_ui_for_wallet()
                        
                        QMessageBox.information(
                            self, "Success", 
                            f"Wallet imported successfully!\nSaved to: {wallet_path}"
                        )
                        
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Invalid password or corrupted wallet file: {str(e)}")
                        
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import wallet: {str(e)}")
    
    def on_wallet_created(self, wallet_data):
        """Handle wallet creation completion"""
        self.progress_bar.setVisible(False)
        
        try:
            # Save wallet using storage manager
            wallet_path = self.wallet_storage.save_wallet(wallet_data)
            
            self.current_wallet = wallet_data
            self.update_ui_for_wallet()
            
            QMessageBox.information(
                self, "Success", 
                f"Wallet '{wallet_data['name']}' created successfully!\n"
                f"Address: {wallet_data['address'][:20]}...\n"
                f"Saved to: {wallet_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save wallet: {str(e)}")
    
    def on_error(self, error_message):
        """Handle worker thread errors"""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", error_message)
    
    def update_ui_for_wallet(self):
        """Update UI when a wallet is loaded"""
        if self.current_wallet:
            wallet_name = self.current_wallet.get("name", "Unknown")
            address = self.current_wallet.get("address", "")
            
            self.wallet_info_label.setText(f"Wallet: {wallet_name}")
            self.wallet_tab.update_wallet_info(self.current_wallet)
            self.receive_tab.update_address(address)
            self.info_tab.update_wallet_info()  # Update info tab
            
            self.statusBar().showMessage(f"Wallet loaded: {wallet_name}")
            
            # Enable Send/Receive tabs now that a wallet is loaded
            try:
                send_index = self.tab_widget.indexOf(self.send_tab)
                recv_index = self.tab_widget.indexOf(self.receive_tab)
                if send_index != -1:
                    self.tab_widget.setTabEnabled(send_index, True)
                if recv_index != -1:
                    self.tab_widget.setTabEnabled(recv_index, True)
            except Exception:
                pass
    
    def get_balance(self, address):
        """Get wallet balance using API"""
        try:
            self.statusBar().showMessage("Fetching balance...")
            
            # Use the balance worker for consistent API calls
            balance_worker = BalanceWorker(self.api_client, address)
            balance_worker.balance_ready.connect(lambda info: self.statusBar().showMessage(
                f"Balance: {info['balance']} QBC" if info['success'] else "Failed to fetch balance"
            ))
            balance_worker.error_occurred.connect(lambda error: self.statusBar().showMessage(f"Error: {error}"))
            balance_worker.start()
            
        except Exception as e:
            self.statusBar().showMessage(f"Balance fetch error: {str(e)}")
            logger.error(f"Error in get_balance: {e}")
    
    def check_for_existing_wallets(self):
        """Cache last used wallet name for later prompt on Wallet tab."""
        try:
            self._pending_last_wallet = self.wallet_storage.get_last_used_wallet()
        except Exception:
            self._pending_last_wallet = None

    def on_tab_changed(self, index):
        """Prompt for password every time Wallet tab is opened until wallet is loaded."""
        try:
            wallet_index = self.tab_widget.indexOf(self.wallet_tab)
        except Exception:
            wallet_index = -1
        # Keep prompting until wallet is loaded (don't clear _pending_last_wallet)
        if index == wallet_index and self.current_wallet is None and self._pending_last_wallet:
            self.open_wallet_with_password(self._pending_last_wallet)
    
    def show_wallet_selector(self):
        """Show dialog to select from existing wallets"""
        wallet_list = self.wallet_storage.get_wallet_list()
        if not wallet_list:
            return
        
        dialog = WalletSelectorDialog(wallet_list, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_wallet = dialog.get_selected_wallet()
            if selected_wallet:
                self.open_wallet_with_password(selected_wallet['name'])
    
    def open_wallet_with_password(self, wallet_name):
        """Open wallet after password verification"""
        password, ok = QInputDialog.getText(
            self, 
            "Enter Password", 
            f"Enter password for wallet '{wallet_name}':",
            QLineEdit.EchoMode.Password
        )
        
        if ok:
            # Validate that password is not empty
            if not password:
                QMessageBox.warning(self, "Error", "Please enter a password.")
                return
            
            try:
                # Load wallet from storage
                wallet_data = self.wallet_storage.load_wallet(wallet_name)
                
                # Verify password by trying to decrypt
                encryption = WalletEncryption()
                try:
                    # Get the encrypted private key data
                    encrypted_private_key = wallet_data.get('private_key_encrypted', {})
                    if not encrypted_private_key:
                        raise Exception("No encrypted private key found in wallet")
                    
                    # Try to decrypt to verify password
                    decrypted_private_key = encryption.decrypt_private_key(encrypted_private_key, password)
                    
                    # Password is correct, set as current wallet
                    self.current_wallet = wallet_data
                    self.update_ui_for_wallet()
                    
                    QMessageBox.information(self, "Success", f"Wallet '{wallet_name}' opened successfully!")
                    
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Invalid password! {str(e)}")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load wallet: {str(e)}")
    
    def save_current_wallet(self):
        """Save current wallet to storage"""
        if self.current_wallet:
            try:
                wallet_name = self.current_wallet.get('name', 'unnamed_wallet')
                self.wallet_storage.save_wallet(self.current_wallet, wallet_name)
                self.statusBar().showMessage("Wallet saved successfully")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save wallet: {str(e)}")


class WalletSelectorDialog(QDialog):
    """Dialog for selecting from existing wallets"""
    
    def __init__(self, wallet_list, parent=None):
        super().__init__(parent)
        self.wallet_list = wallet_list
        self.selected_wallet = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the wallet selector UI"""
        self.setWindowTitle("Select Wallet")
        self.setFixedSize(500, 400)
        
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Select a wallet to open:")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Wallet list
        self.wallet_table = QTableWidget()
        self.wallet_table.setColumnCount(4)
        self.wallet_table.setHorizontalHeaderLabels(["Name", "Address", "Created", "Last Used"])
        self.wallet_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.wallet_table.setAlternatingRowColors(True)
        
        # Populate table
        self.wallet_table.setRowCount(len(self.wallet_list))
        for row, wallet in enumerate(self.wallet_list):
            self.wallet_table.setItem(row, 0, QTableWidgetItem(wallet['name']))
            self.wallet_table.setItem(row, 1, QTableWidgetItem(wallet['address'][:20] + '...'))
            
            created_date = QTableWidgetItem()
            created_date.setText(time.strftime('%Y-%m-%d', time.localtime(wallet['created_at'])))
            self.wallet_table.setItem(row, 2, created_date)
            
            last_used_date = QTableWidgetItem()
            last_used_date.setText(time.strftime('%Y-%m-%d', time.localtime(wallet['last_accessed'])))
            self.wallet_table.setItem(row, 3, last_used_date)
        
        self.wallet_table.resizeColumnsToContents()
        layout.addWidget(self.wallet_table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self.open_wallet)
        
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self.delete_wallet)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.open_btn)
        button_layout.addWidget(self.delete_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def open_wallet(self):
        """Open selected wallet"""
        current_row = self.wallet_table.currentRow()
        if current_row >= 0:
            self.selected_wallet = self.wallet_list[current_row]
            self.accept()
        else:
            QMessageBox.warning(self, "Warning", "Please select a wallet to open.")
    
    def delete_wallet(self):
        """Delete selected wallet"""
        current_row = self.wallet_table.currentRow()
        if current_row >= 0:
            wallet = self.wallet_list[current_row]
            
            # First, ask for confirmation
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Are you sure you want to delete wallet '{wallet['name']}'?\nThis action cannot be undone!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Request password to verify ownership
                password, ok = QInputDialog.getText(
                    self, 
                    "Verify Password", 
                    f"Enter password for wallet '{wallet['name']}' to confirm deletion:",
                    QLineEdit.EchoMode.Password
                )
                
                if not ok:
                    # User cancelled password prompt
                    return
                
                if not password:
                    QMessageBox.warning(self, "Error", "Please enter a password.")
                    return
                
                # Get the storage manager from parent window
                parent_window = self.parent()
                if parent_window and hasattr(parent_window, 'wallet_storage'):
                    try:
                        # Load wallet data to verify password
                        wallet_data = parent_window.wallet_storage.load_wallet(wallet['name'])
                        
                        # Verify password by trying to decrypt the private key
                        encryption = WalletEncryption()
                        encrypted_private_key = wallet_data.get('private_key_encrypted', {})
                        
                        if not encrypted_private_key:
                            QMessageBox.critical(self, "Error", "Wallet data is corrupted.")
                            return
                        
                        try:
                            # Try to decrypt - this will raise an exception if password is wrong
                            decrypted_private_key = encryption.decrypt_private_key(encrypted_private_key, password)
                            
                            # Password is correct, proceed with deletion
                            success = parent_window.wallet_storage.delete_wallet(wallet['name'])
                            
                            if success:
                                # Remove from local list and table
                                self.wallet_list.pop(current_row)
                                self.wallet_table.removeRow(current_row)
                                QMessageBox.information(self, "Success", "Wallet deleted successfully.")
                            else:
                                QMessageBox.critical(self, "Error", "Failed to delete wallet from storage.")
                        
                        except Exception as e:
                            # Password verification failed
                            QMessageBox.critical(self, "Invalid Password", 
                                f"Incorrect password! Wallet deletion cancelled.\n\nError: {str(e)}")
                    
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to load wallet: {str(e)}")
                else:
                    QMessageBox.critical(self, "Error", "Cannot access wallet storage.")
        else:
            QMessageBox.warning(self, "Warning", "Please select a wallet to delete.")
    
    def get_selected_wallet(self):
        """Get the selected wallet"""
        return self.selected_wallet


class InfoTab(QWidget):
    """Info tab showing wallet and network information"""
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()
        
        # Timer for periodic updates - disabled by default to prevent freezing
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_network_info_async)
        # Don't start timer automatically
        
        # Auto-load network info on startup
        QTimer.singleShot(2000, self.update_network_info_async)
    
    def setup_ui(self):
        """Setup the info tab UI"""
        layout = QVBoxLayout()
        
        # Wallet Info Group
        wallet_group = QGroupBox("Wallet Information")
        wallet_layout = QGridLayout()
        
        self.wallet_path_label = QLabel("No wallet loaded")
        self.wallet_address_label = QLabel("No wallet loaded")
        self.wallet_created_label = QLabel("No wallet loaded")
        self.wallet_encrypted_label = QLabel("No wallet loaded")
        
        wallet_layout.addWidget(QLabel("Wallet Path:"), 0, 0)
        wallet_layout.addWidget(self.wallet_path_label, 0, 1)
        wallet_layout.addWidget(QLabel("Address:"), 1, 0)
        wallet_layout.addWidget(self.wallet_address_label, 1, 1)
        wallet_layout.addWidget(QLabel("Created:"), 2, 0)
        wallet_layout.addWidget(self.wallet_created_label, 2, 1)
        wallet_layout.addWidget(QLabel("Encrypted:"), 3, 0)
        wallet_layout.addWidget(self.wallet_encrypted_label, 3, 1)
        
        wallet_group.setLayout(wallet_layout)
        layout.addWidget(wallet_group)
        
        # Network Info Group
        network_group = QGroupBox("Network Information")
        network_layout = QGridLayout()
        
        self.node_status_label = QLabel("Checking...")
        self.block_height_label = QLabel("Checking...")
        self.peer_count_label = QLabel("Checking...")
        self.network_hashrate_label = QLabel("Checking...")
        self.last_block_label = QLabel("Checking...")
        
        network_layout.addWidget(QLabel("Node Status:"), 0, 0)
        network_layout.addWidget(self.node_status_label, 0, 1)
        network_layout.addWidget(QLabel("Block Height:"), 1, 0)
        network_layout.addWidget(self.block_height_label, 1, 1)
        network_layout.addWidget(QLabel("Connected Peers:"), 2, 0)
        network_layout.addWidget(self.peer_count_label, 2, 1)
        network_layout.addWidget(QLabel("Network Hashrate:"), 3, 0)
        network_layout.addWidget(self.network_hashrate_label, 3, 1)
        network_layout.addWidget(QLabel("Last Block:"), 4, 0)
        network_layout.addWidget(self.last_block_label, 4, 1)
        
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        # Storage Info Group
        storage_group = QGroupBox("Storage Information")
        storage_layout = QGridLayout()
        
        storage_info = self.main_window.wallet_storage.get_storage_info()
        
        self.storage_dir_label = QLabel(storage_info['storage_dir'])
        self.total_wallets_label = QLabel(str(storage_info['total_wallets']))
        self.last_used_wallet_label = QLabel(storage_info['last_used_wallet'] or "None")
        
        storage_layout.addWidget(QLabel("Storage Directory:"), 0, 0)
        storage_layout.addWidget(self.storage_dir_label, 0, 1)
        storage_layout.addWidget(QLabel("Total Wallets:"), 1, 0)
        storage_layout.addWidget(self.total_wallets_label, 1, 1)
        storage_layout.addWidget(QLabel("Last Used Wallet:"), 2, 0)
        storage_layout.addWidget(self.last_used_wallet_label, 2, 1)
        
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
        # Refresh button
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh Network Info")
        refresh_btn.clicked.connect(self.update_network_info_async)
        
        self.auto_refresh_checkbox = QCheckBox("Auto-refresh (30s)")
        self.auto_refresh_checkbox.stateChanged.connect(self.toggle_auto_refresh)
        
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(self.auto_refresh_checkbox)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_wallet_info(self):
        """Update wallet information display"""
        if self.main_window.current_wallet:
            wallet_data = self.main_window.current_wallet
            
            # Try to get wallet path from storage
            wallet_name = wallet_data.get('name', 'Unknown')
            storage_info = self.main_window.wallet_storage.get_storage_info()
            wallet_path = f"{storage_info['wallets_dir']}/{wallet_name}.json"
            
            self.wallet_path_label.setText(wallet_path)
            self.wallet_address_label.setText(wallet_data.get('address', 'Unknown'))
            
            created_time = wallet_data.get('created_at', 0)
            if created_time:
                created_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created_time))
                self.wallet_created_label.setText(created_str)
            else:
                self.wallet_created_label.setText("Unknown")
            
            encrypted = wallet_data.get('encrypted', False)
            self.wallet_encrypted_label.setText("Yes" if encrypted else "No")
        else:
            self.wallet_path_label.setText("No wallet loaded")
            self.wallet_address_label.setText("No wallet loaded")
            self.wallet_created_label.setText("No wallet loaded")
            self.wallet_encrypted_label.setText("No wallet loaded")
    
    def update_network_info(self):
        """Update network information from API"""
        try:
            # Get node status
            node_status = self.main_window.api_client.get_node_status()
            if isinstance(node_status, dict) and node_status.get('connected'):
                self.node_status_label.setText("Connected")
                node_info = node_status.get('node_info', {})
                
                # Update block height from node status
                height = node_info.get('height', 'Unknown')
                self.block_height_label.setText(str(height))
                
                # Update peer count from node status
                peers = node_info.get('peers', 'Unknown')
                self.peer_count_label.setText(str(peers))
            else:
                self.node_status_label.setText("Disconnected")
                self.block_height_label.setText("N/A")
                self.peer_count_label.setText("N/A")
            
            # Get chain stats
            try:
                chain_stats = self.main_window.api_client.get_chain_stats()
                if isinstance(chain_stats, dict):
                    # Handle various possible response formats
                    if 'success' in chain_stats and chain_stats.get('success'):
                        stats = chain_stats.get('data', {})
                    else:
                        stats = chain_stats
                    
                    # Update network hashrate if available
                    hashrate = stats.get('network_hashrate') or stats.get('hash_power', 'Unknown')
                    if hashrate != 'Unknown':
                        if isinstance(hashrate, (int, float)):
                            if hashrate > 1e12:
                                self.network_hashrate_label.setText(f"{hashrate/1e12:.2f} TH/s")
                            elif hashrate > 1e9:
                                self.network_hashrate_label.setText(f"{hashrate/1e9:.2f} GH/s")
                            elif hashrate > 1e6:
                                self.network_hashrate_label.setText(f"{hashrate/1e6:.2f} MH/s")
                            else:
                                self.network_hashrate_label.setText(f"{hashrate} H/s")
                        else:
                            self.network_hashrate_label.setText(str(hashrate))
                    else:
                        self.network_hashrate_label.setText("Unknown")
                    
                    # Update last block time if available
                    last_block_time = stats.get('last_block_timestamp') or stats.get('timestamp', 0)
                    if last_block_time and last_block_time > 0:
                        last_block_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_block_time))
                        self.last_block_label.setText(last_block_str)
                    else:
                        self.last_block_label.setText("Unknown")
                else:
                    self.network_hashrate_label.setText("Error")
                    self.last_block_label.setText("Error")
            except Exception as e:
                logger.error(f"Error getting chain stats: {e}")
                self.network_hashrate_label.setText("Error")
                self.last_block_label.setText("Error")
            
            # Get peer count (alternative method if not available from node status)
            try:
                peers_stat = self.main_window.api_client.get_peers_stat()
                if isinstance(peers_stat, list):
                    peer_count = len(peers_stat)
                    self.peer_count_label.setText(str(peer_count))
                elif isinstance(peers_stat, dict) and 'success' in peers_stat and peers_stat.get('success'):
                    peer_count = len(peers_stat.get('data', []))
                    self.peer_count_label.setText(str(peer_count))
            except Exception as e:
                logger.error(f"Error getting peer stats: {e}")
                # Keep existing peer count from node status if available
            
        except Exception as e:
            self.node_status_label.setText("Error connecting")
            self.block_height_label.setText("Error")
            self.peer_count_label.setText("Error")
            self.network_hashrate_label.setText("Error")
            self.last_block_label.setText("Error")
            logger.error(f"Error updating network info: {e}")
    
    def toggle_auto_refresh(self, state):
        """Toggle automatic refresh of network info"""
        if state == 2:  # Checked
            self.update_timer.start(30000)  # 30 seconds
        else:
            self.update_timer.stop()
    
    def update_network_info_async(self):
        """Update network information using worker thread"""
        # Show that we're updating
        self.node_status_label.setText("Updating...")
        self.block_height_label.setText("Updating...")
        self.peer_count_label.setText("Updating...")
        self.network_hashrate_label.setText("Updating...")
        self.last_block_label.setText("Updating...")
        
        # Start worker thread
        self.api_worker = ApiWorker(self.main_window.api_client)
        self.api_worker.network_info_ready.connect(self.on_network_info_ready)
        self.api_worker.error_occurred.connect(self.on_network_error)
        self.api_worker.start()
    
    def on_network_info_ready(self, network_info):
        """Handle network info from worker thread"""
        self.node_status_label.setText(network_info['node_status'])
        self.block_height_label.setText(network_info['block_height'])
        self.peer_count_label.setText(network_info['peer_count'])
        self.network_hashrate_label.setText(network_info['network_hashrate'])
        self.last_block_label.setText(network_info['last_block'])
    
    def on_network_error(self, error_message):
        """Handle network update errors"""
        self.node_status_label.setText("Error")
        self.block_height_label.setText("Error")
        self.peer_count_label.setText("Error")
        self.network_hashrate_label.setText("Error")
        self.last_block_label.setText("Error")
        logger.error(f"Network update error: {error_message}")


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Show splash screen
    splash = SplashScreen()
    splash.show()
    
    # Process events to show splash
    app.processEvents()
    
    # Create main window
    window = QBitcoinWallet()
    
    # Hide splash and show main window after delay
    QTimer.singleShot(3000, splash.close)
    QTimer.singleShot(3000, window.show)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
