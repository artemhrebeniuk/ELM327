import tkinter as tk
import customtkinter as ctk
import obd
import threading
import time
import sys
import random

# Устанавливаем тему оформления
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class OBDDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Настройка окна
        self.title("OBD-II Smart Dashboard")
        self.geometry("800x480")
        self.minsize(750, 430)

        # Состояние подключения и данных
        self.connection = None
        self.polling_thread = None
        self.is_running = False
        
        # Общие переменные состояния (потокобезопасные)
        self.current_speed = 0.0
        self.current_rpm = 0.0
        self.connection_status = "Disconnected"
        self.active_port = ""

        # Для демо-режима
        self.demo_time = 0.0
        self.demo_gear = 1

        # Создаем сетку (Grid Layout)
        self.grid_columnconfigure(0, weight=1) # Левая панель (управление)
        self.grid_columnconfigure(1, weight=3) # Правая панель (приборы)
        self.grid_rowconfigure(0, weight=1)

        # --- ЛЕВАЯ ПАНЕЛЬ (Панель управления) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        # Логотип / Название
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="⚡ OBD-II ELM327", font=ctk.CTkFont(size=18, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Выбор портов
        self.port_label = ctk.CTkLabel(self.sidebar_frame, text="Select Port:", anchor="w")
        self.port_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.port_dropdown = ctk.CTkOptionMenu(self.sidebar_frame, values=["Auto-Detect"])
        self.port_dropdown.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Кнопка обновления портов
        self.refresh_btn = ctk.CTkButton(self.sidebar_frame, text="Refresh Ports", command=self.refresh_ports, fg_color="transparent", border_width=1)
        self.refresh_btn.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        # Переключатель Демо-режима
        self.demo_switch = ctk.CTkSwitch(self.sidebar_frame, text="Demo Simulator Mode")
        self.demo_switch.grid(row=4, column=0, padx=20, pady=15)
        self.demo_switch.select() # По умолчанию включен демо-режим для быстрого теста

        # Кнопка Подключения
        self.connect_btn = ctk.CTkButton(self.sidebar_frame, text="Connect", command=self.toggle_connection, fg_color="#2b73b5", hover_color="#1f5385")
        self.connect_btn.grid(row=5, column=0, padx=20, pady=10, sticky="ew")

        # Статус соединения
        self.status_title_label = ctk.CTkLabel(self.sidebar_frame, text="Status:", anchor="w", font=ctk.CTkFont(size=11))
        self.status_title_label.grid(row=6, column=0, padx=20, pady=(15, 0), sticky="w")
        
        self.status_val_label = ctk.CTkLabel(self.sidebar_frame, text="DEMO MODE ACTIVE", text_color="#ffd700", font=ctk.CTkFont(size=13, weight="bold"))
        self.status_val_label.grid(row=7, column=0, padx=20, pady=0, sticky="w")

        # --- ПРАВАЯ ПАНЕЛЬ (Dashboard) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Виджет Спидометра (Скорость)
        self.speed_card = ctk.CTkFrame(self.main_frame, corner_radius=15)
        self.speed_card.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.speed_card.grid_columnconfigure(0, weight=1)
        self.speed_card.grid_rowconfigure((0, 1, 2, 3), weight=1)

        self.speed_title = ctk.CTkLabel(self.speed_card, text="SPEED", font=ctk.CTkFont(size=16, weight="bold", slant="italic"), text_color="#a0a0a0")
        self.speed_title.grid(row=0, column=0, pady=(20, 0))

        self.speed_value_label = ctk.CTkLabel(self.speed_card, text="0", font=ctk.CTkFont(size=72, weight="bold"))
        self.speed_value_label.grid(row=1, column=0)

        self.speed_unit = ctk.CTkLabel(self.speed_card, text="km/h", font=ctk.CTkFont(size=16, weight="bold"), text_color="#5f9ea0")
        self.speed_unit.grid(row=2, column=0, pady=(0, 20))

        self.speed_progress = ctk.CTkProgressBar(self.speed_card, width=200, height=12)
        self.speed_progress.set(0)
        self.speed_progress.grid(row=3, column=0, pady=(0, 30))

        # Виджет Тахометра (Обороты двигателя)
        self.rpm_card = ctk.CTkFrame(self.main_frame, corner_radius=15)
        self.rpm_card.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.rpm_card.grid_columnconfigure(0, weight=1)
        self.rpm_card.grid_rowconfigure((0, 1, 2, 3), weight=1)

        self.rpm_title = ctk.CTkLabel(self.rpm_card, text="RPM", font=ctk.CTkFont(size=16, weight="bold", slant="italic"), text_color="#a0a0a0")
        self.rpm_title.grid(row=0, column=0, pady=(20, 0))

        self.rpm_value_label = ctk.CTkLabel(self.rpm_card, text="0", font=ctk.CTkFont(size=72, weight="bold"))
        self.rpm_value_label.grid(row=1, column=0)

        self.rpm_unit = ctk.CTkLabel(self.rpm_card, text="RPM", font=ctk.CTkFont(size=16, weight="bold"), text_color="#00fa9a")
        self.rpm_unit.grid(row=2, column=0, pady=(0, 20))

        self.rpm_progress = ctk.CTkProgressBar(self.rpm_card, width=200, height=12, progress_color="#00fa9a")
        self.rpm_progress.set(0)
        self.rpm_progress.grid(row=3, column=0, pady=(0, 30))

        # Назначаем хэндлер для безопасного выхода
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Первичное сканирование портов (откладываем на 100мс для корректной отрисовки окна в macOS)
        self.after(100, self.refresh_ports)

        # Запускаем цикл обновления UI (откладываем на 150мс)
        self.after(150, self.update_ui_loop)

    def refresh_ports(self):
        """
        Сканирует доступные COM-порты и обновляет выпадающий список.
        """
        self.status_val_label.configure(text="Scanning ports...", text_color="#ffd700")

        # Поиск портов с помощью python-obd (pyserial)
        ports = obd.scan_serial()
        
        dropdown_values = ["Auto-Detect"] + ports
        self.port_dropdown.configure(values=dropdown_values)
        self.port_dropdown.set("Auto-Detect")
        
        # Если включен демо-режим, возвращаем статус
        if self.demo_switch.get():
            self.status_val_label.configure(text="DEMO MODE ACTIVE", text_color="#ffd700")
        else:
            self.status_val_label.configure(text="Ready to Connect", text_color="#a0a0a0")

    def toggle_connection(self):
        """
        Обрабатывает нажатие кнопки Подключить / Отключить.
        """
        if self.is_running:
            # Отключение
            self.stop_polling()
            self.connect_btn.configure(text="Connect", fg_color="#2b73b5", hover_color="#1f5385")
            self.port_dropdown.configure(state="normal")
            self.refresh_btn.configure(state="normal")
            self.demo_switch.configure(state="normal")
            
            if self.demo_switch.get():
                self.status_val_label.configure(text="DEMO MODE ACTIVE", text_color="#ffd700")
            else:
                self.status_val_label.configure(text="Disconnected", text_color="#e06666")
        else:
            # Подключение
            self.is_running = True
            self.connect_btn.configure(text="Disconnect", fg_color="#c84b4b", hover_color="#a83b3b")
            self.port_dropdown.configure(state="disabled")
            self.refresh_btn.configure(state="disabled")
            self.demo_switch.configure(state="disabled")

            # Запускаем опрос в фоновом потоке
            self.polling_thread = threading.Thread(target=self.poll_obd_data, daemon=True)
            self.polling_thread.start()

    def stop_polling(self):
        """
        Безопасно останавливает фоновый поток опроса.
        """
        self.is_running = False
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.0)
        
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
            self.connection = None

    def poll_obd_data(self):
        """
        Фоновый поток для опроса ЭБУ машины (или генерации симуляции).
        """
        is_demo = self.demo_switch.get()

        if is_demo:
            self.connection_status = "Connected (Simulated)"
            self.run_demo_loop()
        else:
            self.connection_status = "Connecting..."
            selected_port = self.port_dropdown.get()
            port_param = None if selected_port == "Auto-Detect" else selected_port

            try:
                # fast=False повышает стабильность сопряжения
                self.connection = obd.OBD(portstr=port_param, fast=False)
                
                if self.connection.is_connected():
                    self.connection_status = f"Connected on {self.connection.port_name()}"
                    
                    cmd_speed = obd.commands.SPEED
                    cmd_rpm = obd.commands.RPM

                    while self.is_running:
                        # Запросы к ЭБУ
                        speed_res = self.connection.query(cmd_speed)
                        rpm_res = self.connection.query(cmd_rpm)

                        # Извлечение значений
                        self.current_speed = speed_res.value.magnitude if not speed_res.is_null() else 0.0
                        self.current_rpm = rpm_res.value.magnitude if not rpm_res.is_null() else 0.0

                        # Задержка опроса
                        time.sleep(0.1)
                else:
                    self.connection_status = "Connection Failed"
                    self.is_running = False
            except Exception as e:
                self.connection_status = f"Error: {str(e)}"
                self.is_running = False
            finally:
                if self.connection:
                    self.connection.close()
                    self.connection = None

    def run_demo_loop(self):
        """
        Цикл генерации красивых реалистичных графиков для демонстрации.
        Симулирует разгон по передачам (1-5 передача).
        """
        self.demo_time = 0.0
        self.demo_gear = 1
        
        while self.is_running:
            # Симуляция разгона с переключением передач
            # Обороты растут, падают при переключении, скорость плавно растет
            self.demo_time += 0.08
            
            # Эмуляция педали газа (циклическая езда)
            cycle = (self.demo_time // 30) % 2 # 30 сек разгон, 30 сек торможение/круиз
            
            if cycle == 0: # Разгон
                # Зависимость оборотов от передачи и времени
                gear_max_speeds = {1: 30, 2: 60, 3: 95, 4: 130, 5: 180}
                current_max = gear_max_speeds.get(self.demo_gear, 180)
                
                # Если достигли лимита передачи - переключаемся вверх
                if self.current_speed >= current_max - 5 and self.demo_gear < 5:
                    self.demo_gear += 1
                    # Короткий провал оборотов при сцеплении
                    self.current_rpm = 1500
                    time.sleep(0.3)
                    continue

                # Симуляция роста скорости
                self.current_speed += (6.0 - self.demo_gear) * 0.15 # чем выше передача, тем медленнее ускорение
                if self.current_speed > 180:
                    self.current_speed = 180

                # Обороты двигателя растут пропорционально скорости на текущей передаче
                base_rpm = 1000 + (self.current_speed / current_max) * 4500
                # Добавим немного шума двигателя
                self.current_rpm = base_rpm + random.uniform(-50, 50)
            else: # Замедление / Сброс газа
                self.current_speed -= 0.6
                if self.current_speed < 0:
                    self.current_speed = 0
                    self.demo_gear = 1
                
                # При сбросе газа обороты плавно падают к холостым (800)
                if self.current_speed > 0:
                    # Переключение передач вниз при торможении
                    gear_min_speeds = {5: 110, 4: 80, 3: 50, 2: 20}
                    for g, min_s in gear_min_speeds.items():
                        if self.current_speed < min_s and self.demo_gear == g:
                            self.demo_gear -= 1
                    
                    self.current_rpm = 800 + (self.current_speed * 15) + random.uniform(-20, 20)
                else:
                    self.current_rpm = 800 + random.uniform(-10, 10)

            time.sleep(0.05)

    def update_ui_loop(self):
        """
        Регулярное обновление UI из переменных состояния (вызывается в главном потоке).
        """
        # Обновляем текстовые метрики
        if self.is_running:
            self.speed_value_label.configure(text=f"{int(self.current_speed)}")
            self.rpm_value_label.configure(text=f"{int(self.current_rpm)}")
            
            # Рассчитываем значение прогресс-баров (от 0 до 1)
            # Макс. шкала скорости: 220 км/ч, оборотов: 7000 об/мин
            self.speed_progress.set(min(self.current_speed / 220.0, 1.0))
            
            rpm_ratio = min(self.current_rpm / 7000.0, 1.0)
            self.rpm_progress.set(rpm_ratio)

            # Изменение цвета тахометра при высоких оборотах (красная зона > 5000 RPM)
            if self.current_rpm > 5500:
                self.rpm_progress.configure(progress_color="#ff4c4c") # Красный
                self.rpm_value_label.configure(text_color="#ff4c4c")
            elif self.current_rpm > 4000:
                self.rpm_progress.configure(progress_color="#ffb732") # Оранжевый
                self.rpm_value_label.configure(text_color="#ffb732")
            else:
                self.rpm_progress.configure(progress_color="#00fa9a") # Зеленый/Неон
                self.rpm_value_label.configure(text_color="#ffffff")

            self.status_val_label.configure(text=self.connection_status)
            if "Failed" in self.connection_status or "Error" in self.connection_status:
                self.status_val_label.configure(text_color="#c84b4b")
                # Возвращаем кнопку в исходное состояние
                if self.is_running:
                    self.toggle_connection()
            elif "Connected" in self.connection_status:
                self.status_val_label.configure(text_color="#2ecc71")
        else:
            # Сброс UI при остановке
            self.speed_value_label.configure(text="0", text_color="#ffffff")
            self.rpm_value_label.configure(text="0", text_color="#ffffff")
            self.speed_progress.set(0)
            self.rpm_progress.set(0)
            self.rpm_progress.configure(progress_color="#00fa9a")
            
            if self.demo_switch.get():
                self.status_val_label.configure(text="DEMO MODE ACTIVE", text_color="#ffd700")
            else:
                self.status_val_label.configure(text="Ready to Connect", text_color="#a0a0a0")

        # Перезапуск обновления через 50 миллисекунд (20 кадров в секунду для плавности)
        self.after(50, self.update_ui_loop)

    def on_closing(self):
        """
        Вызывается при закрытии окна. Обеспечивает безопасное закрытие потоков и портов.
        """
        self.stop_polling()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = OBDDashboard()
    app.mainloop()
