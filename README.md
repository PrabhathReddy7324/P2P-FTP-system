# QuickShare - Python P2P File Transfer

A Python/Tkinter implementation of the QuickShare P2P file transfer application with the exact same functionality as the WPF version.

## Features

- **Device Discovery**: UDP broadcast on port 45678 for automatic peer discovery
- **File Transfer**: TCP-based file transfer on port 45679
- **Chunked Transfer**: 64KB chunks with SHA-256 checksum verification
- **Receive Mode**: Toggle to broadcast availability for receiving files
- **Progress Tracking**: Real-time transfer progress display
- **Dark Theme UI**: Modern dark-themed Tkinter interface

## Requirements

- Python 3.8+
- No external dependencies (uses only standard library)

## Project Structure

```
P2P/
├── quickshare/              # Main package
│   ├── __init__.py          # Package exports
│   ├── constants.py         # Configuration (ports, chunk size, timeouts)
│   ├── enums.py             # DeviceStatus, MessageType, TransferStatus
│   ├── models.py            # Data classes (DeviceInfo, FileMetadata, etc.)
│   ├── discovery.py         # UDP discovery service
│   ├── transfer.py          # TCP file transfer service
│   └── ui.py                # Tkinter UI
├── main.py                  # Application entry point
└── README.md
```

## Usage

```bash
python main.py
```

## How It Works

1. **Start the Application**: Run `python main.py` on both sender and receiver machines
2. **Enable Receive Mode**: On the receiving machine, click "Enable Receive Mode"
3. **Select Device**: On the sender, select the receiving device from the device list
4. **Send File**: Click "Send File" or drag-and-drop files onto the drop zone
5. **Automatic Transfer**: Files are transferred with progress tracking and checksum verification
6. **Download Location**: Received files are saved to `~/Downloads/QuickShare/`

## Network Configuration

Make sure your firewall allows:
- **UDP Port 45678**: Device discovery (inbound/outbound)
- **TCP Port 45679**: File transfer (inbound/outbound)

## Protocol

### Discovery Protocol (UDP)
- Broadcasts device presence every 3 seconds
- JSON message format with device info
- Devices not seen for 15 seconds are marked as offline

### Transfer Protocol (TCP)
1. Sender connects to receiver
2. Sends `TransferRequest` with file metadata
3. Receiver responds with `TransferAccept`
4. Sender sends file in 64KB chunks with checksums
5. Receiver acknowledges each chunk
6. Final checksum verification on completion

## Limitations

- Single file transfer at a time
- LAN only (same network subnet)
- No encryption (plain text transfer)
- No resume support for interrupted transfers
