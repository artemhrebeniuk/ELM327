import sys
import socket
import threading
import time
import cv2
import numpy as np
import obd_gui_qt

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QComboBox, QFileDialog, QSizePolicy, QProgressBar, QGraphicsDropShadowEffect, QListView)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QRect, QRectF, QPoint, QPointF, QObject, QEvent, QPropertyAnimation, QEasingCurve, QAbstractAnimation
from PyQt5.QtGui import QImage, QPixmap, QPainter, QFont, QColor, QLinearGradient, QPen, QBrush, QPainterPath, QPolygon, QIcon

APP_STYLESHEET = """
QMainWindow { 
    background-color: #0B0F19; /* Very dark slate */
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}

#controls_container {
    background-color: rgba(15, 23, 42, 240); /* Slate 900 glass */
    border-top: 1px solid rgba(56, 189, 248, 60); /* Ice blue rim light */
    border-top-left-radius: 24px;
    border-top-right-radius: 24px;
}

#header_label, #slider_label {
    color: #94A3B8; 
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 1.5px;
}

#val_label {
    color: #E0F2FE; /* Sky 100 */
    font-size: 18px;
    font-weight: 900;
    min-width: 55px;
}

#info_panel {
    background-color: rgba(30, 41, 59, 200);
    border-radius: 14px; /* Standardize */
    border: 1px solid rgba(56, 189, 248, 80);
}

#speed_val {
    color: #FFFFFF;
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 1px;
}

#speed_unit {
    color: #38BDF8; /* Sky 400 */
    font-size: 13px;
    font-weight: 900;
    margin-top: 6px;
    letter-spacing: 1px;
}

#frame_val {
    color: #94A3B8;
    font-size: 12px;
    font-weight: 800;
    font-family: monospace;
    margin-top: 4px;
}

#action_btn {
    background-color: rgba(30, 41, 59, 255); 
    color: #F8FAFC;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 14px;
    padding: 14px 28px;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.5px;
}
#action_btn:hover { background-color: rgba(51, 65, 85, 255); border-color: rgba(255,255,255,60); }
#action_btn:pressed { background-color: #0F172A; }

#obd_btn {
    background-color: rgba(14, 165, 233, 20); /* Transparent Blue */
    color: #38BDF8;
    border: 1px solid #38BDF8;
    border-radius: 14px;
    padding: 14px 28px;
    font-size: 18px;
    font-weight: 900;
    letter-spacing: 0.5px;
}
#obd_btn:hover {
    background-color: #38BDF8; 
    color: #0F172A;
}
#obd_btn:pressed { background-color: #0284C7; color: #FFFFFF; }

#proj_btn {
    background-color: rgba(30, 41, 59, 255); 
    color: #F8FAFC;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 14px;
    padding: 14px 28px;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.5px;
}
#proj_btn:hover { background-color: rgba(51, 65, 85, 255); border-color: rgba(255,255,255,60); }
#proj_btn:pressed { background-color: #0F172A; }

#proj_btn[active="true"] {
    background-color: rgba(14, 165, 233, 20);
    color: #38BDF8;
    border: 1px solid #38BDF8;
}
#proj_btn[active="true"]:hover {
    background-color: #38BDF8;
    color: #0F172A;
}

QComboBox {
    combobox-popup: 0;
    background-color: rgba(30, 41, 59, 255);
    color: #F8FAFC;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 14px;
    padding: 14px 28px;
    font-size: 18px;
    font-weight: 800;
}
QComboBox:hover { border-color: #38BDF8; background-color: #1E293B; }

QComboBox::drop-down {
    border: none;
    width: 30px;
}
QComboBox::down-arrow {
    width: 14px;
    height: 14px;
}

QComboBox QFrame {
    background-color: transparent;
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #1E293B;
    color: #F8FAFC;
    selection-background-color: #38BDF8;
    selection-color: #0F172A;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 12px; /* Standardize */
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 38px;
    padding-left: 12px;
    border-radius: 8px;
    margin: 2px;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #38BDF8;
    color: #0F172A;
}

QSlider {
    min-height: 40px;
}
QSlider::groove:horizontal {
    border: none;
    height: 10px;
    background: rgba(255, 255, 255, 30); /* Make inactive track more visible */
    border-radius: 5px;
}
QSlider::sub-page:horizontal {
    background: #38BDF8; /* Sky 400 */
    border-radius: 5px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 2px solid #38BDF8;
    width: 20px;
    height: 20px;
    margin: -7px 0;
    border-radius: 12px;
}
QSlider::handle:horizontal:hover {
    background: #E0F2FE;
    border: 4px solid #0284C7;
    width: 22px;
    height: 22px;
    margin: -10px -1px;
    border-radius: 15px;
}

QProgressBar {
    border: 1px solid rgba(56, 189, 248, 80);
    border-radius: 12px;
    text-align: center;
    color: #FFFFFF;
    font-weight: 900;
    background: #0F172A;
    height: 24px;
    font-size: 14px;
    letter-spacing: 1px;
}
QProgressBar::chunk {
    background-color: #38BDF8;
    border-radius: 10px;
}
"""

class LoadingSpinner(QWidget):
    """
    Custom loading spinner widget that draws an animated rotating ring.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(16) # ~60 FPS
        self.setFixedSize(24, 24)

    def rotate(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect().adjusted(2, 2, -2, -2)
        
        # Draw dark track
        pen = QPen(QColor(56, 189, 248, 30), 2.5)
        painter.setPen(pen)
        painter.drawEllipse(rect)
        
        # Draw rotating arc highlight
        pen.setColor(QColor("#38BDF8")) # Sky 400
        painter.setPen(pen)
        painter.drawArc(rect, -self.angle * 16, 120 * 16)

class DynamicProgressBar(QWidget):
    """
    Custom premium progress bar with diagonal animated gloss highlight.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.max_value = 100
        self.anim_offset = 0.0
        
        # Smooth gloss animation timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(25) # ~40 FPS

    def animate(self):
        if self.value > 0 and self.value < self.max_value:
            self.anim_offset += 1.2
            if self.anim_offset > 80:
                self.anim_offset = 0
            self.update()

    def setValue(self, val):
        self.value = max(0, min(val, self.max_value))
        self.update()

    def setRange(self, min_val, max_val):
        self.max_value = max_val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        h = rect.height()
        r = h / 2.0
        
        # Draw background track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220)) # Slate 900
        painter.drawRoundedRect(rect, r, r)
        
        if self.max_value > 0 and self.value > 0:
            pct = self.value / self.max_value
            chunk_w = int(rect.width() * pct)
            
            if chunk_w >= 4:
                chunk_rect = QRect(0, 0, chunk_w, rect.height())
                
                # Draw main progress chunk with a sky blue gradient
                grad = QLinearGradient(0, 0, rect.width(), 0)
                grad.setColorAt(0.0, QColor("#0EA5E9")) # Sky 500
                grad.setColorAt(0.5, QColor("#38BDF8")) # Sky 400
                grad.setColorAt(1.0, QColor("#818CF8")) # Indigo 400
                
                painter.setBrush(grad)
                painter.drawRoundedRect(chunk_rect, r, r)
                
                # Render animated diagonal gloss lines
                painter.save()
                clip_path = QPainterPath()
                clip_path.addRoundedRect(QRectF(chunk_rect), r, r)
                painter.setClipPath(clip_path)
                
                highlight_pen = QPen(QColor(255, 255, 255, 35), 5)
                highlight_pen.setCapStyle(Qt.RoundCap)
                painter.setPen(highlight_pen)
                
                stripe_spacing = 40
                offset = int(self.anim_offset) % stripe_spacing
                for x in range(-stripe_spacing, chunk_w + stripe_spacing, stripe_spacing):
                    painter.drawLine(x + offset, -5, x + offset - 10, h + 5)
                
                painter.restore()

class UdpListener(QThread):
    """
    Background thread that listens for UDP packets containing telemetry data (speed).
    Passes data directly to the playback thread to eliminate signal-routing latency.
    """
    def __init__(self, playback_thread, port: int = 28765):
        super().__init__()
        self.playback_thread = playback_thread
        self.port = port
        self.is_running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2.0)
        try:
            self.sock.bind(('127.0.0.1', self.port))
            print(f"Listening for UDP on port {self.port}")
        except Exception as e:
            print(f"UDP Bind Error: {e}")

    def run(self):
        while self.is_running:
            try:
                data, addr = self.sock.recvfrom(1024)
                speed = float(data.decode('utf-8'))
                self.playback_thread.update_speed(speed)
            except socket.timeout:
                # If no data received for 2.0s, assume disconnected and reset speed to 0
                self.playback_thread.update_speed(0.0)
            except Exception as e:
                pass

    def stop(self):
        self.is_running = False
        try:
            self.sock.close()
        except:
            pass

class VideoLoader(QThread):
    """
    Background thread for loading video frames into memory asynchronously.
    
    This thread decodes the video using OpenCV, compresses frames into memory 
    using JPEG encoding to save RAM, and emits progress signals to the UI.
    """
    progress_updated = pyqtSignal(int, str)
    finished_loading = pyqtSignal(list, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.is_running = True

    def run(self):
        try:
            cap = cv2.VideoCapture(self.path)
            if not cap.isOpened():
                self.error_occurred.emit("Could not open video file.")
                return
                
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                total_frames = 1
                
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            
            cache = []
            frame_idx = 0
            
            while self.is_running:
                ret, frame = cap.read()
                if not ret:
                    break
                    
                # Compress frame to JPEG in memory (100% quality — visually lossless, saves ~10x RAM vs raw PNG)
                success, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
                if success:
                    cache.append(encoded.tobytes())
                    
                frame_idx += 1
                if frame_idx % 5 == 0:
                    prog = min(100, int((frame_idx / total_frames) * 100))
                    # Accurate RAM estimation: sum actual sizes of last N frames and extrapolate
                    if cache:
                        sample = cache[-min(5, len(cache)):]
                        avg_size = sum(len(b) for b in sample) / len(sample)
                        ram_mb = (len(cache) * avg_size) / (1024 * 1024)
                    else:
                        ram_mb = 0
                    self.progress_updated.emit(prog, f"Loading frames into RAM... {prog}% ({ram_mb:.0f} MB)")
            
            cap.release()
            
            if self.is_running:
                if len(cache) == 0:
                    self.error_occurred.emit("No frames could be extracted.")
                else:
                    self.finished_loading.emit(cache, fps)
                
        except Exception as e:
            self.error_occurred.emit(str(e))

    def stop(self):
        self.is_running = False

class PlaybackThread(QThread):
    """
    Thread responsible for calculating and emitting the current video frame based on vehicle telemetry.
    
    Features:
    - Target frame calculation using dynamically adjusted video speed.
    - Exponential smoothing of raw telemetry to prevent jitter and UI flashing.
    - Two playback modes: 
        1: Reversible (Dynamic) - rewinds on deceleration.
        2: Forward Only - stops when decelerating, plays forward when moving.
    """
    frame_ready = pyqtSignal(QImage)
    info_updated = pyqtSignal(float, float, int, int) # smoothed_speed, delta_frames, current_frame, total

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.frames_cache = []
        self.total_frames = 0
        self.fps = 30.0
        
        self.current_frame_float = 0.0
        self.smoothed_speed = 0.0
        self.current_speed = 0.0
        self.last_speed = 0.0
        
        self.sensitivity = 1.0
        self.smoothing_alpha = 0.2
        self.mode = 0 # 0: Reversible, 1: Classic, 2: Autoplay
        self.autoplay_playing = True
        
        self.lock = threading.Lock()
        self.last_emitted_target = -1
        self.rewind_factor = 1.0
        
        # Telemetry interpolation variables for slow/delayed OBD adapters
        self.last_packet_time = 0.0
        self.average_packet_interval = 0.1 # Dynamic moving average of packet intervals
        self.last_raw_speed = 0.0
        self.target_raw_speed = 0.0
        self.packet_received_time = 0.0
        self.last_loop_time = 0.0

    def update_speed(self, speed_val):
        with self.lock:
            now = time.time()
            if self.last_packet_time > 0:
                interval = now - self.last_packet_time
                # Smoothly estimate average packet interval (clamp between 0.02s and 2.0s to avoid extremes)
                if 0.02 < interval < 2.0:
                    self.average_packet_interval = self.average_packet_interval * 0.85 + interval * 0.15
            
            self.last_packet_time = now
            self.last_raw_speed = self.current_speed
            self.target_raw_speed = speed_val
            self.packet_received_time = now
            
    def update_settings(self, sensitivity, smoothing_alpha, mode):
        with self.lock:
            self.sensitivity = sensitivity
            self.smoothing_alpha = smoothing_alpha
            self.mode = mode

    def set_autoplay_state(self, playing: bool):
        with self.lock:
            self.autoplay_playing = playing

    def load_cache(self, cache, fps):
        with self.lock:
            self.frames_cache = cache
            self.total_frames = len(cache)
            self.fps = fps
            self.current_frame_float = 0.0
            self.last_emitted_target = -1

    def run(self):
        self.last_loop_time = time.time()
        while self.is_running:
            start_time = time.time()
            dt = start_time - self.last_loop_time
            self.last_loop_time = start_time
            if dt <= 0.0 or dt > 0.2:
                dt = 0.016 # Default fallback for frame rate drop / startup
            
            # Acquire lock for state computation only (no sleep inside lock)
            target = -1
            jpeg_bytes = None
            c_speed = 0.0
            c_total = 0
            
            with self.lock:
                if self.total_frames == 0 or not self.frames_cache:
                    pass  # Will sleep outside lock below
                else:
                    # Save previous interpolated speed to calculate acceleration
                    self.last_speed = self.current_speed
                    
                    # 1. Smoothly interpolate raw speed based on time elapsed since the last UDP packet
                    if self.packet_received_time > 0:
                        t_elapsed = time.time() - self.packet_received_time
                        if self.average_packet_interval > 0:
                            fraction = min(1.0, t_elapsed / self.average_packet_interval)
                        else:
                            fraction = 1.0
                        self.current_speed = self.last_raw_speed + (self.target_raw_speed - self.last_raw_speed) * fraction
                    else:
                        self.current_speed = self.target_raw_speed
                    
                    # 2. Apply standard exponential smoothing (EMA) on top to filter out high-frequency noise
                    self.smoothed_speed += (self.current_speed - self.smoothed_speed) * self.smoothing_alpha
                    
                    # Clamp speed to 0.0 to prevent fractional power of negative floats (which yields complex numbers in Python)
                    clamped_speed = max(0.0, self.smoothed_speed)
                    base_rate = self.fps * dt
                    
                    if self.mode == 0:
                        acceleration = self.current_speed - self.last_speed
                        if abs(acceleration) < 0.005: # Lower threshold since interpolated speed changes smoothly
                            direction = 1.0
                        else:
                            direction = 1.0 if acceleration >= 0 else -1.0
                            
                        # Non-linear speed scaling: smooths out high speeds
                        # 30 km/h = 1.0x multiplier, 100 km/h = ~2.2x multiplier (instead of 10x)
                        speed_multiplier = (clamped_speed / 30.0) ** 0.65
                        delta_frames = base_rate * speed_multiplier * self.sensitivity * direction
                    elif self.mode == 1:
                        speed_multiplier = (clamped_speed / 30.0) ** 0.65
                        delta_frames = base_rate * speed_multiplier * self.sensitivity
                    else: # Mode 2: Autoplay (Loop)
                        if self.autoplay_playing:
                            delta_frames = base_rate * self.sensitivity
                        else:
                            delta_frames = 0.0
                            
                    # Global logic: if stopped or disconnected, smoothly rewind to frame 0 (only for telemetry modes)
                    if self.mode != 2 and clamped_speed < 0.5:
                        if self.current_frame_float > 0.0:
                            # Smoothly rewind: starts at 1.5x and accelerates over time (to avoid long waiting times)
                            rewind_speed = base_rate * 1.5 * self.rewind_factor
                            delta_frames = -rewind_speed
                            self.current_frame_float = max(0.0, self.current_frame_float + delta_frames)
                            # Increment rewind factor to accelerate the longer we are stopped (max speed cap of 15x normal speed)
                            self.rewind_factor = min(10.0, self.rewind_factor + 0.03)
                        else:
                            delta_frames = 0.0
                            self.current_frame_float = 0.0
                            self.rewind_factor = 1.0
                    else:
                        self.rewind_factor = 1.0
                        self.current_frame_float += delta_frames
                        self.current_frame_float %= self.total_frames
                            
                    target = int(self.current_frame_float)
                    c_speed = self.smoothed_speed
                    c_total = self.total_frames
                    
                    # Copy frame data inside lock to prevent race condition with load_cache()
                    if target != self.last_emitted_target and 0 <= target < self.total_frames:
                        jpeg_bytes = self.frames_cache[target]
            
            # Decode and emit outside lock (heavy CPU work should not hold the lock)
            if jpeg_bytes is not None:
                frame_data = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    h, w, ch = frame.shape
                    bytes_per_line = ch * w
                    qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_BGR888).copy()
                    
                    self.frame_ready.emit(qimg)
                    self.last_emitted_target = target
                    self.info_updated.emit(c_speed, delta_frames, target, c_total)
            
            elapsed = time.time() - start_time
            sleep_time = max(0, 0.016 - elapsed)
            time.sleep(sleep_time)

    def stop(self):
        self.is_running = False

class VideoDisplayWidget(QWidget):
    """
    Custom widget to display the decoded video frames.
    
    Features:
    - Maintains the video's aspect ratio (letterboxing).
    - Supports drag & drop file opening.
    - Emits a click signal to open file dialogs.
    """
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text = "Drag and Drop Video Here"
        self.loading_overlay = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.loading_overlay:
            self.loading_overlay.resize(self.size())

    def set_image(self, img):
        self.image = img
        self.update()

    def set_text(self, text):
        self.text = text
        self.image = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)  # Bilinear interpolation for lossless scaling
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b0c10"))
        if self.image and not self.image.isNull():
            w, h = self.width(), self.height()
            iw, ih = self.image.width(), self.image.height()
            
            scaled_w = w
            scaled_h = int(ih * w / iw)
            if scaled_h > h:
                scaled_h = h
                scaled_w = int(iw * h / ih)
                
            x = (w - scaled_w) // 2
            y = (h - scaled_h) // 2
            
            # Hardware accelerated scale & draw with smooth interpolation
            painter.drawImage(QRect(x, y, scaled_w, scaled_h), self.image)
        else:
            painter.setPen(QColor("#a1a7c4"))
            font = QFont()
            font.setPointSize(28)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text)

class PremiumComboBox(QComboBox):
    """
    Custom QComboBox subclass that eliminates the default platform-dependent 
    white background bounding box around styled rounded dropdowns.
    """
    def showPopup(self):
        super().showPopup()
        
        # Find the container window and parent frame
        popup = self.view().parentWidget()
        container = self.view().window()
        
        # Style the popup container asynchronously after it is shown to prevent white background
        QTimer.singleShot(0, lambda: self._style_popup(popup, container))
        
        # Manually align popup to the combobox with collision detection for screen bounds
        if popup:
            global_pos = self.mapToGlobal(self.rect().bottomLeft())
            screen = self.screen().geometry()
            
            # Check if popup fits below the combobox
            if global_pos.y() + 2 + popup.height() > screen.bottom():
                # Not enough space below (e.g. fullscreen at the bottom of the screen) -> Drop UP
                popup_y = global_pos.y() - self.height() - popup.height() - 2
                popup.setGeometry(global_pos.x(), popup_y, self.width(), popup.height())
            else:
                # Plenty of space -> Drop DOWN
                popup.setGeometry(global_pos.x(), global_pos.y() + 2, self.width(), popup.height())

    def _style_popup(self, popup, container):
        try:
            if container:
                container.setAttribute(Qt.WA_TranslucentBackground, True)
                container.setStyleSheet("background: transparent; border: none;")
            if popup:
                popup.setAttribute(Qt.WA_TranslucentBackground, True)
                popup.setStyleSheet("background: transparent; border: none;")
        except Exception:
            pass

class ExternalVideoWindow(QWidget):
    """
    Borderless, resizable, and draggable secondary window for video projection.
    Uses custom mouse events to support dragging/resizing on macOS/Windows.
    """
    closed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OBD Video Projection")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumSize(400, 225)
        
        # Set window icon
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(script_dir, "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        
        self.image = None
        self.drag_start_pos = None
        self.window_start_geo = None
        self.is_resizing = False
        
        self.setMouseTracking(True)

    def set_image(self, img):
        self.image = img
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)  # Bilinear interpolation for lossless scaling
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#000000"))
        
        if self.image and not self.image.isNull():
            w, h = self.width(), self.height()
            iw, ih = self.image.width(), self.image.height()
            
            scaled_w = w
            scaled_h = int(ih * w / iw)
            if scaled_h > h:
                scaled_h = h
                scaled_w = int(iw * h / ih)
                
            x = (w - scaled_w) // 2
            y = (h - scaled_h) // 2
            
            # Smooth scaling preserves original video quality
            painter.drawImage(QRect(x, y, scaled_w, scaled_h), self.image)
        else:
            painter.setPen(QColor("#38BDF8"))
            font = QFont("Segoe UI", 13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "PROJECTOR MODE ACTIVE\nDouble-click to Maximize")
            
        # Draw frame border and resize grip if not fullscreen
        if not self.isFullScreen():
            # Thin elegant cyan outline
            painter.setPen(QPen(QColor(56, 189, 248, 60), 2))
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
            
            # Triangle resize grip at bottom-right
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(56, 189, 248, 150))
            w, h = self.width(), self.height()
            grip = QPolygon([
                QPoint(w - 15, h),
                QPoint(w, h - 15),
                QPoint(w, h)
            ])
            painter.drawPolygon(grip)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            w, h = self.width(), self.height()
            
            # Check bottom-right corner for resize drag
            if pos.x() >= w - 20 and pos.y() >= h - 20:
                self.is_resizing = True
            else:
                self.is_resizing = False
                
            self.drag_start_pos = event.globalPos()
            self.window_start_geo = self.geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        w, h = self.width(), self.height()
        
        # Change cursor depending on hover position
        if not self.isFullScreen() and pos.x() >= w - 20 and pos.y() >= h - 20:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor if not self.isFullScreen() else Qt.ArrowCursor)
            
        if event.buttons() & Qt.LeftButton:
            if self.drag_start_pos is not None:
                delta = event.globalPos() - self.drag_start_pos
                if self.is_resizing:
                    new_w = max(self.minimumWidth(), self.window_start_geo.width() + delta.x())
                    new_h = max(self.minimumHeight(), self.window_start_geo.height() + delta.y())
                    self.resize(new_w, new_h)
                else:
                    self.move(self.window_start_geo.topLeft() + delta)
                event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        self.window_start_geo = None
        self.is_resizing = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_fullscreen()
            event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
            else:
                self.close()
            event.accept()
        elif event.key() == Qt.Key_F:
            self.toggle_fullscreen()
            event.accept()
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.update()

    def closeEvent(self, event):
        self.closed_signal.emit()
        event.accept()

class UpwardPopupFilter(QObject):
    def __init__(self, combobox, popup):
        super().__init__(popup)
        self.combobox = combobox
        self.popup = popup
        self.is_positioning = False
        self.animation = None
        self.target_geom = None

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Move, QEvent.Resize):
            # If the custom slide-up animation is running, let it control the geometry
            if self.animation and self.animation.state() == QAbstractAnimation.Running:
                return False
                
            if not self.is_positioning:
                self.is_positioning = True
                rect = self.combobox.rect()
                pos = self.combobox.mapToGlobal(rect.topLeft())
                popup_height = self.popup.height()
                if event.type() == QEvent.Resize:
                    popup_height = event.size().height()
                new_y = pos.y() - popup_height - 4
                
                self.target_geom = QRect(pos.x(), new_y, self.popup.width(), popup_height)
                self.popup.move(pos.x(), new_y)
                self.is_positioning = False
                if event.type() == QEvent.Move:
                    return True # Block original down-move event
                    
        elif event.type() == QEvent.Show:
            if self.target_geom:
                rect = self.combobox.rect()
                pos = self.combobox.mapToGlobal(rect.topLeft())
                
                # Start geometry has height 0, positioned at the top of the combobox
                start_geom = QRect(self.target_geom.x(), pos.y() - 4, self.target_geom.width(), 0)
                
                self.is_positioning = True
                self.popup.setGeometry(start_geom)
                self.is_positioning = False
                
                # Animate slide-up from bottom (combobox top) to top
                self.animation = QPropertyAnimation(self.popup, b"geometry")
                self.animation.setDuration(160) # Fast premium slide-up (160ms)
                self.animation.setStartValue(start_geom)
                self.animation.setEndValue(self.target_geom)
                self.animation.setEasingCurve(QEasingCurve.OutCubic)
                self.animation.start()
                
        return super().eventFilter(obj, event)

class UpwardComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup_filter = None

    def showPopup(self):
        # Temporarily disable standard combo box pop down animation to prevent conflicts
        old_effects = QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, False)
        
        # Turn off scrollbars to prevent them from flashing/showing during animation
        self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        popup = self.view().window()
        container = self.view().parentWidget()
        
        # Style the popup container to prevent the white background "miracle"
        for widget in (popup, container):
            if widget:
                widget.setAttribute(Qt.WA_TranslucentBackground, True)
                if widget.isWindow():
                    widget.setWindowFlags(widget.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
                # Assign a specific object name and target only this container so it doesn't cascade
                # and make the actual drop-down list items transparent.
                widget.setObjectName("TransparentPopupContainer")
                widget.setStyleSheet("QWidget#TransparentPopupContainer { background: transparent; border: none; }")
        
        if not self.popup_filter:
            self.popup_filter = UpwardPopupFilter(self, popup)
            popup.installEventFilter(self.popup_filter)
            
        super().showPopup()
        
        # Restore standard animations
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo, old_effects)

class VideoPlayerWidget(QMainWindow):
    """
    The main GUI application for the Adaptive Video Player.
    
    Initializes the user interface, binds signals to slots, handles the 
    window layout, and controls the lifecycle of background threads.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OBD-II Adaptive Video Player")
        self.setGeometry(100, 100, 1280, 750)
        self.setMinimumSize(1024, 600) # Increased minimum width to prevent UI clipping when minimized
        self.setAcceptDrops(True)
        
        # Set window icon
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(script_dir, "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        
        self.is_fullscreen = False
        self.loader_thread = None
        self.external_window = None
        
        self.init_ui()
        self.apply_theme()
        self.showMaximized()  # Launch maximized for best Full HD experience
        
        self.playback_thread = PlaybackThread()
        self.playback_thread.frame_ready.connect(self.on_frame_ready)
        self.playback_thread.info_updated.connect(self.on_info_updated)
        self.playback_thread.start()

        self.udp_listener = UdpListener(self.playback_thread)
        self.udp_listener.start()
        
        # Connect UI changes directly to the thread
        self.sens_slider.valueChanged.connect(self.sync_settings)
        self.smooth_slider.valueChanged.connect(self.sync_settings)
        self.mode_dropdown.currentIndexChanged.connect(self.sync_settings)
        self.sync_settings()

    def sync_settings(self):
        sens_val = self.sens_slider.value() / 10.0
        smooth_val = self.smooth_slider.value() / 100.0
        mode_idx = self.mode_dropdown.currentIndex()
        
        # Show or hide play/pause control depending on playback mode
        if hasattr(self, 'play_pause_btn'):
            if mode_idx == 2:
                self.play_pause_btn.show()
            else:
                self.play_pause_btn.hide()
        
        if hasattr(self, 'sens_val_label'):
            self.sens_val_label.setText(f"{sens_val:.1f}x")
        if hasattr(self, 'smooth_val_label'):
            self.smooth_val_label.setText(f"{smooth_val:.2f}")
            
        self.playback_thread.update_settings(
            sensitivity=sens_val,
            smoothing_alpha=smooth_val,
            mode=mode_idx
        )

    def toggle_play_pause(self):
        is_playing = getattr(self, 'autoplay_is_playing', True)
        is_playing = not is_playing
        self.autoplay_is_playing = is_playing
        
        self.playback_thread.set_autoplay_state(is_playing)
        if is_playing:
            self.play_pause_btn.setText("⏸ PAUSE")
        else:
            self.play_pause_btn.setText("▶ PLAY")

    def init_ui(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Video Display Widget
        self.video_display = VideoDisplayWidget(self.central_widget)
        self.video_display.clicked.connect(self.open_file_dialog)
        self.main_layout.addWidget(self.video_display)
             # Loading Screen Overlay
        self.loading_widget = QWidget(self.video_display)
        self.video_display.loading_overlay = self.loading_widget
        self.loading_widget.setStyleSheet("background-color: rgba(11, 15, 25, 220);") # Deep dark overlay
        self.loading_layout = QVBoxLayout(self.loading_widget)
        self.loading_layout.setAlignment(Qt.AlignCenter)
        
        # Center HUD panel
        self.loading_panel = QWidget()
        self.loading_panel.setFixedSize(550, 200)
        self.loading_panel.setObjectName("loading_panel")
        self.loading_panel.setStyleSheet("""
            #loading_panel {
                background-color: rgba(30, 41, 59, 230);
                border: 1px solid rgba(56, 189, 248, 80);
                border-radius: 16px;
            }
        """)
        
        panel_layout = QVBoxLayout(self.loading_panel)
        panel_layout.setContentsMargins(30, 25, 30, 25)
        panel_layout.setSpacing(15)
        
        # Top row of HUD: Spinner & Title
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.setAlignment(Qt.AlignCenter)
        
        self.loading_spinner = LoadingSpinner()
        title_row.addWidget(self.loading_spinner)
        
        self.load_label = QLabel("INITIALIZING PRECACHE...")
        self.load_label.setStyleSheet("""
            color: #38BDF8; 
            font-size: 15px; 
            font-weight: 900; 
            letter-spacing: 2px;
            background: transparent;
        """)
        self.load_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_row.addWidget(self.load_label)
        panel_layout.addLayout(title_row)
        
        # Middle row: custom animated progress bar
        self.load_bar = DynamicProgressBar()
        self.load_bar.setFixedHeight(14)
        panel_layout.addWidget(self.load_bar)
        
        # Bottom row: stats (Left) and percentage (Right)
        bottom_row = QHBoxLayout()
        
        self.load_stats_label = QLabel("INITIALIZING...")
        self.load_stats_label.setStyleSheet("""
            color: #94A3B8;
            font-size: 14px;
            font-weight: 700;
            background: transparent;
        """)
        self.load_stats_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        bottom_row.addWidget(self.load_stats_label)
        
        bottom_row.addStretch()
        
        self.load_pct_label = QLabel("0%")
        self.load_pct_label.setStyleSheet("""
            color: #FFFFFF; 
            font-size: 24px; 
            font-weight: 900;
            background: transparent;
        """)
        self.load_pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_row.addWidget(self.load_pct_label)
        panel_layout.addLayout(bottom_row)
        
        load_shadow = QGraphicsDropShadowEffect(self)
        load_shadow.setBlurRadius(50)
        load_shadow.setColor(QColor(56, 189, 248, 40))
        load_shadow.setOffset(0, 0)
        self.loading_panel.setGraphicsEffect(load_shadow)
        
        self.loading_layout.addWidget(self.loading_panel)
        self.loading_widget.hide()

        # Controls Container (Bottom Panel)
        self.controls_widget = QWidget(self.central_widget)
        self.controls_widget.setObjectName("controls_container")
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.setContentsMargins(24, 22, 24, 22)
        controls_layout.setSpacing(15)
 
        # Top row: Buttons and Mode
        top_row = QHBoxLayout()
        top_row.setSpacing(12) # Reduced spacing to conserve horizontal pixels
        
        self.load_btn = QPushButton("📂 LOAD VIDEO")
        self.load_btn.setObjectName("action_btn")
        self.load_btn.setCursor(Qt.PointingHandCursor)
        self.load_btn.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        self.load_btn.clicked.connect(self.open_file_dialog)
        top_row.addWidget(self.load_btn)

        self.launch_obd_btn = QPushButton("🚀 START SCANNER")
        self.launch_obd_btn.setObjectName("obd_btn")
        self.launch_obd_btn.setCursor(Qt.PointingHandCursor)
        self.launch_obd_btn.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        self.launch_obd_btn.clicked.connect(self.launch_obd_scanner)
        
        # Premium Glow for Scanner Button
        obd_glow = QGraphicsDropShadowEffect(self)
        obd_glow.setBlurRadius(25)
        obd_glow.setColor(QColor(56, 189, 248, 80)) # Ice blue glow
        obd_glow.setOffset(0, 0)
        self.launch_obd_btn.setGraphicsEffect(obd_glow)
        top_row.addWidget(self.launch_obd_btn)
        
        # Projection Button
        self.proj_btn = QPushButton("📺 PROJECTION")
        self.proj_btn.setObjectName("proj_btn")
        self.proj_btn.setCursor(Qt.PointingHandCursor)
        self.proj_btn.setFocusPolicy(Qt.NoFocus)
        self.proj_btn.clicked.connect(self.toggle_projection)
        top_row.addWidget(self.proj_btn)
 
        top_row.addStretch()

        mode_label = QLabel("MODE:")
        mode_label.setObjectName("header_label")
        top_row.addWidget(mode_label)

        self.mode_dropdown = UpwardComboBox()
        self.mode_dropdown.addItems([
            "1: Reversible (Dynamic)", 
            "2: Classic (Forward Only)",
            "3: Autoplay (Loop)"
        ])
        self.mode_dropdown.setCursor(Qt.PointingHandCursor)
        self.mode_dropdown.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        self.mode_dropdown.setFixedWidth(340) # Prevent dropdown from shrinking and ensure text fits
        
        # Configure drop-down list view to render rounded corners
        self.mode_dropdown.setView(QListView())
        
        # Premium Glow for Combo Box
        combo_glow = QGraphicsDropShadowEffect(self)
        combo_glow.setBlurRadius(20)
        combo_glow.setColor(QColor(56, 189, 248, 30)) 
        combo_glow.setOffset(0, 0)
        self.mode_dropdown.setGraphicsEffect(combo_glow)
        
        top_row.addWidget(self.mode_dropdown)
        
        # Play / Pause button for Autoplay Mode (hidden by default)
        self.play_pause_btn = QPushButton("⏸ PAUSE")
        self.play_pause_btn.setObjectName("action_btn")
        self.play_pause_btn.setCursor(Qt.PointingHandCursor)
        self.play_pause_btn.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        self.play_pause_btn.setMinimumWidth(160) # Ensure text is never truncated
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        self.autoplay_is_playing = True
        
        # Premium Glow for Play/Pause Button
        play_glow = QGraphicsDropShadowEffect(self)
        play_glow.setBlurRadius(25)
        play_glow.setColor(QColor(56, 189, 248, 60))
        play_glow.setOffset(0, 0)
        self.play_pause_btn.setGraphicsEffect(play_glow)
        self.play_pause_btn.hide()
        
        top_row.addWidget(self.play_pause_btn)

        # Premium Telemetry Display — no second stretch so it stays visible at any window width
        self.info_panel = QWidget()
        self.info_panel.setObjectName("info_panel")
        self.info_panel.setMinimumWidth(180)  # Can grow but won't overflow at small widths
        self.info_panel.setAttribute(Qt.WA_StyledBackground, True) # Fixes jagged edges on rounded borders in Qt
        
        # Premium Glow for Info Panel
        self.info_glow = QGraphicsDropShadowEffect(self)
        self.info_glow.setBlurRadius(20)
        self.info_glow.setColor(QColor(56, 189, 248, 40)) 
        self.info_glow.setOffset(0, 0)
        self.info_panel.setGraphicsEffect(self.info_glow)
        info_layout = QHBoxLayout(self.info_panel)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(6)
        
        self.speed_val_label = QLabel("0.0")
        self.speed_val_label.setObjectName("speed_val")
        self.speed_val_label.setFixedWidth(90)
        self.speed_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.speed_val_label)
        
        self.speed_unit_label = QLabel("KM/H")
        self.speed_unit_label.setObjectName("speed_unit")
        self.speed_unit_label.setFixedWidth(50)
        info_layout.addWidget(self.speed_unit_label)
        
        info_layout.addSpacing(8)
        
        self.frame_val_label = QLabel("FRAME: 0 / 0")
        self.frame_val_label.setObjectName("frame_val")
        self.frame_val_label.setFixedWidth(170)
        self.frame_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self.frame_val_label)
        
        top_row.addWidget(self.info_panel)
        controls_layout.addLayout(top_row)

        # Bottom row: Sliders
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(15)
        
        sens_label = QLabel("SENSITIVITY")
        sens_label.setObjectName("slider_label")
        bottom_row.addWidget(sens_label)

        self.sens_slider = QSlider(Qt.Horizontal)
        self.sens_slider.setRange(1, 50)
        self.sens_slider.setValue(10) # 1.0x multiplier
        self.sens_slider.setCursor(Qt.PointingHandCursor)
        self.sens_slider.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        bottom_row.addWidget(self.sens_slider)
        
        self.sens_val_label = QLabel("1.0x")
        self.sens_val_label.setObjectName("val_label")
        self.sens_val_label.setFixedWidth(52)  # Prevent layout shift when value changes
        bottom_row.addWidget(self.sens_val_label)
        
        bottom_row.addSpacing(30)

        smooth_label = QLabel("SMOOTHING")
        smooth_label.setObjectName("slider_label")
        bottom_row.addWidget(smooth_label)

        self.smooth_slider = QSlider(Qt.Horizontal)
        self.smooth_slider.setRange(1, 100)
        self.smooth_slider.setValue(20) # 0.2 alpha
        self.smooth_slider.setCursor(Qt.PointingHandCursor)
        self.smooth_slider.setFocusPolicy(Qt.NoFocus) # Prevent spacebar hijack
        bottom_row.addWidget(self.smooth_slider)
        
        self.smooth_val_label = QLabel("0.20")
        self.smooth_val_label.setObjectName("val_label")
        self.smooth_val_label.setFixedWidth(52)  # Prevent layout shift when value changes
        bottom_row.addWidget(self.smooth_val_label)

        controls_layout.addLayout(bottom_row)
        self.main_layout.addWidget(self.controls_widget)

    def apply_theme(self):
        import PyQt5.QtWidgets as qtw
        
        # 1. Main Dashboard Shadow (Floating effect)
        dash_shadow = qtw.QGraphicsDropShadowEffect(self)
        dash_shadow.setBlurRadius(40)
        dash_shadow.setColor(QColor(0, 0, 0, 180))
        dash_shadow.setOffset(0, -10)
        self.controls_widget.setGraphicsEffect(dash_shadow)
        
        # 2. Glowing effects for OBD Button
        self.obd_glow = qtw.QGraphicsDropShadowEffect(self)
        self.obd_glow.setBlurRadius(25)
        self.obd_glow.setColor(QColor(56, 189, 248, 120)) # Sky Blue glow
        self.obd_glow.setOffset(0, 0)
        self.launch_obd_btn.setGraphicsEffect(self.obd_glow)

        # 3. Glowing effect for Info Panel
        self.info_glow = qtw.QGraphicsDropShadowEffect(self)
        self.info_glow.setBlurRadius(20)
        self.info_glow.setColor(QColor(56, 189, 248, 60)) 
        self.info_glow.setOffset(0, 0)
        self.info_panel.setGraphicsEffect(self.info_glow)
        self.setStyleSheet(APP_STYLESHEET)



    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.start_loading(files[0])

    def open_file_dialog(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Video File", "", "Videos (*.mp4 *.avi *.mkv *.mov);;All Files (*)", options=options)
        if file_name:
            self.start_loading(file_name)

    def launch_obd_scanner(self):
        import subprocess
        import sys
        import os
        
        # Check if already running
        if hasattr(self, 'obd_process') and self.obd_process is not None:
            if self.obd_process.poll() is None:
                return # Already running
                
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            if getattr(sys, 'frozen', False):
                self.obd_process = subprocess.Popen([sys.executable, "--run-obd-scanner"], cwd=script_dir)
            else:
                script_path = os.path.abspath(__file__)
                self.obd_process = subprocess.Popen([sys.executable, script_path, "--run-obd-scanner"], cwd=script_dir)
                
            self.launch_obd_btn.setText("✅ SCANNER RUNNING")
            self.launch_obd_btn.setStyleSheet("background-color: #10B981; color: #FFFFFF; border: 1px solid #10B981;")
            if hasattr(self, 'obd_glow'):
                self.obd_glow.setColor(QColor(16, 185, 129, 150))
        except Exception as e:
            self.video_display.set_text(f"Launch Error: {e}")

    def start_loading(self, path):
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait()
            
        self.loading_widget.show()
        self.load_bar.setValue(0)
        self.load_label.setText("LOADING FRAMES INTO RAM...")
        self.load_stats_label.setText("INITIALIZING PRECACHE...")
        self.load_pct_label.setText("0%")
        self.video_display.set_text("Pre-caching video...")
        
        if self.external_window:
            self.external_window.set_image(None)
        
        self.loader_thread = VideoLoader(path)
        self.loader_thread.progress_updated.connect(self.on_load_progress)
        self.loader_thread.finished_loading.connect(self.on_load_finished)
        self.loader_thread.error_occurred.connect(self.on_load_error)
        self.loader_thread.start()

    def on_load_progress(self, prog, msg):
        self.load_bar.setValue(prog)
        if "(" in msg:
            stats_part = msg.split("(")[-1].replace(")", "")
            self.load_stats_label.setText(f"CACHE SIZE: {stats_part}")
        else:
            self.load_stats_label.setText("CACHING VIDEO BUNDLE")
            
        self.load_pct_label.setText(f"{prog}%")

    def on_load_finished(self, cache, fps):
        self.loading_widget.hide()
        self.playback_thread.load_cache(cache, fps)
        
    def on_load_error(self, err_msg):
        self.loading_widget.hide()
        self.video_display.set_text(f"Error: {err_msg}")

    def on_info_updated(self, smoothed_speed, delta_frames, current_frame, total_frames):
        from PyQt5.QtGui import QColor
        self.frame_val_label.setText(f"FRAME: {current_frame} / {total_frames}")
        mode_idx = self.mode_dropdown.currentIndex()
        
        if mode_idx == 2:
            # Autoplay mode: display playback rate multiplier instead of KM/H
            sens_val = self.sens_slider.value() / 10.0
            self.speed_val_label.setText(f"{sens_val:.1f}")
            self.speed_unit_label.setText("x")
            
            # Indicator color changes based on play/pause state
            is_playing = getattr(self, 'autoplay_is_playing', True)
            if is_playing:
                color = "#10B981" # Emerald Green (Playing)
                glow = QColor(16, 185, 129, 60)
            else:
                color = "#F59E0B" # Amber (Paused)
                glow = QColor(245, 158, 11, 60)
        else:
            self.speed_val_label.setText(f"{smoothed_speed:.1f}")
            self.speed_unit_label.setText("KM/H")
            
            # Dynamic color based on speed
            if smoothed_speed < 30:
                color = "#38BDF8" # Sky Blue
                glow = QColor(56, 189, 248, 60)
            elif smoothed_speed < 60:
                color = "#10B981" # Emerald Green
                glow = QColor(16, 185, 129, 60)
            elif smoothed_speed < 90:
                color = "#F59E0B" # Amber
                glow = QColor(245, 158, 11, 60)
            else:
                color = "#EF4444" # Red
                glow = QColor(239, 68, 68, 60)
            
        self.speed_val_label.setStyleSheet(f"color: {color};")
        self.speed_unit_label.setStyleSheet(f"color: {color};")
        if hasattr(self, 'info_glow'):
            self.info_glow.setColor(glow)

    def on_frame_ready(self, qimg):
        self.video_display.set_image(qimg)
        if self.external_window and self.external_window.isVisible():
            self.external_window.set_image(qimg)

    def toggle_projection(self):
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        from PyQt5.QtGui import QColor
        
        if self.external_window is None:
            self.external_window = ExternalVideoWindow()
            self.external_window.closed_signal.connect(self.close_projection)
            
            if self.video_display.image:
                self.external_window.set_image(self.video_display.image)
                
            self.external_window.show()
            self.proj_btn.setProperty("active", "true")
            self.proj_btn.setText("📺 PROJECTING")
            self.proj_btn.style().unpolish(self.proj_btn)
            self.proj_btn.style().polish(self.proj_btn)
            
            self.proj_glow = QGraphicsDropShadowEffect(self)
            self.proj_glow.setBlurRadius(25)
            self.proj_glow.setColor(QColor(56, 189, 248, 120))
            self.proj_glow.setOffset(0, 0)
            self.proj_btn.setGraphicsEffect(self.proj_glow)
        else:
            self.close_projection()

    def close_projection(self):
        if self.external_window:
            try:
                self.external_window.closed_signal.disconnect(self.close_projection)
            except:
                pass
            self.external_window.close()
            self.external_window = None
            
        self.proj_btn.setProperty("active", "false")
        self.proj_btn.setText("📺 PROJECTION")
        self.proj_btn.setGraphicsEffect(None)
        self.proj_btn.style().unpolish(self.proj_btn)
        self.proj_btn.style().polish(self.proj_btn)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key_Space:
            if self.mode_dropdown.currentIndex() == 2:
                self.toggle_play_pause()
                event.accept()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        if self.is_fullscreen:
            self.controls_widget.hide()
            self.showFullScreen()
        else:
            self.controls_widget.show()
            self.showMaximized()

    def closeEvent(self, event):
        if self.external_window:
            self.external_window.close()
            
        if hasattr(self, 'obd_process') and self.obd_process is not None:
            if self.obd_process.poll() is None:
                self.obd_process.terminate()
                
        if self.loader_thread:
            self.loader_thread.stop()
            self.loader_thread.wait()
        self.playback_thread.stop()
        self.playback_thread.wait()
        self.udp_listener.stop()
        self.udp_listener.wait()
        event.accept()

if __name__ == "__main__":
    # Enable High-DPI scaling for BOTH modes (video player AND obd scanner)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    if "--run-obd-scanner" in sys.argv:
        import obd_gui_qt
        app = QApplication(sys.argv)
        window = obd_gui_qt.OBDDashboardQT()
        window.show()
        sys.exit(app.exec_())
    else:
        app = QApplication(sys.argv)
        player = VideoPlayerWidget()
        player.show()
        sys.exit(app.exec_())
