"""
QuickShare - TCP File Transfer Service
"""

import socket
import threading
import json
import hashlib
import os
import uuid
import struct
from datetime import datetime
from typing import Optional, Dict, Callable

from .constants import TRANSFER_PORT, CHUNK_SIZE, BUFFER_SIZE
from .enums import MessageType, TransferStatus
from .models import DeviceInfo, FileMetadata, ProtocolMessage, FileChunk, TransferRequest


class FileTransferService:
    """TCP-based file transfer service with chunked transfer support"""

    def __init__(self):
        self.download_folder = os.path.join(
            os.path.expanduser("~"),
            "Downloads",
            "QuickShare"
        )
        os.makedirs(self.download_folder, exist_ok=True)

        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._active_transfers: Dict[str, TransferRequest] = {}
        self._pending_requests: Dict[str, dict] = {}  # Stores pending accept/reject decisions

        # Callbacks
        self.on_transfer_requested: Optional[Callable[[TransferRequest], None]] = None
        self.on_transfer_decision: Optional[Callable[[TransferRequest, Callable[[bool], None]], None]] = None
        self.on_transfer_progress: Optional[Callable[[TransferRequest], None]] = None
        self.on_transfer_completed: Optional[Callable[[TransferRequest], None]] = None
        self.on_transfer_failed: Optional[Callable[[TransferRequest, str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def start_server(self):
        """Start the TCP server for receiving files"""
        if self._running:
            return

        self._running = True

        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(('', TRANSFER_PORT))
            self._server_socket.listen(5)

            threading.Thread(target=self._accept_clients, daemon=True).start()

        except Exception as e:
            if self.on_error:
                self.on_error(f"Server error: {e}")

    def stop_server(self):
        """Stop the TCP server"""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except:
                pass

    def _accept_clients(self):
        """Accept incoming client connections"""
        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                client_socket, addr = self._server_socket.accept()
                threading.Thread(
                    target=self._handle_client,
                    args=(client_socket,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running and self.on_error:
                    self.on_error(f"Accept error: {e}")

    def _send_message(self, sock: socket.socket, message: str):
        """Send a length-prefixed message"""
        data = message.encode('utf-8')
        length = struct.pack('>I', len(data))
        sock.sendall(length + data)

    def _receive_message(self, sock: socket.socket) -> str:
        """Receive a length-prefixed message"""
        length_bytes = self._recv_exact(sock, 4)
        length = struct.unpack('>I', length_bytes)[0]
        data = self._recv_exact(sock, length)
        return data.decode('utf-8')

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes"""
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                raise ConnectionError("Connection closed")
            data += packet
        return data

    def _compute_file_checksum(self, file_path: str) -> str:
        """Compute SHA-256 checksum of a file"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(BUFFER_SIZE):
                sha256.update(chunk)
        return sha256.hexdigest().upper()

    def _compute_chunk_checksum(self, data: bytes) -> str:
        """Compute SHA-256 checksum of a chunk"""
        return hashlib.sha256(data).hexdigest().upper()

    def _get_unique_file_path(self, file_path: str) -> str:
        """Get a unique file path if file already exists"""
        if not os.path.exists(file_path):
            return file_path

        directory = os.path.dirname(file_path)
        filename = os.path.splitext(os.path.basename(file_path))[0]
        extension = os.path.splitext(file_path)[1]
        counter = 1

        while os.path.exists(file_path):
            file_path = os.path.join(directory, f"{filename} ({counter}){extension}")
            counter += 1

        return file_path

    def send_file(self, target: DeviceInfo, file_path: str):
        """Send a file to a remote device"""
        threading.Thread(
            target=self._send_file_impl,
            args=(target, file_path),
            daemon=True
        ).start()

    def _send_file_impl(self, target: DeviceInfo, file_path: str):
        """Implementation of file sending"""
        if not os.path.exists(file_path):
            if self.on_error:
                self.on_error(f"File not found: {file_path}")
            return

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        metadata = FileMetadata(
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            total_chunks=int((file_size + CHUNK_SIZE - 1) // CHUNK_SIZE),
            checksum=self._compute_file_checksum(file_path)
        )

        request = TransferRequest(
            sender_id=socket.gethostname(),
            sender_name=socket.gethostname(),
            receiver_id=target.id,
            file_info=metadata,
            status=TransferStatus.PENDING,
            started_at=datetime.now()
        )

        self._active_transfers[request.id] = request

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUFFER_SIZE)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)
            client_socket.connect((target.ip_address, target.port))

            # Send transfer request
            request_msg = ProtocolMessage(
                type=MessageType.TRANSFER_REQUEST,
                sender_id=request.sender_id,
                payload=json.dumps({
                    "Id": metadata.id,
                    "FileName": metadata.file_name,
                    "FilePath": metadata.file_path,
                    "FileSize": metadata.file_size,
                    "ContentType": metadata.content_type,
                    "Checksum": metadata.checksum,
                    "TotalChunks": metadata.total_chunks
                })
            )

            self._send_message(client_socket, json.dumps(request_msg.to_dict()))

            # Wait for accept/reject
            response = self._receive_message(client_socket)
            response_msg = ProtocolMessage.from_dict(json.loads(response))

            if response_msg.type == MessageType.TRANSFER_REJECT:
                request.status = TransferStatus.CANCELLED
                if self.on_transfer_failed:
                    self.on_transfer_failed(request, "Transfer rejected by receiver")
                return

            if response_msg.type != MessageType.TRANSFER_ACCEPT:
                request.status = TransferStatus.FAILED
                if self.on_transfer_failed:
                    self.on_transfer_failed(request, "Invalid response from receiver")
                return

            # Start sending file
            request.status = TransferStatus.IN_PROGRESS
            if self.on_transfer_progress:
                self.on_transfer_progress(request)

            with open(file_path, 'rb') as f:
                chunk_index = 0
                while True:
                    data = f.read(CHUNK_SIZE)
                    if not data:
                        break

                    chunk = FileChunk(
                        transfer_id=request.id,
                        chunk_index=chunk_index,
                        total_chunks=metadata.total_chunks,
                        data=data,
                        checksum=self._compute_chunk_checksum(data)
                    )

                    chunk_msg = ProtocolMessage(
                        type=MessageType.FILE_CHUNK,
                        sender_id=request.sender_id,
                        payload=json.dumps(chunk.to_dict())
                    )

                    self._send_message(client_socket, json.dumps(chunk_msg.to_dict()))

                    # Wait for ACK
                    ack_response = self._receive_message(client_socket)
                    ack_msg = ProtocolMessage.from_dict(json.loads(ack_response))

                    if ack_msg.type != MessageType.CHUNK_ACK:
                        raise Exception("Chunk transfer failed - no ACK received")

                    request.bytes_transferred += len(data)
                    chunk_index += 1

                    if self.on_transfer_progress:
                        self.on_transfer_progress(request)

            # Send completion
            complete_msg = ProtocolMessage(
                type=MessageType.TRANSFER_COMPLETE,
                sender_id=request.sender_id,
                payload=metadata.checksum
            )
            self._send_message(client_socket, json.dumps(complete_msg.to_dict()))

            request.status = TransferStatus.COMPLETED
            request.completed_at = datetime.now()

            if self.on_transfer_completed:
                self.on_transfer_completed(request)

            client_socket.close()

        except Exception as e:
            request.status = TransferStatus.FAILED
            if self.on_transfer_failed:
                self.on_transfer_failed(request, str(e))

        finally:
            if request.id in self._active_transfers:
                del self._active_transfers[request.id]

    def _handle_client(self, client_socket: socket.socket):
        """Handle incoming client connection"""
        request = None

        try:
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, BUFFER_SIZE)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)

            # Receive transfer request
            message = self._receive_message(client_socket)
            msg = ProtocolMessage.from_dict(json.loads(message))

            if msg.type != MessageType.TRANSFER_REQUEST:
                return

            metadata_dict = json.loads(msg.payload)
            metadata = FileMetadata(
                id=metadata_dict.get("Id", str(uuid.uuid4())),
                file_name=metadata_dict.get("FileName", ""),
                file_path=metadata_dict.get("FilePath", ""),
                file_size=metadata_dict.get("FileSize", 0),
                content_type=metadata_dict.get("ContentType", "application/octet-stream"),
                checksum=metadata_dict.get("Checksum", ""),
                total_chunks=metadata_dict.get("TotalChunks", 0)
            )

            request = TransferRequest(
                sender_id=msg.sender_id,
                sender_name=msg.sender_id,
                file_info=metadata,
                status=TransferStatus.PENDING,
                started_at=datetime.now()
            )

            self._active_transfers[request.id] = request

            # Wait for user decision (accept/reject)
            user_accepted = False
            decision_event = threading.Event()
            
            def on_decision(accepted: bool):
                nonlocal user_accepted
                user_accepted = accepted
                decision_event.set()
            
            # Store the decision callback for this request
            self._pending_requests[request.id] = {
                'request': request,
                'callback': on_decision,
                'socket': client_socket
            }
            
            # Notify UI to show accept/reject dialog
            if self.on_transfer_decision:
                self.on_transfer_decision(request, on_decision)
            else:
                # Fallback: auto-accept if no handler
                on_decision(True)
            
            # Wait for user decision (timeout after 60 seconds)
            decision_event.wait(timeout=60)
            
            # Clean up pending request
            if request.id in self._pending_requests:
                del self._pending_requests[request.id]
            
            if not user_accepted:
                # Send reject
                reject_msg = ProtocolMessage(
                    type=MessageType.TRANSFER_REJECT,
                    sender_id=socket.gethostname(),
                    payload="Transfer rejected by user"
                )
                self._send_message(client_socket, json.dumps(reject_msg.to_dict()))
                request.status = TransferStatus.CANCELLED
                return

            # Send accept
            accept_msg = ProtocolMessage(
                type=MessageType.TRANSFER_ACCEPT,
                sender_id=socket.gethostname()
            )
            self._send_message(client_socket, json.dumps(accept_msg.to_dict()))

            # Receive file chunks
            request.status = TransferStatus.IN_PROGRESS
            file_path = os.path.join(self.download_folder, metadata.file_name)
            file_path = self._get_unique_file_path(file_path)

            with open(file_path, 'wb') as f:
                while True:
                    chunk_message = self._receive_message(client_socket)
                    chunk_msg = ProtocolMessage.from_dict(json.loads(chunk_message))

                    if chunk_msg.type == MessageType.TRANSFER_COMPLETE:
                        break

                    if chunk_msg.type == MessageType.FILE_CHUNK:
                        chunk = FileChunk.from_dict(json.loads(chunk_msg.payload))

                        # Verify chunk checksum
                        computed_checksum = self._compute_chunk_checksum(chunk.data)
                        if computed_checksum != chunk.checksum:
                            raise Exception(f"Chunk {chunk.chunk_index} checksum mismatch")

                        f.write(chunk.data)
                        request.bytes_transferred += len(chunk.data)

                        if self.on_transfer_progress:
                            self.on_transfer_progress(request)

                        # Send ACK
                        ack_msg = ProtocolMessage(
                            type=MessageType.CHUNK_ACK,
                            sender_id=socket.gethostname(),
                            payload=str(chunk.chunk_index)
                        )
                        self._send_message(client_socket, json.dumps(ack_msg.to_dict()))

            # Verify final checksum
            final_checksum = self._compute_file_checksum(file_path)

            if final_checksum != metadata.checksum:
                os.remove(file_path)
                raise Exception("File checksum verification failed")

            request.status = TransferStatus.COMPLETED
            request.completed_at = datetime.now()
            request.file_info.file_path = file_path

            if self.on_transfer_completed:
                self.on_transfer_completed(request)

        except Exception as e:
            if request:
                request.status = TransferStatus.FAILED
                if self.on_transfer_failed:
                    self.on_transfer_failed(request, str(e))

        finally:
            if request and request.id in self._active_transfers:
                del self._active_transfers[request.id]
            try:
                client_socket.close()
            except:
                pass
