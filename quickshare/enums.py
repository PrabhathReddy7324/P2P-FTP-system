"""
QuickShare - Enumerations
"""

from enum import Enum


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
