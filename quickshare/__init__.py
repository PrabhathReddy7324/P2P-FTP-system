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

from .constants import (
    DISCOVERY_PORT,
    TRANSFER_PORT,
    SERVICE_IDENTIFIER,
    BROADCAST_INTERVAL_MS,
    CHUNK_SIZE,
    BUFFER_SIZE,
    STALE_THRESHOLD_SECONDS
)

from .enums import (
    DeviceStatus,
    MessageType,
    TransferStatus
)

from .models import (
    DeviceInfo,
    FileMetadata,
    ProtocolMessage,
    FileChunk,
    TransferRequest
)

from .discovery import DiscoveryService
from .transfer import FileTransferService
from .ui import QuickShareApp

__all__ = [
    # Constants
    'DISCOVERY_PORT',
    'TRANSFER_PORT',
    'SERVICE_IDENTIFIER',
    'BROADCAST_INTERVAL_MS',
    'CHUNK_SIZE',
    'BUFFER_SIZE',
    'STALE_THRESHOLD_SECONDS',
    # Enums
    'DeviceStatus',
    'MessageType',
    'TransferStatus',
    # Models
    'DeviceInfo',
    'FileMetadata',
    'ProtocolMessage',
    'FileChunk',
    'TransferRequest',
    # Services
    'DiscoveryService',
    'FileTransferService',
    # UI
    'QuickShareApp',
]
