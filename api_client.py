#!/usr/bin/env python3
"""
QBitcoin API Client - Real gRPC Implementation
=============================================

This module provides a real gRPC client for communicating with QBitcoin nodes.
 
"""

import grpc
import time
import json
import base64
import hashlib
import logging
import requests
from typing import Dict, Any, List, Optional



 

from generated import qbit_pb2, qbit_pb2_grpc
from falcon import FalconSignature

logger = logging.getLogger(__name__)


# Standalone address parsing functions (no external dependencies)
def parse_hexblob(blob: str) -> bytes:
    """
    Convert hexstring to bytes without external dependencies.
    :param blob: Hexadecimal string
    :return: bytes
    """
    return bytes.fromhex(blob)


def is_valid_falcon_address(address: bytes) -> bool:
    """
    Validate Falcon address format (standalone version)
    Only validate Falcon-512 addresses (25 bytes starting with 0x01)
    """
    if len(address) == 25 and address[0:1] == b'\x01':
        # This is a Falcon-512 generated address
        # Basic format validation - 25 bytes total, starts with 0x01
        return True
    return False


def parse_qaddress(qaddress: str, check_multi_sig_address=False) -> bytes:
    """
    Standalone version: Converts from a Qaddress to an Address.
    qaddress: 'Q' + hexstring representation of an address
    check_multi_sig_address: Flag if multi sig address should be checked (ignored for now)
    :param qaddress: Q-prefixed address string
    :param check_multi_sig_address: Currently ignored in standalone version
    :return: Address as bytes
    """
    try:
        # Remove the 'Q' prefix and convert hex to bytes
        if not qaddress.startswith('Q'):
            raise ValueError(f"Invalid address format: must start with 'Q', got: {qaddress}")
        
        # Convert hex string to bytes (remove Q prefix)
        address_bytes = parse_hexblob(qaddress[1:])
        
        # Validate address format (Falcon addresses only)
        if not is_valid_falcon_address(address_bytes):
            # For standalone version, we'll be more lenient and just check basic format
            if len(address_bytes) < 20:  # Minimum reasonable address length
                raise ValueError(f"Invalid address: too short ({len(address_bytes)} bytes)")
            # Allow addresses that don't strictly match Falcon format for compatibility
            
    except ValueError as e:
        raise ValueError(f"Failed to decode address '{qaddress}': {e}")
    except Exception as e:
        raise ValueError(f"Failed to decode address '{qaddress}': {e}")

    return address_bytes


class QBitcoinAPIClient:
    """Real API client for QBitcoin node communication using gRPC, with multi-node support."""
    
    def __init__(self, host='134.122.79.166', public_port=19009, wallet_port=19010, nodes: Optional[List[Dict[str, Any]]] = None):
        # Primary node
        self.host = host
        self.public_port = public_port
        self.wallet_port = wallet_port

        # Multi-node list: list of dicts with keys host, public_port, wallet_port, enabled
        # The first item is treated as primary if provided
        self.nodes: List[Dict[str, Any]] = []
        if nodes and isinstance(nodes, list):
            self.nodes = [
                {
                    'host': n.get('host', self.host),
                    'public_port': int(n.get('public_port', 19009)),
                    'wallet_port': int(n.get('wallet_port', 19010)),
                    'enabled': bool(n.get('enabled', True))
                }
                for n in nodes
            ]
        else:
            self.nodes = [{
                'host': self.host,
                'public_port': self.public_port,
                'wallet_port': self.wallet_port,
                'enabled': True
            }]
        self.connection_timeout = 10
        
        # We'll create stub connections when needed (per-node)
        self._public_stub = None
        self._wallet_stub = None
        self._public_channel = None
        self._wallet_channel = None
        self._active_node_index = 0  # index into self.nodes
        
        # Store pending transactions temporarily
        self._pending_transaction = None
        
        # Transaction deduplication - store recent transaction hashes to prevent duplicates
        self._recent_transactions = {}  # {tx_identifier: timestamp}
        self._tx_dedup_timeout = 30  # 30 seconds timeout for deduplication
    
    def _current_node(self) -> Dict[str, Any]:
        if not self.nodes:
            return {'host': self.host, 'public_port': self.public_port, 'wallet_port': self.wallet_port, 'enabled': True}
        # Ensure index is valid
        if self._active_node_index < 0 or self._active_node_index >= len(self.nodes):
            self._active_node_index = 0
        return self.nodes[self._active_node_index]

    def _switch_to_next_node(self):
        # Round-robin to next enabled node
        if not self.nodes:
            return
        start_index = self._active_node_index
        n = len(self.nodes)
        for i in range(1, n + 1):
            idx = (start_index + i) % n
            if self.nodes[idx].get('enabled', True):
                # Close existing connections
                self.close_connections()
                # Update primary fields for convenience
                node = self.nodes[idx]
                self.host = node['host']
                self.public_port = node['public_port']
                self.wallet_port = node['wallet_port']
                self._active_node_index = idx
                logger.info(f"Switched active node to {self.host}:{self.public_port}")
                return

    def set_nodes(self, nodes: List[Dict[str, Any]]):
        """Replace the node list and reset to the first enabled node."""
        self.nodes = [
            {
                'host': n.get('host', self.host),
                'public_port': int(n.get('public_port', 19009)),
                'wallet_port': int(n.get('wallet_port', 19010)),
                'enabled': bool(n.get('enabled', True))
            }
            for n in nodes
        ]
        # Reset active
        self._active_node_index = 0
        first_enabled = next((i for i, n in enumerate(self.nodes) if n.get('enabled', True)), None)
        if first_enabled is not None:
            self._active_node_index = first_enabled
            node = self.nodes[self._active_node_index]
            self.host = node['host']
            self.public_port = node['public_port']
            self.wallet_port = node['wallet_port']
        # Close existing connections to reconnect lazily
        self.close_connections()

    def add_node(self, host: str, public_port: int = 19009, wallet_port: int = 19010, enabled: bool = True):
        self.nodes.append({'host': host, 'public_port': int(public_port), 'wallet_port': int(wallet_port), 'enabled': bool(enabled)})
        if self.nodes and not self.nodes[self._active_node_index].get('enabled', True):
            self._switch_to_next_node()

    def get_active_node(self) -> Dict[str, Any]:
        return self._current_node()

    def _get_public_stub(self):
        """Get PublicAPI gRPC stub"""
        if not self._public_stub:
            try:
                node = self._current_node()
                self._public_channel = grpc.insecure_channel(f"{node['host']}:{node['public_port']}")
                grpc.channel_ready_future(self._public_channel).result(timeout=self.connection_timeout)
                self._public_stub = qbit_pb2_grpc.PublicAPIStub(self._public_channel)
                logger.info(f"Connected to PublicAPI at {node['host']}:{node['public_port']}")
            except Exception as e:
                logger.error(f"Failed to connect to PublicAPI: {e}")
                raise
        return self._public_stub
    
    def _get_wallet_stub(self):
        """Get WalletAPI gRPC stub (if available)"""
        # Note: Wallet API might not be available on all nodes
        # For now, we'll use the PublicAPI for most operations
        return self._get_public_stub()
    
    def close_connections(self):
        """Close gRPC connections"""
        if self._public_channel:
            self._public_channel.close()
        if self._wallet_channel:
            self._wallet_channel.close()
        self._public_stub = None
        self._wallet_stub = None
        self._public_channel = None
        self._wallet_channel = None
    
    def get_node_status(self) -> Dict[str, Any]:
        """Get node status and information"""
        last_error = None
        tried = 0
        max_attempts = len(self.nodes) if self.nodes else 1
        while tried < max_attempts:
            try:
                stub = self._get_public_stub()
                request = qbit_pb2.GetNodeStateReq()
                response = stub.GetNodeState(request)
                return {
                    'node_info': {
                        'version': response.info.version,
                        'network': response.info.network_id,
                        'synced': response.info.state == qbit_pb2.NodeInfo.SYNCED,
                        'height': response.info.block_height,
                        'peers': response.info.num_connections
                    },
                    'connected': True,
                    'timestamp': int(time.time())
                }
            except Exception as e:
                last_error = e
                logger.error(f"Error getting node status from {self.host}:{self.public_port}: {e}")
                tried += 1
                if tried < max_attempts:
                    self._switch_to_next_node()
                else:
                    break
        return {
            'connected': False,
            'error': str(last_error) if last_error else 'Unknown error'
        }
    
    def get_balance(self, address: str) -> Dict[str, Any]:
        """Get balance for a specific address"""
        try:
            stub = self._get_public_stub()
           
            
            # Use the same address parsing as CLI
            address_bytes = parse_qaddress(address)
            
            # Try GetOptimizedAddressState first (like CLI method 2)
            try:
                 
                request = qbit_pb2.GetAddressStateReq()
                request.address = address_bytes
                response = stub.GetOptimizedAddressState(request)
                
                 
                if response.state:
                    balance_result = {
                        'address': address,
                        'balance': response.state.balance,
                        'unconfirmed_balance': 0,  # QBitcoin doesn't separate unconfirmed
                        'nonce': response.state.nonce
                    }
                    logger.info(f"Balance result from GetOptimizedAddressState: {balance_result}")
                    return balance_result
                else:
                    logger.info("GetOptimizedAddressState returned no state - address doesn't exist")
                    # Address doesn't exist yet
                    return {
                        'address': address,
                        'balance': 0,
                        'unconfirmed_balance': 0,
                        'nonce': 0
                    }
            except Exception as e:
                logger.error(f"GetOptimizedAddressState failed: {e}")
                # Fallback to simple GetBalance (like CLI method 1)
                logger.info("Trying GetBalance as fallback...")
                request = qbit_pb2.GetBalanceReq()
                request.address = address_bytes
                response = stub.GetBalance(request)
                
                 
                
                balance_result = {
                    'address': address,
                    'balance': response.balance,
                    'unconfirmed_balance': 0,  # QBitcoin doesn't separate unconfirmed
                    'nonce': 0  # We'll get this from address state if needed
                }
                 
                return balance_result
        except Exception as e:
            logger.error(f"Error getting balance for {address}: {e}")
            raise
    
    def get_address_state(self, address: str) -> Dict[str, Any]:
        """Get full address state including nonce"""
        try:
            stub = self._get_public_stub()
            
            # Use the same address parsing as CLI
            address_bytes = parse_qaddress(address)
            
            request = qbit_pb2.GetAddressStateReq()
            request.address = address_bytes
            
            response = stub.GetAddressState(request)
            
            if response.state:
                return {
                    'address': address,
                    'balance': response.state.balance,
                    'nonce': response.state.nonce,
                    'transaction_count': len(response.state.transaction_hashes)
                }
            else:
                # Address doesn't exist yet
                return {
                    'address': address,
                    'balance': 0,
                    'nonce': 0,
                    'transaction_count': 0
                }
        except Exception as e:
            logger.error(f"Error getting address state for {address}: {e}")
            raise
    
    def get_transactions_by_address(self, address: str, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Get transaction history for an address - returns ALL transactions"""
        try:
            stub = self._get_public_stub()
            
            # Use the same address parsing as CLI
            address_bytes = parse_qaddress(address)
            
            request = qbit_pb2.GetTransactionsByAddressReq()
            request.address = address_bytes
            # Get all transactions - set a very high number for item_per_page
            request.item_per_page = 10000  # This should get all transactions
            request.page_number = 1  # Always get from first page
            
            response = stub.GetTransactionsByAddress(request)
            
            transactions = []
            for tx_detail in response.transactions_detail:
                if tx_detail.tx:
                    tx_info = {
                        'tx_hash': tx_detail.tx.transaction_hash.hex(),
                        'type': self._get_transaction_type(tx_detail.tx),
                        'amount': self._get_transaction_amount(tx_detail.tx),  # Total transaction amount
                        'address_amount': self._get_address_specific_amount(tx_detail.tx, address),  # Amount specific to this address
                        'fee': tx_detail.tx.fee,
                        'from_address': 'Q' + tx_detail.addr_from.hex() if tx_detail.addr_from else '',
                        'to_address': self._get_transaction_to_address(tx_detail.tx),
                        'outputs': self._get_transaction_outputs(tx_detail.tx),  # Add all outputs
                        'timestamp': tx_detail.timestamp,
                        'block_number': tx_detail.block_number,
                        'confirmations': 1  # We can calculate this if needed
                    }
                    transactions.append(tx_info)
            
            return {
                'transactions': transactions,
                'total_count': len(transactions),
                'page': 1,
                'per_page': len(transactions),
                'total_pages': 1
            }
        except Exception as e:
            logger.error(f"Error getting transactions for {address}: {e}")
            raise
    
    def _get_transaction_type(self, tx) -> str:
        """Determine transaction type from protobuf transaction"""
        if tx.HasField('transfer'):
            return 'transfer'
        elif tx.HasField('coinbase'):
            return 'coinbase'
        elif tx.HasField('token'):
            return 'token'
        elif tx.HasField('transfer_token'):
            return 'transfer_token'
        elif tx.HasField('message'):
            return 'message'
        elif tx.HasField('slave'):
            return 'slave'
        elif tx.HasField('multi_sig_create'):
            return 'multi_sig_create'
        elif tx.HasField('multi_sig_spend'):
            return 'multi_sig_spend'
        elif tx.HasField('multi_sig_vote'):
            return 'multi_sig_vote'
        else:
            return 'unknown'
    
    def _get_transaction_amount(self, tx) -> int:
        """Get transaction amount based on type"""
        if tx.HasField('transfer'):
            return sum(tx.transfer.amounts)
        elif tx.HasField('coinbase'):
            return tx.coinbase.amount
        elif tx.HasField('transfer_token'):
            return sum(tx.transfer_token.amounts)
        else:
            return 0
    
    def _get_transaction_to_address(self, tx) -> str:
        """Get recipient address from transaction (first address for backward compatibility)"""
        if tx.HasField('transfer') and tx.transfer.addrs_to:
            return 'Q' + tx.transfer.addrs_to[0].hex()
        elif tx.HasField('coinbase'):
            return 'Q' + tx.coinbase.addr_to.hex()
        elif tx.HasField('transfer_token') and tx.transfer_token.addrs_to:
            return 'Q' + tx.transfer_token.addrs_to[0].hex()
        else:
            return ''
    
    def _get_transaction_outputs(self, tx) -> List[Dict[str, Any]]:
        """Get all transaction outputs with addresses and amounts"""
        outputs = []
        
        if tx.HasField('transfer'):
            for i, addr_to in enumerate(tx.transfer.addrs_to):
                if i < len(tx.transfer.amounts):
                    outputs.append({
                        'address': 'Q' + addr_to.hex(),
                        'amount': tx.transfer.amounts[i]
                    })
        elif tx.HasField('coinbase'):
            outputs.append({
                'address': 'Q' + tx.coinbase.addr_to.hex(),
                'amount': tx.coinbase.amount
            })
        elif tx.HasField('transfer_token'):
            for i, addr_to in enumerate(tx.transfer_token.addrs_to):
                if i < len(tx.transfer_token.amounts):
                    outputs.append({
                        'address': 'Q' + addr_to.hex(),
                        'amount': tx.transfer_token.amounts[i]
                    })
                    
        return outputs
    def _get_address_specific_amount(self, tx, address: str) -> int:
        """Get the amount specific to an address in a transaction"""
        # For transactions where this address is the sender
        if tx.HasField('transfer') and tx.master_addr:
            sender_address = 'Q' + tx.master_addr.hex()
            if sender_address == address:
                # This address is sending, return negative total amount
                return -sum(tx.transfer.amounts)
        
        # For transactions where this address is a recipient
        if tx.HasField('transfer') and tx.transfer.addrs_to:
            for i, addr_to in enumerate(tx.transfer.addrs_to):
                recipient_address = 'Q' + addr_to.hex()
                if recipient_address == address and i < len(tx.transfer.amounts):
                    # This address is receiving, return the specific amount
                    return tx.transfer.amounts[i]
        
        # For coinbase transactions
        if tx.HasField('coinbase'):
            recipient_address = 'Q' + tx.coinbase.addr_to.hex()
            if recipient_address == address:
                return tx.coinbase.amount
        
        # For token transfers
        if tx.HasField('transfer_token') and tx.transfer_token.addrs_to:
            for i, addr_to in enumerate(tx.transfer_token.addrs_to):
                recipient_address = 'Q' + addr_to.hex()
                if recipient_address == address and i < len(tx.transfer_token.amounts):
                    return tx.transfer_token.amounts[i]
        
        # Default case - return total amount (for backward compatibility)
        return self._get_transaction_amount(tx)
    
    def create_transfer_transaction(self, wallet: Dict[str, Any], to_address: str, 
                                  amount: int, fee: int, message: str = '') -> Dict[str, Any]:
        """Create and sign a transfer transaction"""
        try:
            from_address = wallet['address']
            private_key = wallet['private_key']
            public_key = wallet['public_key']
            
            # Get current address state to get nonce
            addr_state = self.get_address_state(from_address)
            nonce = addr_state['nonce'] + 1
            
            # Convert addresses to bytes
            if from_address.startswith('Q'):
                from_addr_bytes = bytes.fromhex(from_address[1:])
            else:
                from_addr_bytes = from_address.encode()
                
            if to_address.startswith('Q'):
                to_addr_bytes = bytes.fromhex(to_address[1:])
            else:
                to_addr_bytes = to_address.encode()
            
            # Get public key bytes
            public_key_bytes = base64.b64decode(public_key)
            
            # Use the PublicAPI to create the transaction
            stub = self._get_public_stub()
            
            request = qbit_pb2.TransferCoinsReq()
            request.master_addr = from_addr_bytes
            request.addresses_to.append(to_addr_bytes)
            request.amounts.append(amount)
            request.fee = fee
            request.xmss_pk = public_key_bytes
            
            if message:
                request.message_data = message.encode()
            
            response = stub.TransferCoins(request)
            
            if response.extended_transaction_unsigned:
                # Sign the transaction
                tx = response.extended_transaction_unsigned.tx
                tx.nonce = nonce
                
                # Create transaction hash for signing using the exact node format
                tx_hash = self._calculate_transaction_hash_bytes(tx)
                
                # Sign with Falcon
                signature = self._sign_transaction(tx_hash, private_key)
                tx.signature = base64.b64decode(signature)
                tx.public_key = public_key_bytes
                
                # Push the signed transaction
                push_request = qbit_pb2.PushTransactionReq()
                push_request.transaction_signed.CopyFrom(tx)
                
                push_response = stub.PushTransaction(push_request)
                
                if push_response.error_code == qbit_pb2.PushTransactionResp.SUBMITTED:
                    return {
                        'tx_hash': push_response.tx_hash.hex(),
                        'status': 'submitted',
                        'transaction': {
                            'from_address': from_address,
                            'to_address': to_address,
                            'amount': amount,
                            'fee': fee,
                            'nonce': nonce
                        }
                    }
                else:
                    raise Exception(f"Transaction failed: {push_response.error_description}")
            else:
                raise Exception("Failed to create transaction")
            
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            raise
    
    def create_transfer_transaction_secure(self, from_address: str, to_address: str, 
                                          amount: int, fee: int, public_key_hex: str, 
                                          private_key: str = None, message: str = '') -> Dict[str, Any]:
        """Create and sign a transfer transaction securely - with private key for signing"""
        try:
            # Create a unique identifier for this transaction to prevent duplicates
            tx_identifier = f"{from_address}:{to_address}:{amount}:{fee}:{message}"
            tx_hash_id = hashlib.sha256(tx_identifier.encode()).hexdigest()
            
            # Check for recent duplicate transactions
            current_time = time.time()
            if tx_hash_id in self._recent_transactions:
                time_diff = current_time - self._recent_transactions[tx_hash_id]
                if time_diff < self._tx_dedup_timeout:
                    logger.warning(f"Duplicate transaction detected within {time_diff:.1f}s, ignoring")
                    raise Exception(f"Duplicate transaction detected. Please wait {self._tx_dedup_timeout - time_diff:.1f}s before retrying")
            
            # Clean up old transaction records
            self._recent_transactions = {k: v for k, v in self._recent_transactions.items() 
                                       if current_time - v < self._tx_dedup_timeout}
            
            # Mark this transaction as being processed
            self._recent_transactions[tx_hash_id] = current_time
            
            # Get current address state to get nonce
            addr_state = self.get_address_state(from_address)
            nonce = addr_state['nonce'] + 1
            
            logger.info(f"Creating transaction with nonce: {nonce}")
            
            # Convert addresses to bytes
            if from_address.startswith('Q'):
                from_addr_bytes = bytes.fromhex(from_address[1:])
            else:
                from_addr_bytes = from_address.encode()
                
            if to_address.startswith('Q'):
                to_addr_bytes = bytes.fromhex(to_address[1:])
            else:
                to_addr_bytes = to_address.encode()
            
            # Convert public key from hex to bytes
            try:
                public_key_bytes = bytes.fromhex(public_key_hex)
                logger.info(f"Public key converted from hex, size: {len(public_key_bytes)} bytes")
            except ValueError as e:
                logger.error(f"Invalid public key hex format: {e}")
                raise ValueError(f"Invalid public key format: {e}")
            
            # Use the PublicAPI to create the transaction
            stub = self._get_public_stub()
            
            request = qbit_pb2.TransferCoinsReq()
            request.master_addr = from_addr_bytes
            request.addresses_to.append(to_addr_bytes)
            request.amounts.append(amount)
            request.fee = fee
            request.xmss_pk = public_key_bytes
            
            if message:
                request.message_data = message.encode()
            
            logger.info(f"Sending TransferCoins request to node...")
            response = stub.TransferCoins(request)
            
            if response.extended_transaction_unsigned:
                # Get the unsigned transaction
                tx = response.extended_transaction_unsigned.tx
                tx.nonce = nonce
                
                logger.info(f"Unsigned transaction created successfully")
                
                # If private key is provided, sign and submit the transaction
                if private_key:
                    # Create transaction hash for signing using the exact node format
                    tx_hash = self._calculate_transaction_hash_bytes(tx)
                    
                    # Convert private key from hex to base64 format (for compatibility with _sign_transaction)
                    if isinstance(private_key, str) and len(private_key) % 2 == 0:
                        try:
                            # Assume it's hex and convert to base64
                            private_key_bytes = bytes.fromhex(private_key)
                            private_key_b64 = base64.b64encode(private_key_bytes).decode()
                        except ValueError:
                            # If not hex, assume it's already base64
                            private_key_b64 = private_key
                    else:
                        private_key_b64 = private_key
                    
                    # Sign the transaction using the same method as the working version
                    signature_b64 = self._sign_transaction(tx_hash, private_key_b64)
                    
                    # Set signature and public key in transaction (convert signature from base64 to bytes)
                    tx.signature = base64.b64decode(signature_b64)
                    tx.public_key = public_key_bytes
                    
                    signature_bytes = tx.signature
                    logger.info(f"Transaction signed with Falcon, signature size: {len(signature_bytes)} bytes")
                    
                    # Verify signature before submitting
                    public_key_b64 = base64.b64encode(public_key_bytes).decode()
                    if not self.verify_transaction_signature(tx_hash, signature_b64, public_key_b64):
                        error_msg = "Signature verification failed before submission"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    
                    logger.info("Signature verified successfully before submission")
                    
                    # Push the signed transaction to the network
                    push_request = qbit_pb2.PushTransactionReq()
                    push_request.transaction_signed.CopyFrom(tx)
                    
                    logger.info("Submitting signed transaction to network...")
                    push_response = stub.PushTransaction(push_request)
                    
                    if push_response.error_code == qbit_pb2.PushTransactionResp.SUBMITTED:
                        tx_hash_hex = push_response.tx_hash.hex()
                        logger.info(f"Transaction successfully submitted to network with hash: {tx_hash_hex}")
                        
                        return {
                            'success': True,
                            'tx_hash': tx_hash_hex,
                            'status': 'submitted',
                            'transaction': {
                                'from_address': from_address,
                                'to_address': to_address,
                                'amount': amount,
                                'fee': fee,
                                'nonce': nonce,
                                'public_key_size': len(public_key_bytes),
                                'signature_size': len(signature_bytes),
                                'total_size': len(public_key_bytes) + len(signature_bytes),
                                'message': message,
                                'timestamp': int(time.time())
                            }
                        }
                    else:
                        error_msg = push_response.error_description or f"Error code: {push_response.error_code}"
                        logger.error(f"Transaction submission failed: {error_msg}")
                        raise Exception(f"Transaction submission failed: {error_msg}")
                else:
                    # If no private key provided, return unsigned transaction (for external signing)
                    # Generate a deterministic transaction hash for tracking
                    tx_data = f"{from_address}{to_address}{amount}{fee}{nonce}{time.time()}"
                    tx_hash = hashlib.sha256(tx_data.encode()).hexdigest()
                    
                    logger.warning("No private key provided - returning unsigned transaction")
                    return {
                        'success': False,
                        'error': 'Private key required for transaction signing',
                        'unsigned_tx_hash': tx_hash
                    }
            else:
                logger.error("Failed to create unsigned transaction")
                raise Exception("Failed to create transaction")
            
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            raise
    
    def create_unsigned_transaction(self, from_address: str, to_address: str, 
                                   amount: int, fee: int, public_key_hex: str, message: str = '') -> Dict[str, Any]:
        """Create an unsigned transaction and return transaction data for signing"""
        try:
            # Get current address state to get nonce
            addr_state = self.get_address_state(from_address)
            nonce = addr_state['nonce'] + 1
            
            logger.info(f"Creating unsigned transaction with nonce: {nonce}")
            
            # Convert addresses to bytes
            if from_address.startswith('Q'):
                from_addr_bytes = bytes.fromhex(from_address[1:])
            else:
                from_addr_bytes = from_address.encode()
                
            if to_address.startswith('Q'):
                to_addr_bytes = bytes.fromhex(to_address[1:])
            else:
                to_addr_bytes = to_address.encode()
            
            # Convert public key from hex to bytes
            try:
                public_key_bytes = bytes.fromhex(public_key_hex)
                logger.info(f"Public key converted from hex, size: {len(public_key_bytes)} bytes")
            except ValueError as e:
                logger.error(f"Invalid public key hex format: {e}")
                raise ValueError(f"Invalid public key format: {e}")
            
            # Use the PublicAPI to create the transaction
            stub = self._get_public_stub()
            
            request = qbit_pb2.TransferCoinsReq()
            request.master_addr = from_addr_bytes
            request.addresses_to.append(to_addr_bytes)
            request.amounts.append(amount)
            request.fee = fee
            request.xmss_pk = public_key_bytes
            
            if message:
                request.message_data = message.encode()
            
            logger.info(f"Sending TransferCoins request to node...")
            response = stub.TransferCoins(request)
            
            if response.extended_transaction_unsigned:
                # Get the unsigned transaction
                tx = response.extended_transaction_unsigned.tx
                tx.nonce = nonce
                
                # Calculate transaction hash for signing
                tx_hash = self._calculate_transaction_hash_for_signing(tx)
                
                # Log transaction details for debugging
                logger.info(f"Transaction created - nonce: {nonce}, fee: {fee}")
                logger.info(f"From: {from_addr_bytes.hex()}, To: {to_addr_bytes.hex()}")
                logger.info(f"Amount: {amount}, Message: '{message}'")
                logger.info(f"Public key size: {len(public_key_bytes)} bytes")
                
                # Prepare transaction data for client-side signing (without protobuf objects)
                tx_data = {
                    'nonce': nonce,
                    'from_addr_bytes': from_addr_bytes.hex(),
                    'to_addr_bytes': to_addr_bytes.hex(),
                    'amount': amount,
                    'fee': fee,
                    'public_key_hex': public_key_hex,
                    'message': message
                }
                
                # Store the protobuf transaction temporarily (we'll reconstruct it during submission)
                self._pending_transaction = response.extended_transaction_unsigned
                
                logger.info(f"Unsigned transaction created successfully, hash: {tx_hash}")
                
                return {
                    'tx_hash': tx_hash,
                    'tx_data': tx_data
                }
            else:
                logger.error("Failed to create unsigned transaction")
                raise Exception("Failed to create unsigned transaction")
            
        except Exception as e:
            logger.error(f"Error creating unsigned transaction: {e}")
            raise
    
    def submit_signed_transaction(self, transaction_data: Dict[str, Any], 
                                 signature: str, public_key_hex: str) -> Dict[str, Any]:
        """Submit a signed transaction to the network"""
        try:
            logger.info(f"Submitting signed transaction to network...")
            
            # Convert signature from hex to bytes
            signature_bytes = bytes.fromhex(signature)
            public_key_bytes = bytes.fromhex(public_key_hex)
            
            # First, verify the signature before submitting to avoid rejection
            if not self._verify_transaction_signature(transaction_data, signature_bytes, public_key_bytes):
                logger.error("Signature verification failed before submission")
                raise Exception("Invalid signature - verification failed before submission")
            
            logger.info("Signature verified successfully before submission")
            
            stub = self._get_public_stub()
            
            # Use the stored pending transaction if available
            if self._pending_transaction:
                logger.info("Using stored pending transaction")
                # Get the transaction from the stored extended transaction
                tx = self._pending_transaction.tx
                
                # Set the signature and public key
                tx.signature = signature_bytes
                tx.public_key = public_key_bytes
                tx.nonce = transaction_data['nonce']
                
                # Ensure message data consistency
                if transaction_data.get('message') and transaction_data['message'].strip():
                    if hasattr(tx, 'transfer') and tx.transfer:
                        tx.transfer.message_data = transaction_data['message'].encode()
                
                # Create the push request
                request = qbit_pb2.PushTransactionReq()
                request.transaction_signed.CopyFrom(tx)
                
                # Log the stored transaction details for debugging
                logger.info(f"Using stored transaction - nonce: {tx.nonce}, fee: {tx.fee}")
                if hasattr(tx, 'transfer') and tx.transfer and tx.transfer.addrs_to:
                    logger.info(f"From: {tx.master_addr.hex()}, To: {tx.transfer.addrs_to[0].hex()}")
                    logger.info(f"Amount: {tx.transfer.amounts[0] if tx.transfer.amounts else 'None'}")
                    logger.info(f"Message: {tx.transfer.message_data.decode() if tx.transfer.message_data else 'None'}")
                
                # Clear the pending transaction
                self._pending_transaction = None
                
            else:
                logger.info("Reconstructing transaction from data")
                # Reconstruct the transaction manually - ensure consistency with hash calculation
                request = qbit_pb2.PushTransactionReq()
                
                # Build the complete transaction - matching the exact format used for hash calculation
                tx = qbit_pb2.Transaction()
                tx.master_addr = bytes.fromhex(transaction_data['from_addr_bytes'])
                tx.fee = transaction_data['fee']
                tx.public_key = public_key_bytes
                tx.signature = signature_bytes
                tx.nonce = transaction_data['nonce']
                
                # Add transfer details - ensure exactly same format as hash calculation
                transfer = tx.transfer
                transfer.addrs_to.append(bytes.fromhex(transaction_data['to_addr_bytes']))
                transfer.amounts.append(transaction_data['amount'])
                
                # Handle message data consistently
                if transaction_data.get('message') and transaction_data['message'].strip():
                    transfer.message_data = transaction_data['message'].encode()
                
                request.transaction_signed.CopyFrom(tx)
                
                # Log the reconstructed transaction details for debugging
                logger.info(f"Reconstructed transaction - nonce: {tx.nonce}, fee: {tx.fee}")
                logger.info(f"From: {tx.master_addr.hex()}, To: {transfer.addrs_to[0].hex()}")
                logger.info(f"Amount: {transfer.amounts[0]}, Message: {transfer.message_data.decode() if transfer.message_data else 'None'}")
            
            logger.info(f"Sending PushTransaction request to node...")
            response = stub.PushTransaction(request)
            
            # Enhanced error handling with detailed logging
            logger.info(f"PushTransaction response received - error_code: {response.error_code}")
            
            if response.error_code == qbit_pb2.PushTransactionResp.SUBMITTED:
                tx_hash = response.tx_hash.hex()
                logger.info(f"Transaction submitted successfully: {tx_hash}")
                
                return {
                    'tx_hash': tx_hash,
                    'status': 'submitted'
                }
            else:
                # Map error codes to readable descriptions
                error_descriptions = {
                    qbit_pb2.PushTransactionResp.VALIDATION_FAILED: "Transaction validation failed",
                    qbit_pb2.PushTransactionResp.INVALID_SIGNATURE: "Invalid signature", 
                    qbit_pb2.PushTransactionResp.INSUFFICIENT_BALANCE: "Insufficient balance",
                    qbit_pb2.PushTransactionResp.INVALID_NONCE: "Invalid nonce",
                    qbit_pb2.PushTransactionResp.INVALID_FEE: "Invalid fee",
                    qbit_pb2.PushTransactionResp.DUPLICATE_TRANSACTION: "Duplicate transaction"
                }
                
                error_description = error_descriptions.get(response.error_code, "Unknown error")
                error_msg = f"Transaction submission failed: {error_description} (code: {response.error_code})"
                
                if hasattr(response, 'error_description') and response.error_description:
                    error_msg += f" - Details: {response.error_description}"
                    
                logger.error(error_msg)
                raise Exception(error_msg)
            
        except Exception as e:
            logger.error(f"Error submitting signed transaction: {e}")
            raise
    
    def _calculate_transaction_hash(self, tx) -> bytes:
        """Calculate transaction hash for signing"""
        # This is a simplified hash calculation
        # In a real implementation, you'd need to match QBitcoin's exact hashing method
        tx_data = {
            'master_addr': tx.master_addr.hex() if tx.master_addr else '',
            'fee': tx.fee,
            'nonce': tx.nonce
        }
        
        if tx.HasField('transfer'):
            tx_data['transfer'] = {
                'addrs_to': [addr.hex() for addr in tx.transfer.addrs_to],
                'amounts': list(tx.transfer.amounts)
            }
        
        tx_json = json.dumps(tx_data, sort_keys=True).encode()
        return hashlib.sha256(tx_json).digest()
    
    def _sign_transaction(self, tx_hash: bytes, private_key: str) -> str:
        """Sign transaction hash with Falcon private key"""
        try:
            # Decode private key from base64
            private_key_bytes = base64.b64decode(private_key)
            
            # Sign with Falcon using the correct method
            signature_bytes = FalconSignature.sign_message(tx_hash, private_key_bytes)
            
            # Return signature as base64
            return base64.b64encode(signature_bytes).decode()
            
        except Exception as e:
            logger.error(f"Error signing transaction: {e}")
            raise
    
    def verify_transaction_signature(self, tx_hash: bytes, signature: str, public_key: str) -> bool:
        """Verify transaction signature"""
        try:
            # Decode keys and signature from base64
            public_key_bytes = base64.b64decode(public_key)
            signature_bytes = base64.b64decode(signature)
            
            # Verify with Falcon using the correct method
            return FalconSignature.verify_signature(tx_hash, signature_bytes, public_key_bytes)
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    def get_address_from_public_key(self, public_key: str) -> str:
        """Generate address from public key using the node"""
        try:
            stub = self._get_public_stub()
            
            # Decode public key
            public_key_bytes = base64.b64decode(public_key)
            
            request = qbit_pb2.GetAddressFromPKReq()
            request.pk = public_key_bytes
            
            response = stub.GetAddressFromPK(request)
            
            # Convert address bytes to QRL format
            address = 'Q' + response.address.hex().upper()
            
            return address
            
        except Exception as e:
            logger.error(f"Error getting address from public key: {e}")
            # Fallback to local calculation
            return self._calculate_address_locally(public_key)
    
    def _calculate_address_locally(self, public_key: str) -> str:
        """Generate address from public key locally (fallback)"""
        try:
            # Decode public key
            public_key_bytes = base64.b64decode(public_key)
            
            # Create address hash
            hash1 = hashlib.sha256(public_key_bytes).digest()
            hash2 = hashlib.sha256(hash1).digest()
            
            # Take first 20 bytes and create address
            address_bytes = hash2[:20]
            
            # Add 'Q' prefix and encode as hex
            address = 'Q' + address_bytes.hex().upper()
            
            # Pad to standard length (78 characters total)
            while len(address) < 78:
                address += '0'
            
            return address
            
        except Exception as e:
            logger.error(f"Error calculating address locally: {e}")
            raise
    
    def _calculate_transaction_hash_for_signing(self, tx) -> str:
        """Calculate transaction hash that needs to be signed (returns hex string for frontend)"""
        
        # Use the same node-compatible binary format for hash calculation
        tx_hash_bytes = self._calculate_transaction_hash_bytes(tx)
        tx_hash_hex = tx_hash_bytes.hex()
        
        logger.info(f"Calculated transaction hash for signing: {tx_hash_hex}")
        return tx_hash_hex
    
    def _calculate_transaction_hash_bytes(self, tx) -> bytes:
        """Calculate transaction hash in bytes - MUST match node's TransferTransaction.get_data_bytes()"""
        import hashlib
        
        # Exactly match the node's TransferTransaction.get_data_bytes() implementation:
        # tmptxhash = (self.master_addr +
        #              self.fee.to_bytes(8, byteorder='big', signed=False) +
        #              self.message_data)
        # for index in range(0, len(self.addrs_to)):
        #     tmptxhash = (tmptxhash +
        #                  self.addrs_to[index] +
        #                  self.amounts[index].to_bytes(8, byteorder='big', signed=False))
        
        # Start with master_addr + fee + message_data
        tmptxhash = tx.master_addr + tx.fee.to_bytes(8, byteorder='big', signed=False)
        
        # Add message_data (empty bytes if none)
        if hasattr(tx, 'transfer') and tx.transfer and hasattr(tx.transfer, 'message_data'):
            tmptxhash += tx.transfer.message_data
        else:
            tmptxhash += b''  # Empty message_data
        
        # Add each recipient: addr_to + amount
        if hasattr(tx, 'transfer') and tx.transfer:
            for i in range(len(tx.transfer.addrs_to)):
                tmptxhash += tx.transfer.addrs_to[i]
                tmptxhash += tx.transfer.amounts[i].to_bytes(8, byteorder='big', signed=False)
        
        # Return SHA256 hash of the constructed data (matching get_data_hash())
        tx_hash_bytes = hashlib.sha256(tmptxhash).digest()
        
        logger.info(f"Calculated hash bytes using node format: {tx_hash_bytes.hex()}")
        return tx_hash_bytes
    
    def _verify_transaction_signature(self, transaction_data: Dict[str, Any], 
                                     signature_bytes: bytes, public_key_bytes: bytes) -> bool:
        """Verify the transaction signature before submission"""
        try:
            logger.info("Verifying transaction signature...")
            
            # Reconstruct the transaction hash that was signed
            # We need to create the same hash calculation that was used for signing
            
            # Calculate transaction hash using the same method as during creation
            # Since we don't have the original protobuf transaction, reconstruct the hash
            # from the transaction data using the EXACT same format as the node
            
            import hashlib
            
            # Reconstruct transaction data exactly as the node does in TransferTransaction.get_data_bytes()
            # Convert hex strings back to bytes
            master_addr_bytes = bytes.fromhex(transaction_data['from_addr_bytes'])
            fee = transaction_data['fee']
            to_addr_bytes = bytes.fromhex(transaction_data['to_addr_bytes'])
            amount = transaction_data['amount']
            message_data = transaction_data.get('message', '').encode() if transaction_data.get('message') else b''
            
            # Start with master_addr + fee + message_data
            tmptxhash = master_addr_bytes + fee.to_bytes(8, byteorder='big', signed=False) + message_data
            
            # Add recipient: addr_to + amount
            tmptxhash += to_addr_bytes + amount.to_bytes(8, byteorder='big', signed=False)
            
            # Hash the constructed data (matching get_data_hash())
            message_hash_bytes = hashlib.sha256(tmptxhash).digest()
            
            logger.info(f"Reconstructed hash for verification: {message_hash_bytes.hex()}")
            
            # Verify signature using Falcon-512
            falcon_sig = FalconSignature()
            is_valid = falcon_sig.verify_signature(message_hash_bytes, signature_bytes, public_key_bytes)
            
            logger.info(f"Signature verification result: {is_valid}")
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False
    
    # =====================
    # EXPLORER API METHODS
    # =====================
    
    def get_latest_blocks(self, count: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get latest blocks for explorer"""
        try:
            stub = self._get_public_stub()
            
            request = qbit_pb2.GetLatestDataReq()
            request.filter = qbit_pb2.GetLatestDataReq.BLOCKHEADERS
            request.offset = offset
            request.quantity = min(count, 100)  # Limit to 100 blocks max
            
            response = stub.GetLatestData(request)
            
            blocks = []
            for block_header in response.blockheaders:
                header = block_header.header
                tx_count = sum(block_header.transaction_count.count.values())
                
                # Get actual block size by fetching the full block
                actual_block_size = 0
                try:
                    # Use the same method as get_block_by_number to get actual size
                    full_block = self.get_block_by_number(header.block_number)
                    if full_block and 'size' in full_block:
                        actual_block_size = full_block['size']
                except Exception as e:
                    logger.warning(f"Could not get actual size for block {header.block_number}: {e}")
                    # If we can't get actual size, don't estimate - just use 0
                    actual_block_size = 0
                
                block_info = {
                    'block_number': header.block_number,
                    'block_hash': header.hash_header.hex(),
                    'prev_hash': header.hash_header_prev.hex(),
                    'timestamp': header.timestamp_seconds,
                    'transaction_count': tx_count,
                    'merkle_root': header.merkle_root.hex() if header.merkle_root else '',
                    'nonce': header.extra_nonce,
                    'difficulty': getattr(header, 'difficulty', 0),  # Use getattr in case difficulty field doesn't exist
                    'size': actual_block_size  # Use actual block size, not estimation
                }
                blocks.append(block_info)
            
            return blocks
            
        except Exception as e:
            logger.error(f"Error getting latest blocks: {e}")
            raise
    
    def get_latest_transactions(self, count: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Get latest transactions for explorer"""
        try:
            stub = self._get_public_stub()
            
            request = qbit_pb2.GetLatestDataReq()
            request.filter = qbit_pb2.GetLatestDataReq.TRANSACTIONS
            request.offset = offset
            request.quantity = min(count, 100)  # Limit to 100 transactions max
            
            response = stub.GetLatestData(request)
            
            transactions = []
            for tx_extended in response.transactions:
                tx = tx_extended.tx
                
                # Use block header timestamp if available (confirmed transaction)
                # Otherwise use transaction timestamp_seconds for pending transactions
                timestamp = None
                if tx_extended.header and hasattr(tx_extended.header, 'timestamp_seconds'):
                    timestamp = tx_extended.header.timestamp_seconds
                else:
                    # For unconfirmed transactions, use current time or a reasonable default
                    import time
                    timestamp = int(time.time())
                
                tx_info = {
                    'tx_hash': tx.transaction_hash.hex(),
                    'type': self._get_transaction_type(tx),
                    'amount': self._get_transaction_amount(tx),
                    'fee': tx.fee,
                    'from_address': 'Q' + tx_extended.addr_from.hex() if tx_extended.addr_from else '',
                    'to_address': self._get_transaction_to_address(tx),
                    'outputs': self._get_transaction_outputs(tx),  # Add all outputs
                    'timestamp': timestamp,
                    'size': tx_extended.size
                }
                transactions.append(tx_info)
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting latest transactions: {e}")
            raise
    
    def get_block_by_number(self, block_number: int) -> Optional[Dict[str, Any]]:
        """Get block details by block number"""
        try:
            stub = self._get_public_stub()
            
            request = qbit_pb2.GetBlockByNumberReq()
            request.block_number = block_number
            
            response = stub.GetBlockByNumber(request)
            
            if response.block:
                block = response.block
                
                # Get transaction details
                transactions = []
                for tx_pb in block.transactions:
                    tx_info = {
                        'tx_hash': tx_pb.transaction_hash.hex(),
                        'type': self._get_transaction_type(tx_pb),
                        'amount': self._get_transaction_amount(tx_pb),
                        'fee': tx_pb.fee,
                        'from_address': 'Q' + tx_pb.master_addr.hex() if tx_pb.master_addr else '',
                        'to_address': self._get_transaction_to_address(tx_pb)
                    }
                    transactions.append(tx_info)
                
                return {
                    'block_number': block.header.block_number,
                    'block_hash': block.header.hash_header.hex(),
                    'prev_hash': block.header.hash_header_prev.hex(),
                    'timestamp': block.header.timestamp_seconds,
                    'transaction_count': len(block.transactions),
                    'transactions': transactions,
                    'merkle_root': block.header.merkle_root.hex() if block.header.merkle_root else '',
                    'nonce': block.header.extra_nonce,
                    'difficulty': getattr(block.header, 'difficulty', 0),  # Use getattr in case difficulty field doesn't exist
                    'size': len(block.SerializeToString())  # Get actual serialized block size including header and all transactions
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting block by number {block_number}: {e}")
            raise
    
    def get_transaction_by_hash(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details by hash"""
        try:
            stub = self._get_public_stub()
            
            # Convert hex string to bytes
            tx_hash_bytes = bytes.fromhex(tx_hash)
            
            request = qbit_pb2.GetTransactionReq()
            request.tx_hash = tx_hash_bytes
            
            response = stub.GetTransaction(request)
            
            if response.tx:
                tx = response.tx
                
                # Get timestamp from block if transaction is confirmed
                timestamp = None
                if response.block_number:
                    try:
                        # Try to get the block to retrieve timestamp
                        block = self.get_block_by_number(response.block_number)
                        if block:
                            timestamp = block.get('timestamp')
                    except Exception as e:
                        logger.warning(f"Could not get block timestamp for transaction {tx_hash}: {e}")
                
                return {
                    'tx_hash': tx.transaction_hash.hex(),
                    'type': self._get_transaction_type(tx),
                    'amount': self._get_transaction_amount(tx),
                    'fee': tx.fee,
                    'from_address': 'Q' + tx.master_addr.hex() if tx.master_addr else '',
                    'to_address': self._get_transaction_to_address(tx),
                    'outputs': self._get_transaction_outputs(tx),  # Add all outputs
                    'block_number': response.block_number if response.block_number else None,
                    'confirmations': response.confirmations,
                    'block_hash': response.block_header_hash.hex() if response.block_header_hash else '',
                    'timestamp': timestamp,  # Add timestamp from block
                    'nonce': tx.nonce,
                    'public_key': tx.public_key.hex() if tx.public_key else '',
                    'signature': tx.signature.hex() if tx.signature else '',
                    'message': self._get_transaction_message(tx)
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting transaction by hash {tx_hash}: {e}")
            raise
    
    def search_by_query(self, query: str) -> Dict[str, Any]:
        """Search for blocks, transactions, or addresses"""
        try:
            results = {
                'query': query,
                'results': [],
                'type': 'unknown'
            }
            
            # Try to determine query type and search accordingly
            query = query.strip()
            
            # Check if it's a QBitcoin address (starts with Q)
            if query.startswith('Q') and len(query) == 49:  # Typical QBitcoin address length
                logger.info(f"Searching for address: {query}")
                
                # Use the same methods that work in the wallet
                address_info = {
                    'type': 'address',
                    'address': query,
                    'balance': 0,
                    'nonce': 0,
                    'transaction_count': 0,
                    'recent_transactions': []
                }
                
                # Get balance using the same method as wallet
                try:
                    balance_data = self.get_balance(query)
                    address_info['balance'] = balance_data.get('balance', 0)
                    address_info['nonce'] = balance_data.get('nonce', 0)
                    logger.info(f"Successfully got balance: {balance_data}")
                except Exception as e:
                    logger.warning(f"Could not get balance for {query}: {e}")
                    # Continue anyway - address might exist but have no balance
                
                # Get address state for transaction count
                try:
                    state_data = self.get_address_state(query)
                    address_info['transaction_count'] = state_data.get('transaction_count', 0)
                    logger.info(f"Successfully got address state: {state_data}")
                except Exception as e:
                    logger.warning(f"Could not get address state for {query}: {e}")
                    # Continue anyway
                
                # Get recent transactions using the same method as wallet
                try:
                    tx_data = self.get_transactions_by_address(query, 1, 5)
                    address_info['recent_transactions'] = tx_data.get('transactions', [])
                    logger.info(f"Successfully got {len(address_info['recent_transactions'])} transactions")
                except Exception as e:
                    logger.warning(f"Could not get transactions for {query}: {e}")
                    # Continue anyway
                
                # Always return address info, even if some calls failed
                results['type'] = 'address'
                results['results'] = [address_info]
                logger.info(f"Returning address search results: {results}")
                return results
            
            # Check if it's a block number (numeric)
            if query.isdigit():
                try:
                    block_number = int(query)
                    block = self.get_block_by_number(block_number)
                    if block:
                        results['type'] = 'block'
                        results['results'] = [block]
                        return results
                except:
                    pass
            
            # Check if it's a 64-character hex string (transaction hash only)
            if len(query) == 64 and all(c in '0123456789abcdefABCDEF' for c in query):
                # Try to find it as a transaction hash
                try:
                    tx = self.get_transaction_by_hash(query)
                    if tx:
                        results['type'] = 'transaction'
                        results['results'] = [tx]
                        return results
                except Exception as e:
                    logger.debug(f"Not found as transaction: {e}")
                    pass
            
            # No results found
            results['type'] = 'not_found'
            return results
            
        except Exception as e:
            logger.error(f"Error searching for query {query}: {e}")
            raise
    
    def get_chain_stats(self) -> Dict[str, Any]:
        """Get blockchain statistics, including difficulty, hash power, and chain size (GB) from node."""
        try:
            stub = self._get_public_stub()
            # Get main stats (with timeseries for difficulty/hashpower)
            stats_req = qbit_pb2.GetStatsReq()
            stats_req.include_timeseries = True
            stats_resp = stub.GetStats(stats_req)

            # Get chain size (GB) from GetChainStats
            chain_stats_req = qbit_pb2.GetChainStatsReq()
            chain_stats_resp = stub.GetChainStats(chain_stats_req)

            # Get node status for accurate sync information
            node_status = self.get_node_status()

            # Difficulty and hash power from latest timeseries point
            difficulty = 0
            hash_power = 0
            if hasattr(stats_resp, 'block_timeseries') and stats_resp.block_timeseries:
                last_point = stats_resp.block_timeseries[-1]
                # Difficulty may be string, convert to int if needed
                try:
                    difficulty = int(getattr(last_point, 'difficulty', 0))
                except Exception:
                    difficulty = 0
                try:
                    hash_power = int(getattr(last_point, 'hash_power', 0))
                except Exception:
                    hash_power = 0

            # Chain size in GB (may be string)
            chain_size_gb = 0.0
            if hasattr(chain_stats_resp, 'state_size_gb'):
                try:
                    chain_size_gb = float(chain_stats_resp.state_size_gb)
                except Exception:
                    chain_size_gb = 0.0

            # Use block_time_mean from GetStats response if available
            avg_block_time = 0
            if hasattr(stats_resp, 'block_time_mean') and stats_resp.block_time_mean > 0:
                avg_block_time = int(stats_resp.block_time_mean)

            # Use node_status for accurate sync info and GetStats response for other data
            return {
                'block_height': stats_resp.node_info.block_height if hasattr(stats_resp, 'node_info') and hasattr(stats_resp.node_info, 'block_height') else node_status.get('node_info', {}).get('height', 0),
                'total_blocks': (stats_resp.node_info.block_height + 1) if hasattr(stats_resp, 'node_info') and hasattr(stats_resp.node_info, 'block_height') else (node_status.get('node_info', {}).get('height', 0) + 1),
                'network_id': stats_resp.node_info.network_id if hasattr(stats_resp, 'node_info') and hasattr(stats_resp.node_info, 'network_id') else node_status.get('node_info', {}).get('network', 'unknown'),
                'peers': stats_resp.node_info.num_connections if hasattr(stats_resp, 'node_info') and hasattr(stats_resp.node_info, 'num_connections') else node_status.get('node_info', {}).get('peers', 0),
                'synced': node_status.get('node_info', {}).get('synced', False),
                'coins_total': int(stats_resp.coins_total_supply) if hasattr(stats_resp, 'coins_total_supply') else 30000000,
                'coins_emitted': int(stats_resp.coins_emitted) if hasattr(stats_resp, 'coins_emitted') else 0,
                'block_last_reward': int(stats_resp.block_last_reward) if hasattr(stats_resp, 'block_last_reward') else 0,
                'last_block_timestamp': stats_resp.block_timeseries[-1].timestamp if hasattr(stats_resp, 'block_timeseries') and stats_resp.block_timeseries else 0,
                'difficulty': difficulty,
                'hash_power_hps': hash_power,
                'chain_size_gb': chain_size_gb,
                'avg_block_time': avg_block_time,
                'epoch': int(stats_resp.epoch) if hasattr(stats_resp, 'epoch') else 0,
                'uptime_network': int(stats_resp.uptime_network) if hasattr(stats_resp, 'uptime_network') else 0
            }
        except Exception as e:
            logger.error(f"Error getting chain stats: {e}")
            return {
                'block_height': 0,
                'total_blocks': 0,
                'network_id': 'unknown',
                'peers': 0,
                'synced': False,
                'coins_total': 30000000,
                'coins_emitted': 0,
                'block_last_reward': 0,
                'last_block_timestamp': 0,
                'difficulty': 0,
                'hash_power_hps': 0,
                'chain_size_gb': 0.0,
                'avg_block_time': 0,
                'epoch': 0,
                'uptime_network': 0
            }
    
    def get_known_peers(self):
        """Get list of known peers from the node"""
        try:
            if not self._public_stub:
                raise Exception("Public API stub not initialized")
            
            request = qbit_pb2.GetKnownPeersReq()
            response = self._public_stub.GetKnownPeers(request)
            
            peers = []
            for peer in response.known_peers:
                peers.append({
                    'ip': peer.ip,
                    'online': True  # Known peers are typically online
                })
                
            return peers
            
        except Exception as e:
            logger.error(f"Error getting known peers: {e}")
            return []
    
    def get_peers_stat(self):
        """Get detailed statistics for connected peers"""
        try:
            if not self._public_stub:
                raise Exception("Public API stub not initialized")
            
            request = qbit_pb2.GetPeersStatReq()
            response = self._public_stub.GetPeersStat(request)
            
            peers = []
            for peer_stat in response.peers_stat:
                # Decode peer IP from bytes
                peer_ip = peer_stat.peer_ip.decode('utf-8', errors='ignore') if peer_stat.peer_ip else 'Unknown'
                
                # Get additional IP information
                region = self._get_region_from_ip(peer_ip)
                ip_info = self._get_detailed_ip_info(peer_ip)
                
                peer_data = {
                    'ip': peer_ip,
                    'port': peer_stat.port,
                    'online': True,
                    'version': peer_stat.node_chain_state.version if peer_stat.node_chain_state else 'Unknown',
                    'block_height': peer_stat.node_chain_state.block_number if peer_stat.node_chain_state else 0,
                    'timestamp': peer_stat.node_chain_state.timestamp if peer_stat.node_chain_state else 0,
                    'region': region,
                    'connection_type': 'P2P',
                    'latency': 0,  # Not available in current protobuf
                    'organization': ip_info.get('org', 'Unknown'),
                    'timezone': ip_info.get('timezone', 'Unknown'),
                    'city': ip_info.get('city', 'Unknown'),
                    'country': ip_info.get('country', 'Unknown')
                }
                peers.append(peer_data)
                
            return peers
            
        except Exception as e:
            logger.error(f"Error getting peers stats: {e}")
            return []
    
    def _get_detailed_ip_info(self, ip):
        """Get detailed IP information from ipinfo.io"""
        try:
            # Check for local/private IPs first
            if ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                return {'org': 'Local Network', 'timezone': 'Local', 'city': 'Local', 'country': 'Local'}
            
            # Use ipinfo.io API to get detailed location data
            url = f"https://ipinfo.io/{ip}/json"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {}
                
        except Exception as e:
            logger.debug(f"Failed to get detailed IP info for {ip}: {e}")
            return {}
    
    def _get_region_from_ip(self, ip):
        """Get region from IP address using ipinfo.io API"""
        try:
            # Check for local/private IPs first
            if ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                return 'Local'
            
            # Use ipinfo.io API to get location data
            import requests
            url = f"https://ipinfo.io/{ip}/json"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                city = data.get('city', '')
                region = data.get('region', '')
                country = data.get('country', '')
                
                # Build a nice location string
                location_parts = []
                if city:
                    location_parts.append(city)
                if region and region != city:
                    location_parts.append(region)
                if country:
                    location_parts.append(country)
                
                return ', '.join(location_parts) if location_parts else 'Unknown'
            else:
                return 'Unknown'
                
        except Exception as e:
            logger.debug(f"Failed to get IP info for {ip}: {e}")
            return 'Unknown'
    
    def _get_transaction_message(self, tx) -> str:
        """Get message from transaction if available"""
        try:
            if tx.HasField('transfer') and tx.transfer.message_data:
                return tx.transfer.message_data.decode('utf-8', errors='ignore')
            elif tx.HasField('message') and tx.message.message_hash:
                return tx.message.message_hash.decode('utf-8', errors='ignore')
            else:
                return ''
        except:
            return ''


