"""
QuickShare - Desktop P2P File Transfer Application
Python/Tkinter implementation with exact functionality matching the WPF version

Features:
- UDP device discovery on port 45678
- TCP file transfer on port 45679
- Chunked transfer with SHA-256 checksum verification
- Drag-and-drop file support
- Receive mode toggle
- Real-time progress tracking
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import socket
import threading
import json
import hashlib
import os
import uuid
import struct
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable
from enum import Enum
import base64

# ============== Constants ==============
DISCOVERY_PORT = 45678
TRANSFER_PORT = 45679
SERVICE_IDENTIFIER = "QUICKSHARE_V1"
BROADCAST_INTERVAL_MS = 3000
CHUNK_SIZE = 64 * 1024  # 64KB
BUFFER_SIZE = 256 * 1024  # 256KB
STALE_THRESHOLD_SECONDS = 15


# ============== Enums ==============
class DeviceStatus(Enum):
    AVAILABLE = "Available"
    BUSY = "Busy"
    OFFLINE = "Offline"
    RECEIVING = "Receiving"


class MessageType(Enum):
    ANNOUNCE = "Announce"
    PING = "Ping"
    PONG = "Pong"
    TRANSFER_REQUEST = "TransferRequest"
    TRANSFER_ACCEPT = "TransferAccept"
    TRANSFER_REJECT = "TransferReject"
    TRANSFER_CANCEL = "TransferCancel"
    TRANSFER_COMPLETE = "TransferComplete"
    FILE_CHUNK = "FileChunk"
    CHUNK_ACK = "ChunkAck"
    ERROR = "Error"


class TransferStatus(Enum):
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


# ============== Data Classes ==============
@dataclass
class DeviceInfo:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    ip_address: str = ""
    port: int = TRANSFER_PORT
    last_seen: datetime = field(default_factory=datetime.now)
    status: DeviceStatus = DeviceStatus.AVAILABLE
    is_receiving: bool = False

    def __str__(self):
        return f"{self.name} ({self.ip_address}:{self.port})"


@dataclass
class FileMetadata:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    file_name: str = ""
    file_path: str = ""
    file_size: int = 0
    content_type: str = "application/octet-stream"
    checksum: str = ""
    total_chunks: int = 0

    @property
    def formatted_size(self) -> str:
        sizes = ["B", "KB", "MB", "GB", "TB"]
        order = 0
        size = float(self.file_size)
        while size >= 1024 and order < len(sizes) - 1:
            order += 1
            size /= 1024
        return f"{size:.2f} {sizes[order]}"


@dataclass
class ProtocolMessage:
    type: MessageType = MessageType.ANNOUNCE
    sender_id: str = ""
    payload: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {
            "Type": self.type.value,
            "SenderId": self.sender_id,
            "Payload": self.payload,
            "Timestamp": self.timestamp
        }

    @staticmethod
    def from_dict(data: dict) -> 'ProtocolMessage':
        return ProtocolMessage(
            type=MessageType(data.get("Type", "Announce")),
            sender_id=data.get("SenderId", ""),
            payload=data.get("Payload", ""),
            timestamp=data.get("Timestamp", "")
        )


@dataclass
class FileChunk:
    transfer_id: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    data: bytes = b""
    checksum: str = ""

    def to_dict(self):
        return {
            "TransferId": self.transfer_id,
            "ChunkIndex": self.chunk_index,
            "TotalChunks": self.total_chunks,
            "Data": base64.b64encode(self.data).decode('utf-8'),
            "Checksum": self.checksum
        }

    @staticmethod
    def from_dict(data: dict) -> 'FileChunk':
        return FileChunk(
            transfer_id=data.get("TransferId", ""),
            chunk_index=data.get("ChunkIndex", 0),
            total_chunks=data.get("TotalChunks", 0),
            data=base64.b64decode(data.get("Data", "")),
            checksum=data.get("Checksum", "")
        )


@dataclass
class TransferRequest:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    sender_name: str = ""
    receiver_id: str = ""
    file_info: FileMetadata = field(default_factory=FileMetadata)
    status: TransferStatus = TransferStatus.PENDING
    bytes_transferred: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def progress(self) -> float:
        if self.file_info.file_size > 0:
            return (self.bytes_transferred / self.file_info.file_size) * 100
        return 0


# ============== Discovery Service ==============
class DiscoveryService:
    """UDP-based device discovery service"""

    def __init__(self):
        self.device_id = self._get_device_id()
        self.device_name = socket.gethostname()
        self.discovered_devices: Dict[str, DeviceInfo] = {}
        self.is_receive_mode = False
        self._running = False
        self._udp_socket: Optional[socket.socket] = None
        self._lock = threading.Lock()

        # Callbacks
        self.on_device_discovered: Optional[Callable[[DeviceInfo], None]] = None
        self.on_device_lost: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    def _get_device_id(self) -> str:
        """Get a unique device ID based on MAC address or fallback"""
        try:
            import uuid as uuid_module
            mac = uuid_module.getnode()
            return format(mac, '012x').upper()
        except:
            return f"{socket.gethostname()}_{os.getlogin()}"

    def _get_local_ip(self) -> str:
        """Get the local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 65530))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"

    def set_receive_mode(self, enabled: bool):
        """Enable or disable receive mode"""
        self.is_receive_mode = enabled

    def start(self):
        """Start the discovery service"""
        if self._running:
            return

        self._running = True

        try:
            self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._udp_socket.bind(('', DISCOVERY_PORT))
            self._udp_socket.settimeout(1.0)

            # Start background threads
            threading.Thread(target=self._broadcast_presence, daemon=True).start()
            threading.Thread(target=self._listen_for_broadcasts, daemon=True).start()
            threading.Thread(target=self._cleanup_stale_devices, daemon=True).start()

        except Exception as e:
            if self.on_error:
                self.on_error(f"Failed to start discovery: {e}")

    def stop(self):
        """Stop the discovery service"""
        self._running = False
        if self._udp_socket:
            try:
                self._udp_socket.close()
            except:
                pass

    def _broadcast_presence(self):
        """Broadcast our presence on the network"""
        while self._running:
            try:
                announce_data = {
                    "Service": SERVICE_IDENTIFIER,
                    "Id": self.device_id,
                    "Name": self.device_name,
                    "Ip": self._get_local_ip(),
                    "Port": TRANSFER_PORT,
                    "Timestamp": datetime.now(timezone.utc).isoformat(),
                    "IsReceiving": self.is_receive_mode
                }

                message = json.dumps(announce_data).encode('utf-8')
                self._udp_socket.sendto(message, ('<broadcast>', DISCOVERY_PORT))

            except Exception as e:
                if self._running and self.on_error:
                    self.on_error(f"Broadcast error: {e}")

            time.sleep(BROADCAST_INTERVAL_MS / 1000)

    def _listen_for_broadcasts(self):
        """Listen for broadcast announcements"""
        while self._running:
            try:
                data, addr = self._udp_socket.recvfrom(4096)
                message = json.loads(data.decode('utf-8'))

                if message.get("Service") == SERVICE_IDENTIFIER:
                    device_id = message.get("Id")

                    # Ignore our own broadcasts
                    if device_id == self.device_id:
                        continue

                    is_receiving = message.get("IsReceiving", False)
                    device = DeviceInfo(
                        id=device_id,
                        name=message.get("Name", "Unknown"),
                        ip_address=message.get("Ip", ""),
                        port=message.get("Port", TRANSFER_PORT),
                        last_seen=datetime.now(),
                        status=DeviceStatus.RECEIVING if is_receiving else DeviceStatus.AVAILABLE,
                        is_receiving=is_receiving
                    )

                    with self._lock:
                        is_new = device_id not in self.discovered_devices
                        self.discovered_devices[device_id] = device

                    if is_new and self.on_device_discovered:
                        self.on_device_discovered(device)


            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    continue

    def _cleanup_stale_devices(self):
        """Remove devices that haven't been seen recently"""
        while self._running:
            time.sleep(10)

            stale_threshold = datetime.now()
            stale_ids = []

            with self._lock:
                for device_id, device in list(self.discovered_devices.items()):
                    age = (stale_threshold - device.last_seen).total_seconds()
                    if age > STALE_THRESHOLD_SECONDS:
                        stale_ids.append(device_id)
                        del self.discovered_devices[device_id]

            for device_id in stale_ids:
                if self.on_device_lost:
                    self.on_device_lost(device_id)


# ============== File Transfer Service ==============
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


# ============== Main Application ==============
class QuickShareApp:
    """Main QuickShare application with Tkinter UI"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("QuickShare - P2P File Transfer")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)

        # Set dark theme colors
        self.colors = {
            'bg': '#1e1e2e',
            'bg_secondary': '#313244',
            'bg_tertiary': '#45475a',
            'accent': '#89b4fa',
            'accent_hover': '#74c7ec',
            'text': '#cdd6f4',
            'text_secondary': '#a6adc8',
            'success': '#a6e3a1',
            'warning': '#f9e2af',
            'error': '#f38ba8',
            'receiving': '#94e2d5'
        }

        self.root.configure(bg=self.colors['bg'])

        # Initialize services
        self.discovery_service = DiscoveryService()
        self.transfer_service = FileTransferService()

        # State
        self.devices: Dict[str, DeviceInfo] = {}
        self.selected_device: Optional[DeviceInfo] = None
        self.is_receive_mode = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Starting...")
        self.progress_var = tk.DoubleVar(value=0)
        self.transfer_info_var = tk.StringVar(value="")

        self._setup_ui()
        self._setup_callbacks()
        self._setup_dnd()

        # Start services
        self.root.after(100, self._start_services)

    def _setup_ui(self):
        """Setup the user interface"""
        # Configure styles
        style = ttk.Style()
        style.theme_use('clam')

        # Main container
        main_frame = tk.Frame(self.root, bg=self.colors['bg'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel - Device List
        left_panel = tk.Frame(main_frame, bg=self.colors['bg_secondary'], width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        # Device list header
        header_frame = tk.Frame(left_panel, bg=self.colors['bg_secondary'])
        header_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(
            header_frame,
            text="📱 Devices",
            font=('Segoe UI', 14, 'bold'),
            fg=self.colors['text'],
            bg=self.colors['bg_secondary']
        ).pack(side=tk.LEFT)

        # Refresh button
        refresh_btn = tk.Button(
            header_frame,
            text="🔄",
            font=('Segoe UI', 12),
            fg=self.colors['text'],
            bg=self.colors['bg_tertiary'],
            activebackground=self.colors['accent'],
            activeforeground=self.colors['bg'],
            relief=tk.FLAT,
            cursor='hand2',
            command=self._refresh_devices
        )
        refresh_btn.pack(side=tk.RIGHT)

        # Device listbox
        self.device_listbox = tk.Listbox(
            left_panel,
            font=('Segoe UI', 11),
            fg=self.colors['text'],
            bg=self.colors['bg'],
            selectbackground=self.colors['accent'],
            selectforeground=self.colors['bg'],
            relief=tk.FLAT,
            highlightthickness=0,
            activestyle='none'
        )
        self.device_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.device_listbox.bind('<<ListboxSelect>>', self._on_device_select)

        # Right panel
        right_panel = tk.Frame(main_frame, bg=self.colors['bg'])
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Top section - App info
        top_section = tk.Frame(right_panel, bg=self.colors['bg'])
        top_section.pack(fill=tk.X, pady=(0, 20))

        tk.Label(
            top_section,
            text="QuickShare",
            font=('Segoe UI', 24, 'bold'),
            fg=self.colors['accent'],
            bg=self.colors['bg']
        ).pack(anchor='w')

        tk.Label(
            top_section,
            text=f"Device: {socket.gethostname()}",
            font=('Segoe UI', 11),
            fg=self.colors['text_secondary'],
            bg=self.colors['bg']
        ).pack(anchor='w')

        # Drop zone
        self.drop_zone = tk.Frame(
            right_panel,
            bg=self.colors['bg_secondary'],
            relief=tk.FLAT,
            highlightthickness=2,
            highlightbackground=self.colors['bg_tertiary']
        )
        self.drop_zone.pack(fill=tk.BOTH, expand=True, pady=10)

        # Drop zone content
        drop_content = tk.Frame(self.drop_zone, bg=self.colors['bg_secondary'])
        drop_content.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(
            drop_content,
            text="📁",
            font=('Segoe UI', 48),
            fg=self.colors['accent'],
            bg=self.colors['bg_secondary']
        ).pack()

        tk.Label(
            drop_content,
            text="Drop files here or click to browse",
            font=('Segoe UI', 14),
            fg=self.colors['text'],
            bg=self.colors['bg_secondary']
        ).pack(pady=10)

        self.drop_hint_label = tk.Label(
            drop_content,
            text="Select a device from the list first",
            font=('Segoe UI', 10),
            fg=self.colors['text_secondary'],
            bg=self.colors['bg_secondary']
        )
        self.drop_hint_label.pack()

        # Make drop zone clickable
        self.drop_zone.bind('<Button-1>', lambda e: self._browse_file())
        for widget in drop_content.winfo_children():
            widget.bind('<Button-1>', lambda e: self._browse_file())

        # Progress bar
        progress_frame = tk.Frame(right_panel, bg=self.colors['bg'])
        progress_frame.pack(fill=tk.X, pady=10)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=5)

        self.transfer_label = tk.Label(
            progress_frame,
            textvariable=self.transfer_info_var,
            font=('Segoe UI', 10),
            fg=self.colors['text_secondary'],
            bg=self.colors['bg']
        )
        self.transfer_label.pack()

        # Bottom section - Controls
        bottom_section = tk.Frame(right_panel, bg=self.colors['bg'])
        bottom_section.pack(fill=tk.X, pady=10)

        # Receive mode toggle
        self.receive_btn = tk.Button(
            bottom_section,
            text="📥 Enable Receive Mode",
            font=('Segoe UI', 11),
            fg=self.colors['text'],
            bg=self.colors['bg_tertiary'],
            activebackground=self.colors['receiving'],
            activeforeground=self.colors['bg'],
            relief=tk.FLAT,
            cursor='hand2',
            padx=20,
            pady=8,
            command=self._toggle_receive_mode
        )
        self.receive_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Open downloads folder button
        downloads_btn = tk.Button(
            bottom_section,
            text="📂 Open Downloads",
            font=('Segoe UI', 11),
            fg=self.colors['text'],
            bg=self.colors['bg_tertiary'],
            activebackground=self.colors['accent'],
            activeforeground=self.colors['bg'],
            relief=tk.FLAT,
            cursor='hand2',
            padx=20,
            pady=8,
            command=self._open_downloads
        )
        downloads_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Send button
        self.send_btn = tk.Button(
            bottom_section,
            text="📤 Send File",
            font=('Segoe UI', 11, 'bold'),
            fg=self.colors['bg'],
            bg=self.colors['accent'],
            activebackground=self.colors['accent_hover'],
            activeforeground=self.colors['bg'],
            relief=tk.FLAT,
            cursor='hand2',
            padx=20,
            pady=8,
            command=self._browse_file
        )
        self.send_btn.pack(side=tk.RIGHT)

        # Status bar
        status_frame = tk.Frame(self.root, bg=self.colors['bg_secondary'])
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            font=('Segoe UI', 10),
            fg=self.colors['text_secondary'],
            bg=self.colors['bg_secondary'],
            pady=5
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

    def _setup_callbacks(self):
        """Setup service callbacks"""
        # Discovery callbacks
        self.discovery_service.on_device_discovered = self._on_device_discovered
        self.discovery_service.on_device_lost = self._on_device_lost
        self.discovery_service.on_error = lambda e: self._update_status(f"Discovery error: {e}")

        # Transfer callbacks
        self.transfer_service.on_transfer_decision = self._on_transfer_decision_requested
        self.transfer_service.on_transfer_progress = self._on_transfer_progress
        self.transfer_service.on_transfer_completed = self._on_transfer_completed
        self.transfer_service.on_transfer_failed = self._on_transfer_failed

    def _setup_dnd(self):
        """Setup drag and drop support"""
        # Try to use tkinterdnd2 if available
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            # Note: Would need to change root initialization
            pass
        except ImportError:
            # Fallback: manual file selection only
            pass

    def _start_services(self):
        """Start background services"""
        self.discovery_service.start()
        self.transfer_service.start_server()
        self._update_status("Ready. Searching for devices on network...")

    def _update_status(self, message: str):
        """Update status bar message"""
        self.root.after(0, lambda: self.status_var.set(message))

    def _update_device_list(self):
        """Update the device listbox"""
        self.device_listbox.delete(0, tk.END)
        for device_id, device in self.devices.items():
            status_icon = "📥" if device.is_receiving else "💻"
            self.device_listbox.insert(tk.END, f"{status_icon} {device.name} ({device.ip_address})")

    def _on_device_discovered(self, device: DeviceInfo):
        """Handle device discovery"""
        def update():
            existing = self.devices.get(device.id)
            self.devices[device.id] = device
            self._update_device_list()
            self._update_status(f"Found {len(self.devices)} device(s) on network")
        self.root.after(0, update)

    def _on_device_lost(self, device_id: str):
        """Handle device lost"""
        def update():
            if device_id in self.devices:
                del self.devices[device_id]
                self._update_device_list()
                self._update_status(f"Device offline. {len(self.devices)} device(s) available")
        self.root.after(0, update)

    def _on_device_select(self, event):
        """Handle device selection"""
        selection = self.device_listbox.curselection()
        if selection:
            index = selection[0]
            device_keys = list(self.devices.keys())
            if index < len(device_keys):
                self.selected_device = self.devices[device_keys[index]]
                self.drop_hint_label.config(text=f"Ready to send to: {self.selected_device.name}")

    def _on_transfer_decision_requested(self, request: TransferRequest, decision_callback: Callable[[bool], None]):
        """Handle incoming transfer request - show accept/reject dialog"""
        def show_dialog():
            self._update_status(f"📥 Incoming file from {request.sender_name}")
            
            # Show accept/reject dialog
            result = messagebox.askyesno(
                "Incoming File Transfer",
                f"📁 {request.sender_name} wants to send you a file:\n\n"
                f"File: {request.file_info.file_name}\n"
                f"Size: {request.file_info.formatted_size}\n\n"
                f"Do you want to accept this file?",
                icon='question'
            )
            
            if result:
                self._update_status(f"Accepted file from {request.sender_name}")
                self.transfer_info_var.set(f"Receiving: {request.file_info.file_name}")
            else:
                self._update_status(f"Rejected file from {request.sender_name}")
            
            # Call the decision callback on a background thread to not block UI
            threading.Thread(target=lambda: decision_callback(result), daemon=True).start()
        
        self.root.after(0, show_dialog)

    def _on_transfer_requested(self, request: TransferRequest):
        """Handle incoming transfer request"""
        def update():
            self.transfer_info_var.set(f"Receiving: {request.file_info.file_name} from {request.sender_name}")
        self.root.after(0, update)

    def _on_transfer_progress(self, request: TransferRequest):
        """Handle transfer progress update"""
        def update():
            self.progress_var.set(request.progress)
            action = "Sending" if request.sender_id == socket.gethostname() else "Receiving"
            self.transfer_info_var.set(f"{action}: {request.file_info.file_name} - {request.progress:.1f}%")
        self.root.after(0, update)

    def _on_transfer_completed(self, request: TransferRequest):
        """Handle transfer completion"""
        def update():
            self.progress_var.set(0)
            self.transfer_info_var.set("")
            self._update_status(f"Transfer complete: {request.file_info.file_name}")
            messagebox.showinfo("Transfer Complete", f"File transferred successfully:\n{request.file_info.file_name}")
        self.root.after(0, update)

    def _on_transfer_failed(self, request: TransferRequest, error: str):
        """Handle transfer failure"""
        def update():
            self.progress_var.set(0)
            self.transfer_info_var.set("")
            self._update_status(f"Transfer failed: {error}")
            messagebox.showerror("Transfer Failed", f"Transfer failed:\n{error}")
        self.root.after(0, update)

    def _browse_file(self):
        """Open file browser to select a file"""
        if not self.selected_device:
            messagebox.showwarning("No Device Selected", "Please select a device from the list first.")
            return

        file_path = filedialog.askopenfilename(
            title="Select file to send",
            filetypes=[("All Files", "*.*")]
        )

        if file_path:
            self._send_file(file_path)

    def _send_file(self, file_path: str):
        """Send a file to the selected device"""
        if not self.selected_device:
            self._update_status("Please select a device first")
            return

        self._update_status(f"Sending {os.path.basename(file_path)} to {self.selected_device.name}...")
        self.transfer_service.send_file(self.selected_device, file_path)

    def _refresh_devices(self):
        """Refresh the device list"""
        self.devices.clear()
        self._update_device_list()
        self._update_status("Refreshing device list...")

    def _toggle_receive_mode(self):
        """Toggle receive mode"""
        new_state = not self.is_receive_mode.get()
        self.is_receive_mode.set(new_state)
        self.discovery_service.set_receive_mode(new_state)

        if new_state:
            self.receive_btn.config(
                text="📥 Receive Mode ON",
                bg=self.colors['receiving'],
                fg=self.colors['bg']
            )
            self._update_status("📥 Receive Mode ON - Broadcasting availability...")
        else:
            self.receive_btn.config(
                text="📥 Enable Receive Mode",
                bg=self.colors['bg_tertiary'],
                fg=self.colors['text']
            )
            self._update_status("Ready. Searching for devices on network...")

    def _open_downloads(self):
        """Open the downloads folder"""
        folder = self.transfer_service.download_folder
        os.makedirs(folder, exist_ok=True)

        if os.name == 'nt':  # Windows
            os.startfile(folder)
        elif os.name == 'posix':  # macOS/Linux
            import subprocess
            subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', folder])

    def run(self):
        """Run the application"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        """Handle window close"""
        self.discovery_service.stop()
        self.transfer_service.stop_server()
        self.root.destroy()


# ============== Entry Point ==============
if __name__ == "__main__":
    app = QuickShareApp()
    app.run()
