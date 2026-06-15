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
    update_data = pyqtSignal(float, float, float, float, str)  # speed, rpm, coolant, throttle, status
    connection_failed = pyqtSignal(str)                       # error message

class OBDDashboardQT(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("OBD-II Smart Dashboard (Qt)")
        self.setGeometry(100, 100, 950, 560)
        self.setMinimumSize(900, 520)

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
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(25, 30, 25, 30)
        sidebar_layout.setSpacing(20)

        # Логотип / Название
        logo = QLabel("ELM327", sidebar)
        logo.setFont(QFont("Arial", 16, QFont.Bold))
        logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo)

        # Разделительная линия
        line = QFrame(sidebar)
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333333; max-height: 1px;")
        sidebar_layout.addWidget(line)

        # Выбор портов
        port_label = QLabel("Select Port:", sidebar)
        port_label.setFont(QFont("Arial", 10, QFont.Bold))
        port_label.setStyleSheet("color: #888888;")
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
        status_title.setFont(QFont("Arial", 10, QFont.Bold))
        status_title.setStyleSheet("color: #888888;")
        sidebar_layout.addWidget(status_title)

        self.status_val = QLabel("DEMO MODE ACTIVE", sidebar)
        self.status_val.setObjectName("StatusLabel")
        self.status_val.setFont(QFont("Arial", 11, QFont.Bold))
        self.status_val.setStyleSheet("color: #ffd700;")
        self.status_val.setWordWrap(True)
        sidebar_layout.addWidget(self.status_val)

        sidebar_layout.addStretch() # Уводит все элементы наверх
        main_layout.addWidget(sidebar)

        # --- ПРАВАЯ ПАНЕЛЬ (Dashboard Grid) ---
        dashboard = QFrame(self)
        dashboard.setObjectName("Dashboard")
        dashboard_layout = QGridLayout(dashboard)
        dashboard_layout.setContentsMargins(25, 25, 25, 25)
        dashboard_layout.setSpacing(20)

        # 1. Виджет Спидометра (Скорость) - ТОП СЛЕВА
        self.speed_card = QFrame(dashboard)
        self.speed_card.setObjectName("SpeedCard")
        speed_layout = QVBoxLayout(self.speed_card)
        speed_layout.setContentsMargins(20, 20, 20, 20)
        speed_layout.addStretch(1)
        
        speed_title = QLabel("⚡ SPEED", self.speed_card)
        speed_title.setFont(QFont("Arial", 11, QFont.Bold))
        speed_title.setStyleSheet("color: #00d2ff;")
        speed_title.setAlignment(Qt.AlignCenter)
        speed_layout.addWidget(speed_title)

        self.speed_val_label = QLabel("0", self.speed_card)
        self.speed_val_label.setFont(QFont("Impact", 68))
        self.speed_val_label.setAlignment(Qt.AlignCenter)
        speed_layout.addWidget(self.speed_val_label)

        speed_unit = QLabel("km/h", self.speed_card)
        speed_unit.setFont(QFont("Arial", 11, QFont.Bold))
        speed_unit.setStyleSheet("color: #555555;")
        speed_unit.setAlignment(Qt.AlignCenter)
        speed_layout.addWidget(speed_unit)

        self.speed_progress = QProgressBar(self.speed_card)
        self.speed_progress.setObjectName("SpeedProgress")
        self.speed_progress.setMaximum(220)
        self.speed_progress.setValue(0)
        self.speed_progress.setTextVisible(False)
        self.speed_progress.setFixedHeight(12)
        speed_layout.addWidget(self.speed_progress)
        speed_layout.addStretch(1)

        dashboard_layout.addWidget(self.speed_card, 0, 0)

        # 2. Виджет Тахометра (Обороты) - ТОП СПРАВА
        self.rpm_card = QFrame(dashboard)
        self.rpm_card.setObjectName("RpmCard")
        rpm_layout = QVBoxLayout(self.rpm_card)
        rpm_layout.setContentsMargins(20, 20, 20, 20)
        rpm_layout.addStretch(1)

        rpm_title = QLabel("🔥 ENGINE RPM", self.rpm_card)
        rpm_title.setFont(QFont("Arial", 11, QFont.Bold))
        rpm_title.setStyleSheet("color: #00fa9a;")
        rpm_title.setAlignment(Qt.AlignCenter)
        rpm_layout.addWidget(rpm_title)

        self.rpm_val_label = QLabel("0", self.rpm_card)
        self.rpm_val_label.setFont(QFont("Impact", 68))
        self.rpm_val_label.setAlignment(Qt.AlignCenter)
        rpm_layout.addWidget(self.rpm_val_label)

        rpm_unit = QLabel("rpm", self.rpm_card)
        rpm_unit.setFont(QFont("Arial", 11, QFont.Bold))
        rpm_unit.setStyleSheet("color: #555555;")
        rpm_unit.setAlignment(Qt.AlignCenter)
        rpm_layout.addWidget(rpm_unit)

        self.rpm_progress = QProgressBar(self.rpm_card)
        self.rpm_progress.setObjectName("RpmProgress")
        self.rpm_progress.setMaximum(7000)
        self.rpm_progress.setValue(0)
        self.rpm_progress.setTextVisible(False)
        self.rpm_progress.setFixedHeight(12)
        rpm_layout.addWidget(self.rpm_progress)
        rpm_layout.addStretch(1)

        dashboard_layout.addWidget(self.rpm_card, 0, 1)

        # 3. Виджет Температуры (Охл. жидкость) - БОТТОМ СЛЕВА
        self.temp_card = QFrame(dashboard)
        self.temp_card.setObjectName("TempCard")
        temp_layout = QVBoxLayout(self.temp_card)
        temp_layout.setContentsMargins(20, 15, 20, 15)
        temp_layout.addStretch(1)

        temp_title = QLabel("🌡️ COOLANT TEMP", self.temp_card)
        temp_title.setFont(QFont("Arial", 10, QFont.Bold))
        temp_title.setStyleSheet("color: #ff5e62;")
        temp_title.setAlignment(Qt.AlignCenter)
        temp_layout.addWidget(temp_title)

        self.temp_val_label = QLabel("--", self.temp_card)
        self.temp_val_label.setFont(QFont("Impact", 38))
        self.temp_val_label.setAlignment(Qt.AlignCenter)
        temp_layout.addWidget(self.temp_val_label)

        temp_unit = QLabel("°C", self.temp_card)
        temp_unit.setFont(QFont("Arial", 9, QFont.Bold))
        temp_unit.setStyleSheet("color: #555555;")
        temp_unit.setAlignment(Qt.AlignCenter)
        temp_layout.addWidget(temp_unit)

        self.temp_progress = QProgressBar(self.temp_card)
        self.temp_progress.setObjectName("TempProgress")
        self.temp_progress.setMaximum(120)
        self.temp_progress.setValue(0)
        self.temp_progress.setTextVisible(False)
        self.temp_progress.setFixedHeight(8)
        temp_layout.addWidget(self.temp_progress)
        temp_layout.addStretch(1)

        dashboard_layout.addWidget(self.temp_card, 1, 0)

        # 4. Виджет Дросселя (Throttle Position) - БОТТОМ СПРАВА
        self.throttle_card = QFrame(dashboard)
        self.throttle_card.setObjectName("ThrottleCard")
        throttle_layout = QVBoxLayout(self.throttle_card)
        throttle_layout.setContentsMargins(20, 15, 20, 15)
        throttle_layout.addStretch(1)

        throttle_title = QLabel("⚙️ THROTTLE POSITION", self.throttle_card)
        throttle_title.setFont(QFont("Arial", 10, QFont.Bold))
        throttle_title.setStyleSheet("color: #a88beb;")
        throttle_title.setAlignment(Qt.AlignCenter)
        throttle_layout.addWidget(throttle_title)

        self.throttle_val_label = QLabel("--", self.throttle_card)
        self.throttle_val_label.setFont(QFont("Impact", 38))
        self.throttle_val_label.setAlignment(Qt.AlignCenter)
        throttle_layout.addWidget(self.throttle_val_label)

        throttle_unit = QLabel("%", self.throttle_card)
        throttle_unit.setFont(QFont("Arial", 9, QFont.Bold))
        throttle_unit.setStyleSheet("color: #555555;")
        throttle_unit.setAlignment(Qt.AlignCenter)
        throttle_layout.addWidget(throttle_unit)

        self.throttle_progress = QProgressBar(self.throttle_card)
        self.throttle_progress.setObjectName("ThrottleProgress")
        self.throttle_progress.setMaximum(100)
        self.throttle_progress.setValue(0)
        self.throttle_progress.setTextVisible(False)
        self.throttle_progress.setFixedHeight(8)
        throttle_layout.addWidget(self.throttle_progress)
        throttle_layout.addStretch(1)

        dashboard_layout.addWidget(self.throttle_card, 1, 1)

        # Настройка пропорций строк сетки (верхняя строка больше, нижняя меньше)
        dashboard_layout.setRowStretch(0, 3)
        dashboard_layout.setRowStretch(1, 2)
        dashboard_layout.setColumnStretch(0, 1)
        dashboard_layout.setColumnStretch(1, 1)

        main_layout.addWidget(dashboard, 1)

    def refresh_ports(self):
        self.status_val.setText("Scanning ports...")
        self.status_val.setStyleSheet("color: #ffd700;")
        
        try:
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
        except Exception as e:
            import traceback
            print("\n[ОШИБКА СКАНИРОВАНИЯ ПОРТОВ]")
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
            # Отключение
            self.is_running = False
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("""
                QPushButton#ConnectButton {
                    background-color: #2b73b5;
                }
                QPushButton#ConnectButton:hover {
                    background-color: #3b83c5;
                }
            """)
            self.port_dropdown.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.demo_checkbox.setEnabled(True)
            
            # Сброс датчиков
            self.speed_val_label.setText("0")
            self.rpm_val_label.setText("0")
            self.temp_val_label.setText("--")
            self.throttle_val_label.setText("--")
            self.speed_progress.setValue(0)
            self.rpm_progress.setValue(0)
            self.temp_progress.setValue(0)
            self.throttle_progress.setValue(0)
            
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
            self.connect_btn.setStyleSheet("""
                QPushButton#ConnectButton {
                    background-color: #c84b4b;
                }
                QPushButton#ConnectButton:hover {
                    background-color: #a83b3b;
                }
            """)
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
                    cmd_temp = obd.commands.COOLANT_TEMP
                    cmd_throttle = obd.commands.THROTTLE_POS

                    while self.is_running:
                        speed_res = self.connection.query(cmd_speed)
                        rpm_res = self.connection.query(cmd_rpm)
                        temp_res = self.connection.query(cmd_temp)
                        throttle_res = self.connection.query(cmd_throttle)

                        speed_val = speed_res.value.magnitude if not speed_res.is_null() else 0.0
                        rpm_val = rpm_res.value.magnitude if not rpm_res.is_null() else 0.0
                        temp_val = temp_res.value.magnitude if not temp_res.is_null() else 0.0
                        throttle_val = throttle_res.value.magnitude if not throttle_res.is_null() else 0.0

                        # Отправляем данные в главный поток
                        self.signals.update_data.emit(speed_val, rpm_val, temp_val, throttle_val, status_str)
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
        current_temp = 45.0  # Начальная температура двигателя при прогреве

        while self.is_running:
            demo_time += 0.08
            cycle = (demo_time // 30) % 2
            
            # 1. Симуляция прогрева двигателя (температура растет до 90 градусов)
            if current_temp < 90.0:
                current_temp += 0.05
            else:
                current_temp = 90.0 + random.uniform(-0.5, 0.5)

            # 2. Симуляция педали газа (Дроссель)
            if cycle == 0:  # Разгон
                # Дроссель выжат при разгоне
                current_throttle = 75.0 + random.uniform(-5.0, 5.0)
                
                gear_max_speeds = {1: 30, 2: 60, 3: 95, 4: 130, 5: 180}
                current_max = gear_max_speeds.get(demo_gear, 180)

                # Переключение передач вверх
                if current_speed >= current_max - 5 and demo_gear < 5:
                    demo_gear += 1
                    current_rpm = 1500
                    current_throttle = 0.0  # Сброс газа при выжиме сцепления
                    self.signals.update_data.emit(current_speed, current_rpm, current_temp, current_throttle, "Connected (Simulated)")
                    time.sleep(0.3)
                    continue

                current_speed += (6.0 - demo_gear) * 0.15
                if current_speed > 180:
                    current_speed = 180

                base_rpm = 1000 + (current_speed / current_max) * 4500
                current_rpm = base_rpm + random.uniform(-50, 50)
            else:  # Торможение
                # Дроссель отпущен
                current_throttle = 5.0 + random.uniform(-2.0, 2.0)
                
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
                    current_throttle = 0.0

            self.signals.update_data.emit(current_speed, current_rpm, current_temp, current_throttle, "Connected (Simulated)")
            time.sleep(0.05)

    def on_data_received(self, speed, rpm, coolant, throttle, status):
        # Обновление Speed
        self.speed_val_label.setText(f"{int(speed)}")
        self.speed_progress.setValue(int(speed))
        
        # Обновление RPM
        self.rpm_val_label.setText(f"{int(rpm)}")
        self.rpm_progress.setValue(int(rpm))

        # Обновление Coolant
        self.temp_val_label.setText(f"{int(coolant)}")
        self.temp_progress.setValue(int(coolant))

        # Обновление Throttle
        self.throttle_val_label.setText(f"{int(throttle)}")
        self.throttle_progress.setValue(int(throttle))

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
                border-radius: 6px;
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
        # Премиальный темный стиль в автомобильном неоновом дизайне (QSS)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f1015;
            }
            
            /* ЛЕВАЯ ПАНЕЛЬ */
            #Sidebar {
                background-color: #15161e;
                border-right: 1px solid #222533;
            }
            
            QLabel {
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            
            QLabel#StatusLabel {
                font-size: 11px;
                padding: 4px;
            }

            QComboBox {
                background-color: #1c1e29;
                color: #ffffff;
                border: 1px solid #2e3247;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #1c1e29;
                color: #ffffff;
                border: 1px solid #2e3247;
                selection-background-color: #2b73b5;
            }
            
            QPushButton {
                background-color: #222533;
                color: #ffffff;
                border: 1px solid #2e3247;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2c3047;
                border-color: #3b4260;
            }
            QPushButton:pressed {
                background-color: #15161e;
            }
            
            #ConnectButton {
                background-color: #0072ff;
                border: none;
                font-size: 13px;
                padding: 12px;
            }
            #ConnectButton:hover {
                background-color: #0082ff;
            }
            
            QCheckBox {
                color: #a0a5c1;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }

            /* КАРТОЧКИ ПРИБОРОВ */
            #SpeedCard, #RpmCard, #TempCard, #ThrottleCard {
                background-color: #15161e;
                border: 1px solid #222533;
                border-radius: 16px;
            }
            
            /* Цветные верхние границы (акценты) */
            #SpeedCard { border-top: 3px solid #00d2ff; }
            #RpmCard { border-top: 3px solid #00fa9a; }
            #TempCard { border-top: 3px solid #ff5e62; }
            #ThrottleCard { border-top: 3px solid #a88beb; }
            
            QLabel[text="0"], QLabel[text="--"] {
                color: #ffffff;
                font-family: "Impact", "Arial Black", sans-serif;
            }

            /* ШКАЛЫ ПРОГРЕССА */
            QProgressBar {
                background-color: #090a0f;
                border: 1px solid #1c1e29;
                border-radius: 6px;
                text-align: center;
            }
            
            #SpeedProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0052d4, stop:0.5 #4364f7, stop:1 #6fb1fc);
                border-radius: 5px;
            }
            
            #RpmProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00fa9a, stop:1 #00ffd0);
                border-radius: 5px;
            }
            
            #TempProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c6ff, stop:1 #ff5e62);
                border-radius: 3px;
            }
            
            #ThrottleProgress::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7f00ff, stop:1 #e100ff);
                border-radius: 3px;
            }
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OBDDashboardQT()
    window.show()
    sys.exit(app.exec_())
