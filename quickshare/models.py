"""
QuickShare - Data Models
"""

import uuid
import base64
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional

from .constants import TRANSFER_PORT, CHUNK_SIZE
from .enums import DeviceStatus, MessageType, TransferStatus


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
