"""
QuickShare - Tkinter User Interface
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import socket
import threading
import os
from typing import Optional, Dict, Callable

from .models import DeviceInfo, TransferRequest
from .discovery import DiscoveryService
from .transfer import FileTransferService


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
