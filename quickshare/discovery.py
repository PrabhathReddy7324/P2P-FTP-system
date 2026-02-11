"""
QuickShare - UDP Discovery Service
"""

import socket
import threading
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Callable

from .constants import (
    DISCOVERY_PORT, TRANSFER_PORT, SERVICE_IDENTIFIER,
    BROADCAST_INTERVAL_MS, STALE_THRESHOLD_SECONDS
)
from .enums import DeviceStatus
from .models import DeviceInfo


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
