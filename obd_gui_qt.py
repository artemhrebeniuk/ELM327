import sys
import math
import threading
import time
import random
import obd
import os
import glob
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QComboBox, QPushButton, QFrame, QGridLayout, QCheckBox, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject, QRectF
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QBrush

class CircularGauge(QWidget):
    def __init__(self, parent=None, max_value=100, color="#00fa9a"):
        super().__init__(parent)
        self.max_value = max_value
        self.current_value = 0
        self.gauge_color = QColor(color)
        self.setMinimumSize(250, 250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setValue(self, value):
        self.current_value = min(max(value, 0), self.max_value)
        self.update()

    def setColor(self, color_str):
        new_color = QColor(color_str)
        if self.gauge_color != new_color:
            self.gauge_color = new_color
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        padding = 30 # Больше отступ, чтобы свечение не обрезалось краями виджета
        rect = QRectF(self.width()/2 - side/2 + padding, 
                      self.height()/2 - side/2 + padding, 
                      side - padding*2, side - padding*2)
        
        start_angle_deg = 225
        extent_angle_deg = -270
        start_angle = start_angle_deg * 16
        extent_angle = extent_angle_deg * 16

        ratio = self.current_value / self.max_value
        current_extent = int(extent_angle * ratio)

        arc_width = max(10, int(side * 0.04))

        # --- ЗАСЕЧКИ (Tick Marks) ---
        painter.save()
        painter.translate(self.width()/2, self.height()/2)
        radius = side/2 - padding + arc_width + 4
        
        tick_pen = QPen(QColor("#444b66"))
        tick_pen.setWidth(2)
        painter.setPen(tick_pen)
        
        num_ticks = 14 
        for i in range(num_ticks + 1):
            angle_deg = start_angle_deg + (extent_angle_deg * i / num_ticks)
            angle_rad = math.radians(angle_deg)
            x1 = radius * math.cos(angle_rad)
            y1 = -radius * math.sin(angle_rad) 
            x2 = (radius + 8) * math.cos(angle_rad) 
            y2 = -(radius + 8) * math.sin(angle_rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        painter.restore()

        # --- GLOW EFFECT ---
        if current_extent != 0:
            glow_color = QColor(self.gauge_color)
            for i in range(1, 6):
                glow_color.setAlpha(45 // i) 
                pen_glow = QPen(glow_color)
                pen_glow.setWidth(arc_width + i*6) 
                pen_glow.setCapStyle(Qt.RoundCap)
                painter.setPen(pen_glow)
                painter.drawArc(rect, start_angle, current_extent)

        # --- ФОНОВАЯ ДУГА ---
        pen_bg = QPen(QColor("#222533"))
        pen_bg.setWidth(arc_width)
        pen_bg.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(rect, start_angle, extent_angle)

        # --- АКТИВНАЯ ДУГА ---
        if current_extent != 0:
            pen_fg = QPen(self.gauge_color)
            pen_fg.setWidth(arc_width)
            pen_fg.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_fg)
            painter.drawArc(rect, start_angle, current_extent)

class LinearGauge(QWidget):
    def __init__(self, parent=None, max_value=100, color="#ff5e62"):
        super().__init__(parent)
        self.max_value = max_value
        self.current_value = 0
        self.gauge_color = QColor(color)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setValue(self, value):
        self.current_value = min(max(value, 0), self.max_value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        h = 10
        y = rect.height() // 2 - h // 2
        w = rect.width() - 20
        x = 10
        
        # Background
        bg_rect = QRectF(x, y, w, h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#222533"))
        painter.drawRoundedRect(bg_rect, h/2, h/2)

        if self.current_value > 0:
            ratio = self.current_value / self.max_value
            fill_w = w * ratio
            fill_rect = QRectF(x, y, fill_w, h)
            
            # Glow
            glow_color = QColor(self.gauge_color)
            for i in range(1, 5):
                glow_color.setAlpha(40 // i)
                painter.setBrush(glow_color)
                g_rect = QRectF(x, y - i*2, fill_w + i*2, h + i*4)
                painter.drawRoundedRect(g_rect, (h + i*4)/2, (h + i*4)/2)

            # Foreground
            painter.setBrush(self.gauge_color)
            painter.drawRoundedRect(fill_rect, h/2, h/2)

class OBDSignals(QObject):
    update_data = pyqtSignal(float, float, float, float, str)  # speed, rpm, coolant, battery, status
    connection_failed = pyqtSignal(str)                       # error message

class OBDDashboardQT(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OBD-II Smart Dashboard (Qt)")
        self.setGeometry(100, 100, 1280, 800)
        self.setMinimumSize(1000, 650)

        self.connection = None
        self.polling_thread = None
        self.is_running = False

        self.signals = OBDSignals()
        self.signals.update_data.connect(self.on_data_received)
        self.signals.connection_failed.connect(self.on_connection_failed)

        self.font_main = "Avenir Next"
        self.font_mono = "Menlo"

        self.log_filename = None
        self.error_log_filename = None

        self.init_ui()
        self.apply_dark_theme()

        QTimer.singleShot(200, self.refresh_ports)

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- ЛЕВАЯ ПАНЕЛЬ ---
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(25, 30, 25, 30)
        sidebar_layout.setSpacing(20)

        logo = QLabel("⚡ OBD-II ELM327", sidebar)
        logo.setFont(QFont(self.font_main, 16, QFont.Bold))
        logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo)

        line = QFrame(sidebar)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333333; max-height: 1px;")
        sidebar_layout.addWidget(line)

        port_label = QLabel("Select Port:", sidebar)
        port_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        port_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(port_label)

        self.port_dropdown = QComboBox(sidebar)
        self.port_dropdown.addItem("Auto-Detect")
        self.port_dropdown.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.port_dropdown)

        baud_label = QLabel("Select Baudrate:", sidebar)
        baud_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        baud_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(baud_label)

        self.baud_dropdown = QComboBox(sidebar)
        self.baud_dropdown.addItems(["Auto (Scan)", "38400", "9600", "115200", "230400"])
        self.baud_dropdown.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.baud_dropdown)

        proto_label = QLabel("Select Protocol:", sidebar)
        proto_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        proto_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(proto_label)

        self.proto_dropdown = QComboBox(sidebar)
        self.proto_dropdown.addItems(["Auto", "CAN 11-bit 500k (Audi)", "CAN 29-bit 500k", "CAN 11-bit 250k"])
        self.proto_dropdown.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.proto_dropdown)

        self.refresh_btn = QPushButton("Refresh Ports", sidebar)
        self.refresh_btn.setFont(QFont(self.font_main, 12, QFont.Bold))
        self.refresh_btn.clicked.connect(self.refresh_ports)
        sidebar_layout.addWidget(self.refresh_btn)

        self.demo_checkbox = QCheckBox("Demo Simulator", sidebar)
        self.demo_checkbox.setFont(QFont(self.font_main, 12))
        self.demo_checkbox.setChecked(True)
        self.demo_checkbox.stateChanged.connect(self.on_demo_toggle)
        sidebar_layout.addWidget(self.demo_checkbox)

        self.log_checkbox = QCheckBox("Log Data to CSV", sidebar)
        self.log_checkbox.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.log_checkbox)

        self.error_log_checkbox = QCheckBox("Log Errors (DTC)", sidebar)
        self.error_log_checkbox.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.error_log_checkbox)

        self.connect_btn = QPushButton("Connect", sidebar)
        self.connect_btn.setObjectName("ConnectButton")
        self.connect_btn.setFont(QFont(self.font_main, 14, QFont.Bold))
        self.connect_btn.clicked.connect(self.toggle_connection)
        sidebar_layout.addWidget(self.connect_btn)

        status_title = QLabel("Status:", sidebar)
        status_title.setFont(QFont(self.font_main, 10, QFont.Bold))
        status_title.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(status_title)

        self.status_val = QLabel("DEMO MODE ACTIVE", sidebar)
        self.status_val.setObjectName("StatusLabel")
        self.status_val.setFont(QFont(self.font_main, 11, QFont.Bold))
        self.status_val.setStyleSheet("color: #ffd700;")
        self.status_val.setWordWrap(True)
        sidebar_layout.addWidget(self.status_val)

        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)

        # --- ПРАВАЯ ПАНЕЛЬ (Dashboard) ---
        dashboard = QFrame(self)
        dashboard.setObjectName("Dashboard")
        dashboard_layout = QGridLayout(dashboard)
        dashboard_layout.setContentsMargins(25, 25, 25, 25)
        dashboard_layout.setSpacing(20)

        # 1. СПИДОМЕТР (Круговая шкала)
        self.speed_card = QFrame(dashboard)
        self.speed_card.setObjectName("SpeedCard")
        speed_layout = QVBoxLayout(self.speed_card)
        speed_layout.setContentsMargins(20, 20, 20, 20)

        self.speed_gauge = CircularGauge(self.speed_card, max_value=220, color="#00d2ff")
        speed_layout.addWidget(self.speed_gauge)

        # Текст внутри шкалы, чтобы он всегда был отцентрирован и не ломал размер шкалы
        speed_text_layout = QVBoxLayout(self.speed_gauge)
        speed_title = QLabel("⚡ SPEED", self.speed_gauge)
        speed_title.setFont(QFont(self.font_main, 12, QFont.Bold))
        speed_title.setStyleSheet("color: #00d2ff;")
        speed_title.setAlignment(Qt.AlignCenter)
        
        self.speed_val_label = QLabel("0", self.speed_gauge)
        self.speed_val_label.setFont(QFont(self.font_mono, 64, QFont.Bold))
        self.speed_val_label.setAlignment(Qt.AlignCenter)
        
        speed_unit = QLabel("km/h", self.speed_gauge)
        speed_unit.setFont(QFont(self.font_main, 12, QFont.Bold))
        speed_unit.setStyleSheet("color: #888888;")
        speed_unit.setAlignment(Qt.AlignCenter)
        
        speed_text_layout.addStretch(1)
        speed_text_layout.addWidget(speed_title)
        speed_text_layout.addWidget(self.speed_val_label)
        speed_text_layout.addWidget(speed_unit)
        speed_text_layout.addStretch(1)
        
        dashboard_layout.addWidget(self.speed_card, 0, 0)

        # 2. ТАХОМЕТР (Круговая шкала)
        self.rpm_card = QFrame(dashboard)
        self.rpm_card.setObjectName("RpmCard")
        rpm_layout = QVBoxLayout(self.rpm_card)
        rpm_layout.setContentsMargins(20, 20, 20, 20)

        self.rpm_gauge = CircularGauge(self.rpm_card, max_value=7000, color="#00fa9a")
        rpm_layout.addWidget(self.rpm_gauge)

        rpm_text_layout = QVBoxLayout(self.rpm_gauge)
        rpm_title = QLabel("🔥 ENGINE RPM", self.rpm_gauge)
        rpm_title.setFont(QFont(self.font_main, 12, QFont.Bold))
        rpm_title.setStyleSheet("color: #00fa9a;")
        rpm_title.setAlignment(Qt.AlignCenter)
        
        self.rpm_val_label = QLabel("0", self.rpm_gauge)
        self.rpm_val_label.setFont(QFont(self.font_mono, 64, QFont.Bold))
        self.rpm_val_label.setAlignment(Qt.AlignCenter)
        
        rpm_unit = QLabel("rpm", self.rpm_gauge)
        rpm_unit.setFont(QFont(self.font_main, 12, QFont.Bold))
        rpm_unit.setStyleSheet("color: #888888;")
        rpm_unit.setAlignment(Qt.AlignCenter)

        rpm_text_layout.addStretch(1)
        rpm_text_layout.addWidget(rpm_title)
        rpm_text_layout.addWidget(self.rpm_val_label)
        rpm_text_layout.addWidget(rpm_unit)
        rpm_text_layout.addStretch(1)

        dashboard_layout.addWidget(self.rpm_card, 0, 1)

        # 3. ТЕМПЕРАТУРА (Индивидуальная линейная шкала)
        self.temp_card = QFrame(dashboard)
        self.temp_card.setObjectName("TempCard")
        temp_layout = QVBoxLayout(self.temp_card)
        temp_layout.setContentsMargins(30, 30, 30, 30)

        temp_header = QHBoxLayout()
        temp_title = QLabel("🌡️ COOLANT", self.temp_card)
        temp_title.setFont(QFont(self.font_main, 14, QFont.Bold))
        temp_title.setStyleSheet("color: #ff5e62;")
        
        self.temp_val_label = QLabel("-- °C", self.temp_card)
        self.temp_val_label.setFont(QFont(self.font_mono, 32, QFont.Bold))
        self.temp_val_label.setStyleSheet("color: #ffffff;")
        self.temp_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        temp_header.addWidget(temp_title)
        temp_header.addWidget(self.temp_val_label)

        self.temp_gauge = LinearGauge(self.temp_card, max_value=120, color="#ff5e62")

        temp_layout.addStretch(1)
        temp_layout.addLayout(temp_header)
        temp_layout.addSpacing(15)
        temp_layout.addWidget(self.temp_gauge)
        temp_layout.addStretch(1)

        dashboard_layout.addWidget(self.temp_card, 1, 0)

        # 4. БАТАРЕЯ (Индивидуальная линейная шкала)
        self.battery_card = QFrame(dashboard)
        self.battery_card.setObjectName("BatteryCard")
        battery_layout = QVBoxLayout(self.battery_card)
        battery_layout.setContentsMargins(30, 30, 30, 30)

        battery_header = QHBoxLayout()
        battery_title = QLabel("🔋 BATTERY", self.battery_card)
        battery_title.setFont(QFont(self.font_main, 14, QFont.Bold))
        battery_title.setStyleSheet("color: #00f2fe;")
        
        self.battery_val_label = QLabel("-- %", self.battery_card)
        self.battery_val_label.setFont(QFont(self.font_mono, 32, QFont.Bold))
        self.battery_val_label.setStyleSheet("color: #ffffff;")
        self.battery_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        battery_header.addWidget(battery_title)
        battery_header.addWidget(self.battery_val_label)

        self.battery_gauge = LinearGauge(self.battery_card, max_value=100, color="#00f2fe")

        battery_layout.addStretch(1)
        battery_layout.addLayout(battery_header)
        battery_layout.addSpacing(15)
        battery_layout.addWidget(self.battery_gauge)
        battery_layout.addStretch(1)

        dashboard_layout.addWidget(self.battery_card, 1, 1)

        # Настройка пропорций строк сетки
        dashboard_layout.setRowStretch(0, 3)
        dashboard_layout.setRowStretch(1, 2)
        dashboard_layout.setColumnStretch(0, 1)
        dashboard_layout.setColumnStretch(1, 1)

        self.add_shadow(self.speed_card)
        self.add_shadow(self.rpm_card)
        self.add_shadow(self.temp_card)
        self.add_shadow(self.battery_card)

        main_layout.addWidget(dashboard, 1)

    def add_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        widget.setGraphicsEffect(shadow)

    def refresh_ports(self):
        self.status_val.setText("Scanning ports...")
        self.status_val.setStyleSheet("color: #ffd700;")
        
        try:
            ports = obd.scan_serial()
            ports = [p for p in ports if "debug-console" not in p and "Bluetooth-Incoming" not in p]
            
            if sys.platform == 'darwin':
                try:
                    my_uid = os.getuid()
                    current_tty = ""
                    try:
                        current_tty = os.ttyname(sys.stdout.fileno())
                    except Exception:
                        pass
                        
                    user_ptys = [f for f in glob.glob('/dev/ttys[0-9]*') if os.stat(f).st_uid == my_uid]
                    for pty in user_ptys:
                        if pty != current_tty and pty not in ports:
                            ports.append(pty)
                except Exception as pty_err:
                    print(f"Ошибка автопоиска PTY на macOS: {pty_err}")
            
            self.port_dropdown.clear()
            self.port_dropdown.addItem("Auto-Detect")
            self.port_dropdown.addItem("Wi-Fi (192.168.0.10:35000)")
            self.port_dropdown.addItems(ports)
            
            if self.demo_checkbox.isChecked():
                self.status_val.setText("DEMO MODE ACTIVE")
                self.status_val.setStyleSheet("color: #ffd700;")
            else:
                self.status_val.setText("Ready to Connect")
                self.status_val.setStyleSheet("color: #a0a0a0;")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_val.setText("Scan Error")
            self.status_val.setStyleSheet("color: #c84b4b;")

    def on_demo_toggle(self, state):
        if state == Qt.Checked:
            self.status_val.setText("DEMO MODE ACTIVE")
            self.status_val.setStyleSheet("color: #ffd700;")
        else:
            self.status_val.setText("Ready to Connect")
            self.status_val.setStyleSheet("color: #a0a0a0;")

    def toggle_connection(self):
        if self.is_running:
            self.is_running = False
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("""
                QPushButton#ConnectButton { background-color: #2b73b5; }
                QPushButton#ConnectButton:hover { background-color: #3b83c5; }
            """)
            self.port_dropdown.setEnabled(True)
            self.baud_dropdown.setEnabled(True)
            self.proto_dropdown.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.demo_checkbox.setEnabled(True)
            self.log_checkbox.setEnabled(True)
            self.error_log_checkbox.setEnabled(True)
            
            self.speed_val_label.setText("0")
            self.rpm_val_label.setText("0")
            self.temp_val_label.setText("-- °C")
            self.battery_val_label.setText("-- %")
            self.speed_gauge.setValue(0)
            self.rpm_gauge.setValue(0)
            self.temp_gauge.setValue(0)
            self.battery_gauge.setValue(0)
            
            if self.demo_checkbox.isChecked():
                self.status_val.setText("DEMO MODE ACTIVE")
                self.status_val.setStyleSheet("color: #ffd700;")
            else:
                self.status_val.setText("Disconnected")
                self.status_val.setStyleSheet("color: #e06666;")
        else:
            self.is_running = True
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("""
                QPushButton#ConnectButton { background-color: #c84b4b; }
                QPushButton#ConnectButton:hover { background-color: #a83b3b; }
            """)
            self.port_dropdown.setEnabled(False)
            self.baud_dropdown.setEnabled(False)
            self.proto_dropdown.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.demo_checkbox.setEnabled(False)
            self.log_checkbox.setEnabled(False)
            self.error_log_checkbox.setEnabled(False)

            if self.log_checkbox.isChecked():
                self.log_filename = f"obd_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                try:
                    with open(self.log_filename, "w") as f:
                        f.write("Timestamp,Speed_kmh,RPM,Coolant_C,Battery_pct\n")
                except Exception as e:
                    print(f"Error creating log file: {e}")
            else:
                self.log_filename = None

            if self.error_log_checkbox.isChecked():
                self.error_log_filename = f"obd_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            else:
                self.error_log_filename = None

            self.status_val.setText("Connecting...")
            self.status_val.setStyleSheet("color: #ffd700;")

            self.polling_thread = threading.Thread(target=self.poll_obd_data, daemon=True)
            self.polling_thread.start()

    def poll_obd_data(self):
        is_demo = self.demo_checkbox.isChecked()

        if is_demo:
            self.run_demo_loop()
        else:
            selected_port = self.port_dropdown.currentText()
            ports_to_try = [self.port_dropdown.itemText(i) for i in range(1, self.port_dropdown.count())] if selected_port == "Auto-Detect" else [selected_port]

            connected = False
            for port in ports_to_try:
                if selected_port == "Auto-Detect" and "Wi-Fi" in port:
                    continue  # Don't try Wi-Fi during serial auto-detect scan
                try:
                    selected_baud = self.baud_dropdown.currentText()
                    baud_param = None if "Auto" in selected_baud else int(selected_baud)
                    
                    selected_proto = self.proto_dropdown.currentText()
                    proto_param = None
                    if "CAN 11-bit 500k" in selected_proto:
                        proto_param = "6"
                    elif "CAN 29-bit 500k" in selected_proto:
                        proto_param = "7"
                    elif "CAN 11-bit 250k" in selected_proto:
                        proto_param = "8"
                    
                    actual_port = "socket://192.168.0.10:35000" if "Wi-Fi" in port else port
                    self.connection = obd.OBD(portstr=actual_port, baudrate=baud_param, protocol=proto_param, fast=False)
                    if self.connection.is_connected():
                        connected = True
                        break
                    else:
                        if self.connection:
                            self.connection.close()
                            self.connection = None
                except Exception as e:
                    if self.connection:
                        self.connection.close()
                        self.connection = None

            if connected:
                try:
                    status_str = f"Connected on {self.connection.port_name()}"
                    cmd_speed = obd.commands.SPEED
                    cmd_rpm = obd.commands.RPM
                    cmd_temp = obd.commands.COOLANT_TEMP
                    cmd_battery = obd.commands.HYBRID_BATTERY_REMAINING
                    cmd_dtc = obd.commands.GET_DTC
                    dtc_counter = 0

                    while self.is_running:
                        speed_res = self.connection.query(cmd_speed, force=True)
                        time.sleep(0.08)
                        rpm_res = self.connection.query(cmd_rpm, force=True)
                        time.sleep(0.08)
                        temp_res = self.connection.query(cmd_temp, force=True)
                        time.sleep(0.08)
                        battery_res = self.connection.query(cmd_battery, force=True)
                        time.sleep(0.08)

                        speed_val = speed_res.value.magnitude if not speed_res.is_null() else 0.0
                        rpm_val = rpm_res.value.magnitude if not rpm_res.is_null() else 0.0
                        temp_val = temp_res.value.magnitude if not temp_res.is_null() else 0.0
                        battery_val = battery_res.value.magnitude if not battery_res.is_null() else 0.0

                        # Print raw debug values and messages to terminal
                        print(f"DEBUG raw:\n"
                              f"  Speed: {speed_res.value} (raw: {speed_res.messages})\n"
                              f"  RPM: {rpm_res.value} (raw: {rpm_res.messages})\n"
                              f"  Temp: {temp_res.value} (raw: {temp_res.messages})\n"
                              f"  Battery: {battery_res.value} (raw: {battery_res.messages})", flush=True)

                        self.signals.update_data.emit(speed_val, rpm_val, temp_val, battery_val, status_str)
                        
                        dtc_counter += 1
                        if dtc_counter >= 50:
                            dtc_counter = 0
                            if getattr(self, 'error_log_filename', None):
                                dtc_res = self.connection.query(cmd_dtc, force=True)
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                try:
                                    with open(self.error_log_filename, "a") as f:
                                        if not dtc_res.is_null() and len(dtc_res.value) > 0:
                                            errors = ", ".join([f"{code[0]} ({code[1]})" for code in dtc_res.value])
                                            f.write(f"[{timestamp}] Errors: {errors}\n")
                                        else:
                                            f.write(f"[{timestamp}] No errors found.\n")
                                except Exception:
                                    pass

                        time.sleep(0.1)
                except Exception as e:
                    self.signals.connection_failed.emit(f"Error: {str(e)}")
                finally:
                    if self.connection:
                        self.connection.close()
                        self.connection = None
            else:
                self.signals.connection_failed.emit("Connection Failed")

    def run_demo_loop(self):
        demo_time = 0.0
        demo_gear = 1
        current_speed = 0.0
        current_rpm = 800.0
        current_temp = 45.0
        current_battery = 85.0
        dtc_counter = 0

        while self.is_running:
            demo_time += 0.08
            cycle = (demo_time // 30) % 2
            
            if current_temp < 90.0:
                current_temp += 0.05
            else:
                current_temp = 90.0 + random.uniform(-0.5, 0.5)

            if cycle == 0:
                current_battery -= 0.012
            else:
                current_battery += 0.006
            
            if current_battery < 20.0: current_battery = 85.0
            elif current_battery > 100.0: current_battery = 100.0

            if cycle == 0:
                gear_max_speeds = {1: 30, 2: 60, 3: 95, 4: 130, 5: 180}
                current_max = gear_max_speeds.get(demo_gear, 180)

                if current_speed >= current_max - 5 and demo_gear < 5:
                    demo_gear += 1
                    current_rpm = 1500
                    self.signals.update_data.emit(current_speed, current_rpm, current_temp, current_battery, "Connected (Simulated)")
                    time.sleep(0.3)
                    continue

                current_speed += (6.0 - demo_gear) * 0.15
                if current_speed > 180: current_speed = 180

                base_rpm = 1000 + (current_speed / current_max) * 4500
                current_rpm = base_rpm + random.uniform(-50, 50)
            else:
                current_speed -= 0.6
                if current_speed < 0:
                    current_speed = 0
                    demo_gear = 1

                if current_speed > 0:
                    gear_min_speeds = {5: 110, 4: 80, 3: 50, 2: 20}
                    for g, min_s in gear_min_speeds.items():
                        if current_speed < min_s and demo_gear == g:
                            demo_gear -= 1
                    current_rpm = 800 + (current_speed * 15) + random.uniform(-20, 20)
                else:
                    current_rpm = 800 + random.uniform(-10, 10)

            self.signals.update_data.emit(current_speed, current_rpm, current_temp, current_battery, "Connected (Simulated)")
            
            dtc_counter += 1
            if dtc_counter >= 50:
                dtc_counter = 0
                if getattr(self, 'error_log_filename', None):
                    try:
                        with open(self.error_log_filename, "a") as f:
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            if random.random() < 0.1:  # 10% chance to simulate an error
                                f.write(f"[{timestamp}] Errors: P0171 (System too lean)\n")
                            else:
                                f.write(f"[{timestamp}] No errors found.\n")
                    except Exception:
                        pass
                        
            time.sleep(0.05)

    def on_data_received(self, speed, rpm, coolant, battery, status):
        if self.log_filename:
            try:
                with open(self.log_filename, "a") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    f.write(f"{timestamp},{speed:.1f},{rpm:.1f},{coolant:.1f},{battery:.1f}\n")
            except Exception:
                pass

        self.speed_val_label.setText(f"{int(speed)}")
        self.speed_gauge.setValue(int(speed))
        
        self.rpm_val_label.setText(f"{int(rpm)}")
        self.rpm_gauge.setValue(int(rpm))

        self.temp_val_label.setText(f"{int(coolant)} °C")
        self.temp_gauge.setValue(int(coolant))

        self.battery_val_label.setText(f"{int(battery)} %")
        self.battery_gauge.setValue(int(battery))

        self.status_val.setText(status)
        self.status_val.setStyleSheet("color: #2ecc71;")

        if rpm > 5500:
            color = "#ff4c4c"
            self.rpm_val_label.setStyleSheet("color: #ff4c4c;")
        elif rpm > 4000:
            color = "#ffb732"
            self.rpm_val_label.setStyleSheet("color: #ffb732;")
        else:
            color = "#00fa9a"
            self.rpm_val_label.setStyleSheet("color: #ffffff;")

        self.rpm_gauge.setColor(color)

    def on_connection_failed(self, error_msg):
        self.status_val.setText(error_msg)
        self.status_val.setStyleSheet("color: #c84b4b;")
        if self.is_running:
            self.toggle_connection()

    def closeEvent(self, event):
        self.is_running = False
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=0.5)
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        event.accept()

    def apply_dark_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: #0b0c10; }}
            
            #Sidebar {{ 
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #12141d, stop:1 #181a24);
                border-right: 1px solid #1f2233; 
            }}
            
            QLabel {{ color: #ffffff; }}
            QLabel#StatusLabel {{ font-size: 11px; padding: 4px; }}
            
            /* Стилизация заголовков в сайдбаре */
            QLabel[text="Select Port:"], QLabel[text="Select Baudrate:"], QLabel[text="Select Protocol:"] {{
                color: #646b8a; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;
            }}
            
            QComboBox {{
                background-color: #1a1d29; color: #a1a7c4;
                border: 1px solid #282c3e; border-radius: 8px; padding: 10px 14px;
            }}
            QComboBox:hover {{ border-color: #404663; background-color: #1f2231; color: #ffffff; }}
            QComboBox::drop-down {{ border: none; width: 30px; }}
            
            QComboBox QAbstractItemView {{
                background-color: #1a1d29; color: #ffffff;
                border: 1px solid #282c3e; border-radius: 8px; selection-background-color: #00d2ff;
            }}
            
            QPushButton {{
                background-color: #202433; color: #ffffff;
                border: 1px solid #2b3044; border-radius: 8px; padding: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #2a2f42; border-color: #404663; }}
            QPushButton:pressed {{ background-color: #1a1d29; }}
            
            #ConnectButton {{ 
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #005cff, stop:1 #00d2ff);
                color: #ffffff; border: none; border-radius: 12px; padding: 14px; font-size: 16px; font-weight: bold;
            }}
            #ConnectButton:hover {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #004ecc, stop:1 #00bfff); }}
            
            QCheckBox {{ color: #8a91b0; font-size: 13px; spacing: 10px; }}
            QCheckBox::indicator {{ 
                width: 20px; height: 20px; border-radius: 6px; 
                border: 1px solid #282c3e; background-color: #1a1d29; 
            }}
            QCheckBox::indicator:hover {{ border-color: #00d2ff; }}
            QCheckBox::indicator:checked {{ background-color: #00d2ff; border-color: #00d2ff; }}
            
            #SpeedCard, #RpmCard, #TempCard, #BatteryCard {{
                background-color: #12141d; border: 1px solid #1f2233; border-radius: 18px;
            }}
            #SpeedCard {{ border-top: 3px solid #00d2ff; }}
            #RpmCard {{ border-top: 3px solid #00fa9a; }}
            #TempCard {{ border-top: 3px solid #ff5e62; }}
            #BatteryCard {{ border-top: 3px solid #00f2fe; }}
            
            QLabel[text="0"], QLabel[text="--"] {{ color: #ffffff; }}
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OBDDashboardQT()
    window.show()
    sys.exit(app.exec_())
