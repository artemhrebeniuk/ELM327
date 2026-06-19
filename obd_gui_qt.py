import sys
import math
import threading
import time
import random
import obd
from obd import OBDCommand, Unit
from obd.protocols import ECU
import os
import glob
import socket
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton, QFrame, QGridLayout, QCheckBox, QSizePolicy, QGraphicsDropShadowEffect)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject, QRectF
from PyQt5.QtGui import QFont, QPainter, QPen, QColor, QBrush

# ============================================================================
#  КАСТОМНЫЕ UDS КОМАНДЫ ДЛЯ ЭЛЕКТРОМОБИЛЕЙ (Audi E-tron и подобные)
#  Стандартные OBD-II PIDs (01 0C, 01 0D, 01 05) НЕ работают на EV,
#  потому что были разработаны для мониторинга выбросов ДВС.
#  Для EV нужно использовать UDS Service 0x22 (Read Data By Identifier)
#  с проприетарными Data Identifiers (DID) производителя.
# ============================================================================

def _decode_ev_soc(messages):
    """Декодер: SOC батареи (%). DID 0x028C → ответ 62 02 8C [byte]
    Формула: byte * 100 / 255 (процент 0-100)"""
    try:
        d = messages[0].data
        if len(d) >= 4:  # 62 02 8C XX
            raw_byte = d[3]
            return raw_byte * 100.0 / 255.0
    except Exception:
        pass
    return None

def _decode_ev_speed(messages):
    """Декодер: Скорость (km/h). DID 0x0281 → ответ 62 02 81 [A] [B]
    Формула: (A*256+B) / 100"""
    try:
        d = messages[0].data
        if len(d) >= 5:  # 62 02 81 AA BB
            return (d[3] * 256 + d[4]) / 100.0
    except Exception:
        pass
    return None

def _decode_ev_hv_voltage(messages):
    """Декодер: Напряжение HV батареи (V). DID 0x0289 → ответ 62 02 89 [A] [B]
    Формула: (A*256+B) / 4"""
    try:
        d = messages[0].data
        if len(d) >= 5:  # 62 02 89 AA BB
            return (d[3] * 256 + d[4]) / 4.0
    except Exception:
        pass
    return None

def _decode_ev_battery_temp(messages):
    """Декодер: Температура батареи (°C). DID 0x028B → ответ 62 02 8B [byte]
    Формула: byte - 40"""
    try:
        d = messages[0].data
        if len(d) >= 4:  # 62 02 8B XX
            return d[3] - 40.0
    except Exception:
        pass
    return None

def _decode_raw_passthrough(messages):
    """Универсальный декодер — возвращает сырые байты ответа для отладки"""
    try:
        d = messages[0].data
        return d
    except Exception:
        return None

# --- Определяем кастомные OBD команды для Audi E-tron ---
# header=b"7E0" адресует основной ЭБУ (Engine/Powertrain ECU)
# Для BMS может потребоваться другой header (7E4, 7E5 и т.д.)

CMD_EV_SOC = OBDCommand(
    "EV_SOC", "EV Battery SOC %",
    b"22028C", 5, _decode_ev_soc, ECU.ALL, False, header=b"7E0"
)

CMD_EV_SPEED = OBDCommand(
    "EV_SPEED", "EV Vehicle Speed km/h",
    b"22F40D", 5, _decode_ev_speed, ECU.ALL, False, header=b"7E0"
)

CMD_EV_HV_VOLTAGE = OBDCommand(
    "EV_HV_VOLTAGE", "EV HV Battery Voltage",
    b"220289", 6, _decode_ev_hv_voltage, ECU.ALL, False, header=b"7E0"
)

CMD_EV_BATTERY_TEMP = OBDCommand(
    "EV_BATTERY_TEMP", "EV Battery Temperature",
    b"22028B", 5, _decode_ev_battery_temp, ECU.ALL, False, header=b"7E0"
)

# Списки команд для пробования с разными headers (7E0, 7E4, 7E5, 7DF) + Приборная панель (714, 720)
# Если один header не работает — пробуем следующий
EV_HEADERS_TO_TRY = [b"7E0", b"7E4", b"7DF", b"7E5", b"714", b"720"]

# Список альтернативных DID для скорости (разные производители используют разные)
SPEED_DIDS_TO_TRY = [
    (b"22F40D", "UDS-mapped standard speed (F40D)"),   # UDS-эквивалент стандартного PID 0x0D
    (b"220281", "Audi proprietary speed (0281)"),       # Проприетарный Audi
    (b"010D",   "Standard OBD-II speed"),               # Стандартный OBD на случай если поддержан
]

SOC_DIDS_TO_TRY = [
    (b"22028C", "Audi BMS SOC (028C)"),
    (b"22F45B", "UDS-mapped hybrid battery (F45B)"),  # UDS-эквивалент стандартного PID 0x5B
    (b"015B",   "Standard OBD-II hybrid battery"),
]

VOLTAGE_DIDS_TO_TRY = [
    (b"220289", "Audi HV Voltage (0289)"),
    (b"224800", "Audi HV Voltage alt (4800)"),
    (b"221E3B", "VAG HV Voltage (1E3B)"),
    (b"2201EB", "VAG HV Voltage alt 2 (01EB)"),
    (b"221D3B", "VAG HV Voltage alt 3 (1D3B)"),
    (b"22742F", "VAG HV Voltage alt 4 (742F)"),
    (b"22029A", "VAG HV Voltage alt 5 (029A)"),
]

TEMP_DIDS_TO_TRY = [
    (b"221EB1", "VAG Battery Temp (1EB1)"),
    (b"22028B", "Audi Battery Temp (028B)"),
    (b"221E3F", "VAG Battery Temp (1E3F)"),
    (b"221E34", "VAG Battery Temp alt 2 (1E34)"),
    (b"22F405", "UDS-mapped coolant temp (F405)"),
    (b"0105",   "Standard OBD-II coolant temp"),
]

RANGE_DIDS_TO_TRY = [
    (b"2202BD", "VAG Range Guess (02BD)"),
    (b"221204", "VAG Range Guess (1204)"),
    (b"222222", "VAG Range Guess (2222)"),
    (b"220222", "VAG Range Guess alt (0222)"),
]

CURRENT_DIDS_TO_TRY = [
    (b"221E3D", "VAG Battery Current (1E3D)"),
    (b"22028A", "Audi Battery Current (028A)"),
    (b"221E3C", "VAG Battery Current alt (1E3C)"),
    (b"2201EC", "VAG Battery Current alt 2 (01EC)"),
]

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
    update_data = pyqtSignal(float, float, float, float, float, str)  # speed, hv_voltage, temp, battery_soc, current, status
    connection_failed = pyqtSignal(str)                       # error message
    log_message = pyqtSignal(str)                             # console log from background thread

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

        # Vehicle Profile Selection
        profile_label = QLabel("Vehicle Profile:", sidebar)
        profile_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        profile_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(profile_label)

        self.vehicle_profile_dropdown = QComboBox(sidebar)
        self.vehicle_profile_dropdown.addItems(["Audi E-tron / VAG EV", "Mercedes Sprinter / Standard ICE"])
        self.vehicle_profile_dropdown.setFont(QFont(self.font_main, 12))
        self.vehicle_profile_dropdown.currentIndexChanged.connect(self.on_vehicle_profile_changed)
        sidebar_layout.addWidget(self.vehicle_profile_dropdown)

        conn_type_label = QLabel("Connection Type:", sidebar)
        conn_type_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        conn_type_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(conn_type_label)

        self.conn_type_dropdown = QComboBox(sidebar)
        self.conn_type_dropdown.addItems(["Wi-Fi", "Bluetooth (Serial)"])
        self.conn_type_dropdown.setFont(QFont(self.font_main, 12))
        self.conn_type_dropdown.currentIndexChanged.connect(self.on_connection_type_changed)
        sidebar_layout.addWidget(self.conn_type_dropdown)

        self.port_label = QLabel("Select Port:", sidebar)
        self.port_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        self.port_label.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(self.port_label)

        self.wifi_input = QLineEdit("192.168.0.10:35000", sidebar)
        self.wifi_input.setFont(QFont(self.font_main, 12))
        sidebar_layout.addWidget(self.wifi_input)

        self.port_dropdown = QComboBox(sidebar)
        self.port_dropdown.addItem("Auto-Detect")
        self.port_dropdown.setFont(QFont(self.font_main, 12))
        self.port_dropdown.hide()
        sidebar_layout.addWidget(self.port_dropdown)

        self.baud_label = QLabel("Select Baudrate:", sidebar)
        self.baud_label.setFont(QFont(self.font_main, 10, QFont.Bold))
        self.baud_label.setStyleSheet("color: #888888;")
        self.baud_label.hide()
        sidebar_layout.addWidget(self.baud_label)

        self.baud_dropdown = QComboBox(sidebar)
        self.baud_dropdown.addItems(["Auto (Scan)", "38400", "9600", "115200", "230400"])
        self.baud_dropdown.setFont(QFont(self.font_main, 12))
        self.baud_dropdown.hide()
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
        self.refresh_btn.hide()
        sidebar_layout.addWidget(self.refresh_btn)

        self.demo_checkbox = QCheckBox("Demo Simulator", sidebar)
        self.demo_checkbox.setFont(QFont(self.font_main, 12))
        self.demo_checkbox.setChecked(False)
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

        self.status_val = QLabel("Ready to Connect", sidebar)
        self.status_val.setObjectName("StatusLabel")
        self.status_val.setFont(QFont(self.font_main, 11, QFont.Bold))
        self.status_val.setStyleSheet("color: #a0a0a0;")
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

        # 2. НАПРЯЖЕНИЕ HV БАТАРЕИ (Круговая шкала) — вместо RPM (на электричке нет ДВС)
        self.rpm_card = QFrame(dashboard)
        self.rpm_card.setObjectName("RpmCard")
        rpm_layout = QVBoxLayout(self.rpm_card)
        rpm_layout.setContentsMargins(20, 20, 20, 20)

        self.rpm_gauge = CircularGauge(self.rpm_card, max_value=300, color="#ffaa00")
        rpm_layout.addWidget(self.rpm_gauge)

        rpm_text_layout = QVBoxLayout(self.rpm_gauge)
        self.rpm_title = QLabel("⚡ BATTERY POWER", self.rpm_gauge)
        self.rpm_title.setFont(QFont(self.font_main, 12, QFont.Bold))
        self.rpm_title.setStyleSheet("color: #ffaa00;")
        self.rpm_title.setAlignment(Qt.AlignCenter)
        
        self.rpm_val_label = QLabel("0", self.rpm_gauge)
        self.rpm_val_label.setFont(QFont(self.font_mono, 64, QFont.Bold))
        self.rpm_val_label.setAlignment(Qt.AlignCenter)
        
        self.rpm_unit = QLabel("kW", self.rpm_gauge)
        self.rpm_unit.setFont(QFont(self.font_main, 12, QFont.Bold))
        self.rpm_unit.setStyleSheet("color: #888888;")
        self.rpm_unit.setAlignment(Qt.AlignCenter)

        rpm_text_layout.addStretch(1)
        rpm_text_layout.addWidget(self.rpm_title)
        rpm_text_layout.addWidget(self.rpm_val_label)
        rpm_text_layout.addWidget(self.rpm_unit)
        rpm_text_layout.addStretch(1)

        dashboard_layout.addWidget(self.rpm_card, 0, 1)

        # 3. ТЕМПЕРАТУРА (Индивидуальная линейная шкала)
        self.temp_card = QFrame(dashboard)
        self.temp_card.setObjectName("TempCard")
        temp_layout = QVBoxLayout(self.temp_card)
        temp_layout.setContentsMargins(30, 30, 30, 30)

        temp_header = QHBoxLayout()
        self.temp_title = QLabel("🔋 BATTERY TEMP", self.temp_card)
        self.temp_title.setFont(QFont(self.font_main, 14, QFont.Bold))
        self.temp_title.setStyleSheet("color: #ff5e62;")
        
        self.temp_val_label = QLabel("-- °C", self.temp_card)
        self.temp_val_label.setFont(QFont(self.font_mono, 32, QFont.Bold))
        self.temp_val_label.setStyleSheet("color: #ffffff;")
        self.temp_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        temp_header.addWidget(self.temp_title)
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
        self.battery_title = QLabel("🔋 BATTERY", self.battery_card)
        self.battery_title.setFont(QFont(self.font_main, 14, QFont.Bold))
        self.battery_title.setStyleSheet("color: #00f2fe;")
        
        self.battery_val_label = QLabel("-- %", self.battery_card)
        self.battery_val_label.setFont(QFont(self.font_mono, 32, QFont.Bold))
        self.battery_val_label.setStyleSheet("color: #ffffff;")
        self.battery_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        battery_header.addWidget(self.battery_title)
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

    def on_vehicle_profile_changed(self, index):
        is_ev = (index == 0)
        if is_ev:
            self.rpm_title.setText("⚡ BATTERY POWER")
            self.rpm_title.setStyleSheet("color: #ffaa00;")
            self.rpm_unit.setText("kW")
            self.rpm_gauge.max_value = 300
            self.temp_title.setText("🔋 BATTERY TEMP")
            self.temp_title.setStyleSheet("color: #ff5e62;")
            self.battery_title.setText("🔋 BATTERY")
            self.battery_title.setStyleSheet("color: #00f2fe;")
            self.battery_gauge.max_value = 100
            
            # Reset gauges
            self.speed_gauge.setValue(0)
            self.rpm_gauge.setValue(0)
            self.temp_gauge.setValue(0)
            self.battery_gauge.setValue(0)
            self.rpm_gauge.setColor("#ffaa00")
        else:
            self.rpm_title.setText("⚡ ENGINE RPM")
            self.rpm_title.setStyleSheet("color: #00fa9a;")
            self.rpm_unit.setText("rpm")
            self.rpm_gauge.max_value = 5000
            self.temp_title.setText("🌡️ COOLANT TEMP")
            self.temp_title.setStyleSheet("color: #ff5e62;")
            self.battery_title.setText("🔌 SYSTEM VOLTAGE")
            self.battery_title.setStyleSheet("color: #00f2fe;")
            self.battery_gauge.max_value = 18
            
            # Reset gauges
            self.speed_gauge.setValue(0)
            self.rpm_gauge.setValue(0)
            self.temp_gauge.setValue(0)
            self.battery_gauge.setValue(0)
            self.rpm_gauge.setColor("#00fa9a")

    def add_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(15)
        shadow.setColor(QColor(0, 0, 0, 180))
        widget.setGraphicsEffect(shadow)

    def on_connection_type_changed(self, index):
        is_wifi = (index == 0)
        if is_wifi:
            self.wifi_input.show()
            self.port_dropdown.hide()
            self.refresh_btn.hide()
            self.baud_dropdown.hide()
            self.baud_label.hide()
        else:
            self.wifi_input.hide()
            self.port_dropdown.show()
            self.refresh_btn.show()
            self.baud_dropdown.show()
            self.baud_label.show()
            self.refresh_ports()

    def refresh_ports(self):
        if self.conn_type_dropdown.currentIndex() == 0:
            return

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
            self.conn_type_dropdown.setEnabled(True)
            self.vehicle_profile_dropdown.setEnabled(True)
            self.wifi_input.setEnabled(True)
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
            self.conn_type_dropdown.setEnabled(False)
            self.vehicle_profile_dropdown.setEnabled(False)
            self.wifi_input.setEnabled(False)
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
                        f.write("Timestamp,Speed_kmh,HV_Voltage_V,Battery_Temp_C,SOC_pct\n")
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

    def _log(self, msg):
        """Выводит сообщение в консоль и пытается отправить в UI"""
        print(msg, flush=True)

    def _try_query_did(self, did_bytes, header, description):
        """Пробует отправить одну UDS команду с указанным header.
        Возвращает (raw_data, hex_string) если ответ получен, иначе (None, hex_string).
        """
        try:
            probe_cmd = OBDCommand(
                f"PROBE_{did_bytes.decode()}", description,
                did_bytes, 8, _decode_raw_passthrough, ECU.ALL, False, header=header
            )
            res = self.connection.query(probe_cmd, force=True)
            
            if not res.is_null() and res.value is not None:
                hex_str = " ".join(f"{b:02X}" for b in res.value)
                return res.value, hex_str
            else:
                raw_msgs = res.messages if hasattr(res, 'messages') else []
                hex_str = ""
                if raw_msgs:
                    for m in raw_msgs:
                        if hasattr(m, 'data') and m.data:
                            hex_str = " ".join(f"{b:02X}" for b in m.data)
                return None, hex_str
        except Exception as e:
            return None, f"ERROR: {e}"

    def _scan_working_commands(self):
        """Фаза сканирования: пробуем разные DID + headers, чтобы найти рабочие.
        Возвращает dict с найденными рабочими командами."""
        self._log("\n" + "=" * 70)
        self._log("  🔍 ДИАГНОСТИЧЕСКОЕ СКАНИРОВАНИЕ ПОДДЕРЖИВАЕМЫХ КОМАНД")
        self._log("  Audi E-tron — электромобиль, стандартные OBD PIDs не работают.")
        self._log("  Пробуем UDS Service 0x22 (Read Data By Identifier)...")
        self._log("=" * 70)

        found = {}
        
        # Пробуем разные DID для каждого параметра
        for param_name, did_list in [
            ("speed", SPEED_DIDS_TO_TRY),
            ("soc", SOC_DIDS_TO_TRY),
            ("voltage", VOLTAGE_DIDS_TO_TRY),
            ("temp", TEMP_DIDS_TO_TRY),
            ("range", RANGE_DIDS_TO_TRY),
            ("current", CURRENT_DIDS_TO_TRY),
        ]:
            self._log(f"\n--- Сканируем: {param_name.upper()} ---")
            found_this_param = False
            
            for did_bytes, desc in did_list:
                if found_this_param:
                    break
                    
                # Для стандартных OBD команд (01xx) не нужен кастомный header
                if did_bytes.startswith(b"01"):
                    headers_for_this = [None]  # None = не менять header
                else:
                    headers_for_this = EV_HEADERS_TO_TRY
                
                for header in headers_for_this:
                    if not self.is_running:
                        return found
                        
                    header_str = header.decode() if header else "default"
                    self._log(f"  ▶ Пробуем {desc} (header={header_str})...")
                    
                    data, hex_str = self._try_query_did(did_bytes, header, desc)
                    time.sleep(0.15)  # Пауза между запросами
                    
                    if data is not None and len(data) > 0:
                        is_uds = did_bytes.startswith(b"22")
                        is_std = did_bytes.startswith(b"01")
                        
                        is_valid = False
                        if is_uds and data[0] == 0x62:
                            is_valid = True
                        elif is_std and data[0] == 0x41:
                            is_valid = True
                            
                        if is_valid:
                            self._log(f"  ✅ ОТВЕТ ПОЛУЧЕН: [{hex_str}]")
                            found[param_name] = {
                                "did": did_bytes,
                                "header": header,
                                "desc": desc,
                                "last_raw": hex_str,
                            }
                            found_this_param = True
                            break
                        else:
                            if data[0] == 0x7F:
                                self._log(f"  ❌ Отказ ЭБУ (NRC): [{hex_str}]")
                            else:
                                self._log(f"  ❌ Мусор/нули от адаптера: [{hex_str}]")
                    else:
                        self._log(f"  ❌ Нет ответа (raw: [{hex_str}])")
        
        self._log("\n" + "=" * 70)
        self._log("  📊 РЕЗУЛЬТАТЫ СКАНИРОВАНИЯ:")
        if found:
            for param, info in found.items():
                h = info['header'].decode() if info['header'] else 'default'
                self._log(f"  ✅ {param.upper()}: {info['desc']} (header={h})")
        else:
            self._log("  ⚠️  НИ ОДНА КОМАНДА НЕ ВЕРНУЛА ДАННЫХ.")
            self._log("  Возможные причины:")
            self._log("    1. Security Gateway блокирует доступ через дешёвый ELM327")
            self._log("    2. Нужен другой CAN header для вашей модели E-tron")
            self._log("    3. Адаптер не поддерживает UDS Service 0x22")
        self._log("=" * 70 + "\n")
        
        return found

    def _decode_response(self, param_name, data):
        """Декодирует сырые данные ответа в числовое значение."""
        if data is None or len(data) < 3:
            return 0.0
        
        try:
            # UDS ответ: 62 [DID_H] [DID_L] [data...]
            if data[0] == 0x62:
                payload = data[3:]  # Данные после 62 DID_H DID_L
                if param_name == "soc":
                    if len(payload) >= 1:
                        # 0x57 = 87 = 87%
                        val = float(payload[0])
                        if val <= 100.0:
                            return val
                        else:
                            return val * 100.0 / 255.0
                elif param_name == "speed":
                    if len(payload) >= 2:
                        raw = payload[0] * 256 + payload[1]
                        val = raw / 100.0
                        if val > 300:  # Если значение абсурдно большое — пробуем другую формулу
                            val = payload[0]  # Может быть просто один байт = km/h
                        return float(val)
                    elif len(payload) >= 1:
                        return float(payload[0])  # Один байт = прямое значение km/h
                elif param_name == "voltage":
                    if len(payload) >= 2:
                        raw = payload[0] * 256 + payload[1]
                        # Для VAG HV Voltage (DID 1E3B) делитель = 10.0
                        if data[1] == 0x1E and data[2] == 0x3B:
                            return raw / 10.0
                        return raw / 4.0
                elif param_name == "temp":
                    # VAG Battery Temp (1EB1): Сырой байт 0x7C (124) -> 24 °C. Формула A - 100.
                    if data[1] == 0x1E and data[2] == 0xB1 and len(payload) >= 1:
                        return payload[0] - 100.0
                        
                    if len(payload) >= 1:
                        if payload[0] == 0xFF or payload[0] == 0x00:
                            return 0.0 # FF или 00 = dummy/not supported
                        return payload[0] - 40.0
                elif param_name == "range":
                    if len(payload) >= 2:
                        raw = payload[0] * 256 + payload[1]
                        return float(raw)
                    elif len(payload) >= 1:
                        return float(payload[0])
                elif param_name == "current":
                    if len(payload) >= 3:
                        raw = payload[0] * 65536 + payload[1] * 256 + payload[2]
                        return float(raw)
                    elif len(payload) >= 2:
                        raw = payload[0] * 256 + payload[1]
                        return float(raw)
            
            # Стандартный OBD ответ: 41 [PID] [data...]
            elif data[0] == 0x41:
                pid = data[1]
                payload = data[2:]
                if pid == 0x0D and len(payload) >= 1:  # Speed
                    return float(payload[0])
                elif pid == 0x0C and len(payload) >= 2:  # RPM
                    return (payload[0] * 256 + payload[1]) / 4.0
                elif pid == 0x05 and len(payload) >= 1:  # Coolant temp
                    return payload[0] - 40.0
                elif pid == 0x5B and len(payload) >= 1:  # Hybrid battery
                    return payload[0] * 100.0 / 255.0
        except Exception as e:
            self._log(f"  ⚠️ Ошибка декодирования {param_name}: {e}")
        
        return 0.0

    def poll_obd_data(self):
        is_demo = self.demo_checkbox.isChecked()

        if is_demo:
            self.run_demo_loop()
        else:
            is_wifi = (self.conn_type_dropdown.currentIndex() == 0)
            
            if is_wifi:
                wifi_addr = self.wifi_input.text().strip()
                if wifi_addr and not wifi_addr.startswith("socket://"):
                    actual_port = f"socket://{wifi_addr}"
                else:
                    actual_port = wifi_addr
                ports_to_try = [actual_port]
            else:
                selected_port = self.port_dropdown.currentText()
                if selected_port == "Auto-Detect":
                    ports_to_try = [self.port_dropdown.itemText(i) for i in range(1, self.port_dropdown.count())]
                else:
                    ports_to_try = [selected_port]

            if not ports_to_try:
                self._log("❌ Нет доступных COM-портов для подключения.")
                self.signals.connection_failed.emit("No COM ports found")
                return

            connected = False
            for port in ports_to_try:
                if not self.is_running:
                    return
                
                selected_proto = self.proto_dropdown.currentText()
                if "Auto" in selected_proto:
                    # Попробуем автодетекцию, а если не выйдет - переберем популярные CAN-протоколы вручную
                    protocols_to_try = [None, "6", "7", "8", "9", "3", "4", "5"]
                elif "CAN 11-bit 500k" in selected_proto:
                    protocols_to_try = ["6"]
                elif "CAN 29-bit 500k" in selected_proto:
                    protocols_to_try = ["7"]
                elif "CAN 11-bit 250k" in selected_proto:
                    protocols_to_try = ["8"]
                else:
                    protocols_to_try = [None]

                for proto_param in protocols_to_try:
                    if not self.is_running:
                        return
                    try:
                        if is_wifi:
                            baud_param = 38400
                        else:
                            selected_baud = self.baud_dropdown.currentText()
                            baud_param = None if "Auto" in selected_baud else int(selected_baud)
                        
                        proto_name_debug = f"Protocol: {proto_param}" if proto_param else "Protocol: Auto-Detect"
                        self._log(f"🔌 Подключаемся к {port} ({proto_name_debug})...")
                        self.connection = obd.OBD(portstr=port, baudrate=baud_param, protocol=proto_param, fast=False)
                        
                        if self.connection.is_connected():
                            self._log(f"✅ Подключение успешно: {port}")
                            if hasattr(self.connection, 'protocol_name'):
                                self._log(f"   Протокол: {self.connection.protocol_name()}")
                            connected = True
                            break
                        else:
                            self._log(f"❌ Не удалось подключиться к {port} с протоколом {proto_param}")
                            if self.connection:
                                try:
                                    self.connection.close()
                                except Exception:
                                    pass
                                self.connection = None
                            time.sleep(0.8) # Даем адаптеру остыть/сбросить сокет
                    except Exception as e:
                        self._log(f"❌ Ошибка подключения к {port} ({proto_param}): {e}")
                        if self.connection:
                            try:
                                self.connection.close()
                            except Exception:
                                pass
                            self.connection = None
                        time.sleep(0.8) # Даем адаптеру остыть/сбросить сокет
                
                if connected:
                    break

            if connected:
                try:
                    status_str = f"Connected on {self.connection.port_name()}"
                    
                    is_ev = (self.vehicle_profile_dropdown.currentIndex() == 0)
                    
                    if is_ev:
                        # ============ ФАЗА 1: СКАНИРОВАНИЕ (UDS EV) ============
                        self.signals.update_data.emit(0, 0, 0, 0, 150000.0, "Scanning EV commands...")
                        working_cmds = self._scan_working_commands()
                        
                        if not self.is_running:
                            return
                        
                        active_commands = {}
                        decoders = {
                            "speed": _decode_raw_passthrough,
                            "soc": _decode_raw_passthrough,
                            "voltage": _decode_raw_passthrough,
                            "temp": _decode_raw_passthrough,
                            "range": _decode_raw_passthrough,
                            "current": _decode_raw_passthrough,
                        }
                        for param_name, info in working_cmds.items():
                            cmd = OBDCommand(
                                f"EV_{param_name.upper()}", info['desc'],
                                info['did'], 8, decoders[param_name], ECU.ALL, False,
                                header=info['header']
                            )
                            active_commands[param_name] = cmd
                        
                        has_any_data = len(active_commands) > 0
                        
                        if not has_any_data:
                            self._log("\n⚠️  Переходим в режим стандартных OBD-II PIDs (fallback)...")
                            status_str = "Connected (no EV data — standard OBD)"
                        else:
                            found_names = ", ".join(active_commands.keys())
                            status_str = f"EV Mode: {found_names}"
                            self._log(f"\n🚀 Начинаем опрос: {found_names}")
                    else:
                        has_any_data = False
                        status_str = "Connected (Standard ICE)"
                        self._log(f"\n🚀 Начинаем опрос (Standard OBD-II): RPM, Speed, Temp, Fuel")
                    
                    # ============ ФАЗА 2: ЦИКЛИЧЕСКИЙ ОПРОС ============
                    poll_count = 0
                    dtc_counter = 0
                    
                    while self.is_running:
                        speed_val = 0.0
                        voltage_val = 0.0
                        temp_val = 0.0
                        soc_val = 0.0
                        range_val = 0.0
                        current_val = 150000.0
                        
                        if has_any_data:
                            # Опрос через кастомные UDS команды
                            for param_name, cmd in active_commands.items():
                                if not self.is_running:
                                    break
                                    
                                res = self.connection.query(cmd, force=True)
                                time.sleep(0.01)
                                
                                if not res.is_null() and res.value is not None:
                                    val = self._decode_response(param_name, res.value)
                                    hex_str = " ".join(f"{b:02X}" for b in res.value) if res.value else "empty"
                                    
                                    if param_name == "speed":
                                        speed_val = val
                                    elif param_name == "soc":
                                        soc_val = val
                                    elif param_name == "voltage":
                                        voltage_val = val
                                    elif param_name == "temp":
                                        temp_val = val
                                    elif param_name == "range":
                                        range_val = val
                                    elif param_name == "current":
                                        current_val = val
                                    
                                    # Подробный debug каждые 10 циклов
                                    if poll_count % 10 == 0:
                                        self._log(f"  {param_name}: {val:.1f} (raw: [{hex_str}])")
                                else:
                                    if poll_count % 10 == 0:
                                        self._log(f"  {param_name}: NO DATA")
                                        
                        else:
                            # Стандартный OBD-II (ДВС или Fallback)
                            speed_res = self.connection.query(obd.commands.SPEED, force=True)
                            time.sleep(0.01)
                            
                            # Для ДВС пишем RPM во второй прибор
                            if not is_ev:
                                rpm_res = self.connection.query(obd.commands.RPM, force=True)
                                voltage_val = rpm_res.value.magnitude if not rpm_res.is_null() and rpm_res.value is not None else 0.0
                            else:
                                voltage_res = self.connection.query(obd.commands.CONTROL_MODULE_VOLTAGE, force=True)
                                voltage_val = voltage_res.value.magnitude if not voltage_res.is_null() and voltage_res.value is not None else 0.0
                            time.sleep(0.01)
                            
                            temp_res = self.connection.query(obd.commands.COOLANT_TEMP, force=True)
                            time.sleep(0.01)
                            
                            # Для ДВС пишем Напряжение бортовой сети в четвертый прибор
                            if not is_ev:
                                volt_res = self.connection.query(obd.commands.CONTROL_MODULE_VOLTAGE, force=True)
                                soc_val = volt_res.value.magnitude if not volt_res.is_null() and volt_res.value is not None else 0.0
                            else:
                                soc_res = self.connection.query(obd.commands.HYBRID_BATTERY_REMAINING, force=True)
                                soc_val = soc_res.value.magnitude if not soc_res.is_null() and soc_res.value is not None else 0.0
                            time.sleep(0.01)
                            
                            speed_val = speed_res.value.magnitude if not speed_res.is_null() and speed_res.value is not None else 0.0
                            temp_val = temp_res.value.magnitude if not temp_res.is_null() and temp_res.value is not None else 0.0
                            current_val = 150000.0
                            
                            if poll_count % 10 == 0:
                                self._log(f"DEBUG (standard OBD):\n"
                                          f"  Speed: {speed_val:.1f} | RPM/Volt: {voltage_val:.1f}\n"
                                          f"  Temp: {temp_val:.1f} | Fuel/SOC: {soc_val:.1f}")

                        self.signals.update_data.emit(speed_val, voltage_val, temp_val, soc_val, current_val, status_str)
                        
                        # DTC scan
                        dtc_counter += 1
                        if dtc_counter >= 50:
                            dtc_counter = 0
                            if getattr(self, 'error_log_filename', None):
                                try:
                                    dtc_res = self.connection.query(obd.commands.GET_DTC, force=True)
                                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    with open(self.error_log_filename, "a") as f:
                                        if not dtc_res.is_null() and len(dtc_res.value) > 0:
                                            errors = ", ".join([f"{code[0]} ({code[1]})" for code in dtc_res.value])
                                            f.write(f"[{timestamp}] Errors: {errors}\n")
                                        else:
                                            f.write(f"[{timestamp}] No errors found.\n")
                                except Exception:
                                    pass

                        poll_count += 1
                        time.sleep(0.15)
                        
                except Exception as e:
                    import traceback
                    self._log(f"\n❌ ОШИБКА: {e}")
                    traceback.print_exc()
                    self.signals.connection_failed.emit(f"Error: {str(e)}")
                finally:
                    if self.connection:
                        try:
                            self.connection.close()
                        except Exception:
                            pass
                        self.connection = None
            else:
                self.signals.connection_failed.emit("Connection Failed — check adapter")

    def run_demo_loop(self):
        """Демо-режим: симулирует электромобиль (скорость, HV напряжение, температура батареи, SOC)"""
        is_ev = (self.vehicle_profile_dropdown.currentIndex() == 0)
        demo_time = 0.0
        current_speed = 0.0
        current_voltage = 396.0 if is_ev else 800.0   # Для EV вольтаж, для ДВС обороты RPM (холостые 800)
        current_temp = 22.0
        current_soc = 85.0
        dtc_counter = 0

        while self.is_running:
            demo_time += 0.08
            cycle = (demo_time // 30) % 2
            
            # Температура батареи/ДВС медленно растёт при движении
            if current_speed > 0:
                current_temp += 0.02 if is_ev else 0.05
            if current_temp > (45.0 if is_ev else 90.0):
                current_temp = (45.0 if is_ev else 90.0) + random.uniform(-0.3, 0.3)
            elif current_temp < 18.0:
                current_temp = 18.0

            # Заряд / Топливо
            if cycle == 0:
                current_soc -= 0.015 if is_ev else 0.01  # Расход заряда или бензина
            else:
                current_soc += 0.005 if is_ev else 0.0   # Рекуперация (у ДВС нет)
            
            if current_soc < 15.0: current_soc = 85.0
            elif current_soc > 100.0: current_soc = 100.0

            if cycle == 0:
                # Разгон
                if current_speed < 130:
                    current_speed += random.uniform(0.3, 0.8)
                else:
                    current_speed = 130 + random.uniform(-2, 2)
                
                if is_ev:
                    current_voltage = 396.0 - (current_speed / 130.0) * 20.0 + random.uniform(-2, 2)
                    sim_current_amps = - (current_speed / 130.0) * 150.0 - random.uniform(0, 5)
                else:
                    # ДВС: Симулируем переключения передач
                    spd = current_speed
                    if spd < 30:
                        rpm = 800 + (spd / 30.0) * 2200
                    elif spd < 60:
                        rpm = 1500 + ((spd - 30) / 30.0) * 2000
                    elif spd < 90:
                        rpm = 1800 + ((spd - 60) / 30.0) * 1800
                    else:
                        rpm = 2000 + ((spd - 90) / 40.0) * 1500
                    current_voltage = rpm + random.uniform(-20, 20)
                    sim_current_amps = 0.0
            else:
                # Торможение
                current_speed -= 0.5
                if current_speed < 0:
                    current_speed = 0

                if is_ev:
                    if current_speed > 0:
                        current_voltage = 400.0 + (1.0 - current_speed / 130.0) * 10.0 + random.uniform(-1, 1)
                        sim_current_amps = (current_speed / 130.0) * 80.0 + random.uniform(0, 3)
                    else:
                        current_voltage = 408.0 + random.uniform(-1, 1)
                        sim_current_amps = -1.0 + random.uniform(-0.1, 0.1)
                else:
                    # ДВС: Обороты падают
                    if current_speed > 0:
                        rpm = 1200 + (current_speed / 130.0) * 800
                    else:
                        rpm = 800
                    current_voltage = rpm + random.uniform(-10, 10)
                    sim_current_amps = 0.0

            if is_ev:
                # Конвертируем Амперы обратно в сырое значение (offset = 150000)
                sim_current_raw = 150000.0 + sim_current_amps * 100.0
                self.signals.update_data.emit(current_speed, current_voltage, current_temp, current_soc, sim_current_raw, "Connected (EV Simulator)")
            else:
                sim_system_voltage = 14.1 + random.uniform(-0.1, 0.1)
                # For ICE: speed, rpm (stored in current_voltage), coolant_temp (stored in current_temp), system_voltage, raw_current=0.0
                self.signals.update_data.emit(current_speed, current_voltage, current_temp, sim_system_voltage, 150000.0, "Connected (ICE Simulator)")
            
            dtc_counter += 1
            if dtc_counter >= 50:
                dtc_counter = 0
                if getattr(self, 'error_log_filename', None):
                    try:
                        with open(self.error_log_filename, "a") as f:
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            f.write(f"[{timestamp}] No errors found.\n")
                    except Exception:
                        pass
                        
            time.sleep(0.05)

    def on_data_received(self, speed, val2, temp, val4, current, status):
        is_ev = (self.vehicle_profile_dropdown.currentIndex() == 0)

        if self.log_filename:
            try:
                with open(self.log_filename, "a") as f:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    f.write(f"{timestamp},{speed:.1f},{val2:.1f},{temp:.1f},{val4:.1f}\n")
            except Exception:
                pass

        self.speed_val_label.setText(f"{int(speed)}")
        self.speed_gauge.setValue(int(speed))

        self.temp_val_label.setText(f"{int(temp)} °C")
        self.temp_gauge.setValue(int(temp))

        if is_ev:
            # EV Profile: val2 is hv_voltage, current is raw current, val4 is SOC
            if current > 0:
                actual_current_amps = (current - 150000.0) / 100.0
            else:
                actual_current_amps = 0.0

            power_kw = - (val2 * actual_current_amps) / 1000.0

            self.rpm_val_label.setText(f"{power_kw:.1f}")
            self.rpm_gauge.setValue(abs(int(power_kw)))

            self.battery_val_label.setText(f"{int(val4)} %")
            self.battery_gauge.setValue(int(val4))

            # Color coding for EV power
            if power_kw < -1.0:
                color = "#00d2ff" # Рекуперация (голубой)
                self.rpm_val_label.setStyleSheet("color: #00d2ff;")
            elif power_kw > 10.0:
                color = "#ff5e62" # Активный разгон (красно-оранжевый)
                self.rpm_val_label.setStyleSheet("color: #ff5e62;")
            elif power_kw > 1.0:
                color = "#ffb732" # Слабый разгон (оранжевый)
                self.rpm_val_label.setStyleSheet("color: #ffb732;")
            else:
                color = "#00fa9a" # Покой (зеленый)
                self.rpm_val_label.setStyleSheet("color: #ffffff;")
            self.rpm_gauge.setColor(color)
        else:
            # ICE Profile: val2 is Engine RPM, val4 is System Voltage (V)
            self.rpm_val_label.setText(f"{int(val2)}")
            self.rpm_gauge.setValue(int(val2))

            self.battery_val_label.setText(f"{val4:.2f} V")
            self.battery_gauge.setValue(int(val4))

            # Color coding for ICE engine RPM
            if val2 > 4500:
                color = "#ff4c4c" # Красная зона
                self.rpm_val_label.setStyleSheet("color: #ff4c4c;")
            elif val2 > 3000:
                color = "#ffb732" # Повышенные обороты
                self.rpm_val_label.setStyleSheet("color: #ffb732;")
            else:
                color = "#00fa9a" # Обычные обороты
                self.rpm_val_label.setStyleSheet("color: #ffffff;")
            self.rpm_gauge.setColor(color)

        self.status_val.setText(status)
        self.status_val.setStyleSheet("color: #2ecc71;")

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
            QLabel[text="Select Port:"], QLabel[text="Select Baudrate:"], QLabel[text="Select Protocol:"], QLabel[text="Connection Type:"], QLabel[text="Vehicle Profile:"] {{
                color: #646b8a; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;
            }}
            
            QComboBox, QLineEdit {{
                background-color: #1a1d29; color: #a1a7c4;
                border: 1px solid #282c3e; border-radius: 8px; padding: 10px 14px;
            }}
            QComboBox:hover, QLineEdit:hover, QLineEdit:focus {{ border-color: #404663; background-color: #1f2231; color: #ffffff; }}
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
