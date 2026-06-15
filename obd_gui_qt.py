import sys
import threading
import time
import random
import obd
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QComboBox, QPushButton, QProgressBar, QFrame, QGridLayout, QCheckBox)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont

# Объект для безопасной передачи данных из фонового потока в GUI поток
class OBDSignals(QObject):
    update_data = pyqtSignal(float, float, str)  # speed, rpm, status
    connection_failed = pyqtSignal(str)          # error message

class OBDDashboardQT(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OBD-II Smart Dashboard (Qt)")
        self.setGeometry(100, 100, 800, 480)
        self.setMinimumSize(750, 430)

        # Состояние подключения
        self.connection = None
        self.polling_thread = None
        self.is_running = False

        # Сигналы для потоков
        self.signals = OBDSignals()
        self.signals.update_data.connect(self.on_data_received)
        self.signals.connection_failed.connect(self.on_connection_failed)

        # Инициализация интерфейса
        self.init_ui()
        self.apply_dark_theme()

        # Сканируем порты при старте
        QTimer.singleShot(200, self.refresh_ports)

    def init_ui(self):
        # Центральный виджет и главный Layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- ЛЕВАЯ ПАНЕЛЬ (Панель управления) ---
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 20, 20, 20)
        sidebar_layout.setSpacing(15)

        # Логотип
        logo = QLabel("⚡ OBD-II ELM327", sidebar)
        logo.setFont(QFont("Arial", 16, QFont.Bold))
        logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo)

        # Выбор портов
        port_label = QLabel("Select Port:", sidebar)
        port_label.setFont(QFont("Arial", 10))
        sidebar_layout.addWidget(port_label)

        self.port_dropdown = QComboBox(sidebar)
        self.port_dropdown.addItem("Auto-Detect")
        sidebar_layout.addWidget(self.port_dropdown)

        # Кнопка обновления
        self.refresh_btn = QPushButton("Refresh Ports", sidebar)
        self.refresh_btn.clicked.connect(self.refresh_ports)
        sidebar_layout.addWidget(self.refresh_btn)

        # Демо-режим
        self.demo_checkbox = QCheckBox("Demo Simulator Mode", sidebar)
        self.demo_checkbox.setChecked(True)
        self.demo_checkbox.stateChanged.connect(self.on_demo_toggle)
        sidebar_layout.addWidget(self.demo_checkbox)

        # Кнопка подключения
        self.connect_btn = QPushButton("Connect", sidebar)
        self.connect_btn.setObjectName("ConnectButton")
        self.connect_btn.clicked.connect(self.toggle_connection)
        sidebar_layout.addWidget(self.connect_btn)

        # Статус соединения
        status_title = QLabel("Status:", sidebar)
        status_title.setFont(QFont("Arial", 9))
        sidebar_layout.addWidget(status_title)

        self.status_val = QLabel("DEMO MODE ACTIVE", sidebar)
        self.status_val.setObjectName("StatusLabel")
        self.status_val.setFont(QFont("Arial", 11, QFont.Bold))
        self.status_val.setStyleSheet("color: #ffd700;")
        self.status_val.setWordWrap(True)
        sidebar_layout.addWidget(self.status_val)

        sidebar_layout.addStretch() # Пружина вниз
        main_layout.addWidget(sidebar)

        # --- ПРАВАЯ ПАНЕЛЬ (Dashboard) ---
        dashboard = QFrame(self)
        dashboard.setObjectName("Dashboard")
        dashboard_layout = QGridLayout(dashboard)
        dashboard_layout.setContentsMargins(20, 20, 20, 20)
        dashboard_layout.setSpacing(20)

        # Виджет Спидометра (Скорость)
        self.speed_card = QFrame(dashboard)
        self.speed_card.setObjectName("Card")
        speed_card_layout = QVBoxLayout(self.speed_card)
        speed_card_layout.setContentsMargins(20, 20, 20, 20)
        
        speed_title = QLabel("SPEED", self.speed_card)
        speed_title.setFont(QFont("Arial", 14, QFont.Bold))
        speed_title.setStyleSheet("color: #a0a0a0;")
        speed_title.setAlignment(Qt.AlignCenter)
        speed_card_layout.addWidget(speed_title)

        self.speed_val_label = QLabel("0", self.speed_card)
        self.speed_val_label.setFont(QFont("Arial", 64, QFont.Bold))
        self.speed_val_label.setAlignment(Qt.AlignCenter)
        speed_card_layout.addWidget(self.speed_val_label)

        speed_unit = QLabel("km/h", self.speed_card)
        speed_unit.setFont(QFont("Arial", 12, QFont.Bold))
        speed_unit.setStyleSheet("color: #5f9ea0;")
        speed_unit.setAlignment(Qt.AlignCenter)
        speed_card_layout.addWidget(speed_unit)

        self.speed_progress = QProgressBar(self.speed_card)
        self.speed_progress.setMaximum(220)
        self.speed_progress.setValue(0)
        self.speed_progress.setTextVisible(False)
        self.speed_progress.setFixedHeight(10)
        speed_card_layout.addWidget(self.speed_progress)

        dashboard_layout.addWidget(self.speed_card, 0, 0)

        # Виджет Тахометра (Обороты)
        self.rpm_card = QFrame(dashboard)
        self.rpm_card.setObjectName("Card")
        rpm_card_layout = QVBoxLayout(self.rpm_card)
        rpm_card_layout.setContentsMargins(20, 20, 20, 20)

        rpm_title = QLabel("RPM", self.rpm_card)
        rpm_title.setFont(QFont("Arial", 14, QFont.Bold))
        rpm_title.setStyleSheet("color: #a0a0a0;")
        rpm_title.setAlignment(Qt.AlignCenter)
        rpm_card_layout.addWidget(rpm_title)

        self.rpm_val_label = QLabel("0", self.rpm_card)
        self.rpm_val_label.setFont(QFont("Arial", 64, QFont.Bold))
        self.rpm_val_label.setAlignment(Qt.AlignCenter)
        rpm_card_layout.addWidget(self.rpm_val_label)

        rpm_unit = QLabel("RPM", self.rpm_card)
        rpm_unit.setFont(QFont("Arial", 12, QFont.Bold))
        rpm_unit.setStyleSheet("color: #00fa9a;")
        rpm_unit.setAlignment(Qt.AlignCenter)
        rpm_card_layout.addWidget(rpm_unit)

        self.rpm_progress = QProgressBar(self.rpm_card)
        self.rpm_progress.setMaximum(7000)
        self.rpm_progress.setValue(0)
        self.rpm_progress.setTextVisible(False)
        self.rpm_progress.setFixedHeight(10)
        self.rpm_progress.setStyleSheet("""
            QProgressBar::chunk {
                background-color: #00fa9a;
                border-radius: 5px;
            }
        """)
        rpm_card_layout.addWidget(self.rpm_progress)

        dashboard_layout.addWidget(self.rpm_card, 0, 1)

        main_layout.addWidget(dashboard, 1)

    def refresh_ports(self):
        self.status_val.setText("Scanning ports...")
        self.status_val.setStyleSheet("color: #ffd700;")
        
        # Получаем список портов без блокировки UI
        ports = obd.scan_serial()
        
        self.port_dropdown.clear()
        self.port_dropdown.addItem("Auto-Detect")
        self.port_dropdown.addItems(ports)
        
        if self.demo_checkbox.isChecked():
            self.status_val.setText("DEMO MODE ACTIVE")
            self.status_val.setStyleSheet("color: #ffd700;")
        else:
            self.status_val.setText("Ready to Connect")
            self.status_val.setStyleSheet("color: #a0a0a0;")

    def on_demo_toggle(self, state):
        if state == Qt.Checked:
            self.status_val.setText("DEMO MODE ACTIVE")
            self.status_val.setStyleSheet("color: #ffd700;")
        else:
            self.status_val.setText("Ready to Connect")
            self.status_val.setStyleSheet("color: #a0a0a0;")

    def toggle_connection(self):
        if self.is_running:
            # Отключение
            self.is_running = False
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("background-color: #2b73b5;")
            self.port_dropdown.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.demo_checkbox.setEnabled(True)
            
            # Сброс датчиков
            self.speed_val_label.setText("0")
            self.rpm_val_label.setText("0")
            self.speed_progress.setValue(0)
            self.rpm_progress.setValue(0)
            
            if self.demo_checkbox.isChecked():
                self.status_val.setText("DEMO MODE ACTIVE")
                self.status_val.setStyleSheet("color: #ffd700;")
            else:
                self.status_val.setText("Disconnected")
                self.status_val.setStyleSheet("color: #e06666;")
        else:
            # Подключение
            self.is_running = True
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setStyleSheet("background-color: #c84b4b;")
            self.port_dropdown.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.demo_checkbox.setEnabled(False)

            self.status_val.setText("Connecting...")
            self.status_val.setStyleSheet("color: #ffd700;")

            # Запускаем опрос в фоновом потоке
            self.polling_thread = threading.Thread(target=self.poll_obd_data, daemon=True)
            self.polling_thread.start()

    def poll_obd_data(self):
        is_demo = self.demo_checkbox.isChecked()

        if is_demo:
            self.run_demo_loop()
        else:
            selected_port = self.port_dropdown.currentText()
            port_param = None if selected_port == "Auto-Detect" else selected_port

            try:
                self.connection = obd.OBD(portstr=port_param, fast=False)
                if self.connection.is_connected():
                    status_str = f"Connected on {self.connection.port_name()}"
                    cmd_speed = obd.commands.SPEED
                    cmd_rpm = obd.commands.RPM

                    while self.is_running:
                        speed_res = self.connection.query(cmd_speed)
                        rpm_res = self.connection.query(cmd_rpm)

                        speed_val = speed_res.value.magnitude if not speed_res.is_null() else 0.0
                        rpm_val = rpm_res.value.magnitude if not rpm_res.is_null() else 0.0

                        # Отправляем данные в главный поток
                        self.signals.update_data.emit(speed_val, rpm_val, status_str)
                        time.sleep(0.1)
                else:
                    self.signals.connection_failed.emit("Connection Failed")
            except Exception as e:
                self.signals.connection_failed.emit(f"Error: {str(e)}")
            finally:
                if self.connection:
                    self.connection.close()
                    self.connection = None

    def run_demo_loop(self):
        # Алгоритм симуляции поездки
        demo_time = 0.0
        demo_gear = 1
        current_speed = 0.0
        current_rpm = 800.0

        while self.is_running:
            demo_time += 0.08
            cycle = (demo_time // 30) % 2

            if cycle == 0:  # Разгон
                gear_max_speeds = {1: 30, 2: 60, 3: 95, 4: 130, 5: 180}
                current_max = gear_max_speeds.get(demo_gear, 180)

                if current_speed >= current_max - 5 and demo_gear < 5:
                    demo_gear += 1
                    current_rpm = 1500
                    time.sleep(0.3)
                    continue

                current_speed += (6.0 - demo_gear) * 0.15
                if current_speed > 180:
                    current_speed = 180

                base_rpm = 1000 + (current_speed / current_max) * 4500
                current_rpm = base_rpm + random.uniform(-50, 50)
            else:  # Торможение
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

            self.signals.update_data.emit(current_speed, current_rpm, "Connected (Simulated)")
            time.sleep(0.05)

    def on_data_received(self, speed, rpm, status):
        self.speed_val_label.setText(f"{int(speed)}")
        self.rpm_val_label.setText(f"{int(rpm)}")
        self.speed_progress.setValue(int(speed))
        self.rpm_progress.setValue(int(rpm))
        self.status_val.setText(status)
        self.status_val.setStyleSheet("color: #2ecc71;")

        # Динамический цвет тахометра в зависимости от оборотов
        if rpm > 5500:
            color = "#ff4c4c" # Красная зона
        elif rpm > 4000:
            color = "#ffb732" # Оранжевая зона
        else:
            color = "#00fa9a" # Зеленая зона

        self.rpm_progress.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 5px;
            }}
        """)

    def on_connection_failed(self, error_msg):
        self.status_val.setText(error_msg)
        self.status_val.setStyleSheet("color: #c84b4b;")
        if self.is_running:
            self.toggle_connection()

    def closeEvent(self, event):
        # Безопасное завершение при закрытии окна
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
        # Красивые стили для темной темы приложения (QSS)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            #Sidebar {
                background-color: #252526;
                border-right: 1px solid #3c3c3c;
            }
            #Dashboard {
                background-color: #1e1e1e;
            }
            #Card {
                background-color: #2d2d2d;
                border: 1px solid #3e3e3e;
                border-radius: 12px;
            }
            QLabel {
                color: #ffffff;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                min-width: 150px;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: white;
                selection-background-color: #2b73b5;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: white;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            #ConnectButton {
                background-color: #2b73b5;
                border: none;
                font-weight: bold;
                padding: 10px;
            }
            #ConnectButton:hover {
                background-color: #3b83c5;
            }
            QCheckBox {
                color: white;
            }
            QProgressBar {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background-color: #5f9ea0;
                border-radius: 5px;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OBDDashboardQT()
    window.show()
    sys.exit(app.exec_())
