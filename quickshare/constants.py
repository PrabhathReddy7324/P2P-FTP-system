"""
QuickShare - Constants and Configuration
"""

# Network ports
DISCOVERY_PORT = 45678
TRANSFER_PORT = 45679

# Protocol
SERVICE_IDENTIFIER = "QUICKSHARE_V1"

# Timing (milliseconds)
BROADCAST_INTERVAL_MS = 3000
STALE_THRESHOLD_SECONDS = 15

# Transfer settings
CHUNK_SIZE = 64 * 1024  # 64KB
BUFFER_SIZE = 256 * 1024  # 256KB
