import serial
import time
import sys
import random
import math

def run_emulator(port):
    print("=" * 60)
    print(f"   Эмулятор OBD-II ELM327 запущен на порту: {port}")
    print("   Ожидание подключения клиента (нашего GUI приложения)...")
    print("   Нажмите Ctrl+C для остановки эмулятора.")
    print("=" * 60)

    try:
        # Открываем порт эмулятора.
        # Настройки по умолчанию для ELM327: скорость 38400 бод, 8 бит данных, без четности, 1 стоп-бит
        ser = serial.Serial(port, baudrate=38400, timeout=1)
    except Exception as e:
        print(f"\n[ОШИБКА] Не удалось открыть порт {port}: {e}")
        print("Убедитесь, что вы создали виртуальную пару портов (например, через com0com или socat)")
        return

    buffer = ""
    engine_temp = 50.0  # Начальная температура двигателя для эмуляции
    start_time = time.time()
    headers_on = False  # Флаг заголовков (ATH1/ATH0)
    current_header = "7E0"  # Текущий CAN-заголовок (по умолчанию Engine ECU)

    try:
        while True:
            if ser.in_waiting > 0:
                # Читаем байты из порта
                data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                buffer += data
                
                # Символ возврата каретки '\r' означает конец команды в ELM327
                if '\r' in buffer:
                    parts = buffer.split('\r')
                    # Последняя часть (без '\r') остается в буфере
                    buffer = parts[-1]
                    
                    # Обрабатываем все завершенные команды
                    for cmd in parts[:-1]:
                        cmd = cmd.strip().upper()
                        if not cmd:
                            continue
                        
                        # Убираем пробелы
                        cmd_clean = cmd.replace(" ", "")
                        print(f"📥 [Получен запрос]: '{cmd}'")
                        
                        # Отслеживаем состояние заголовков и текущий CAN-заголовок
                        if cmd_clean == "ATH1":
                            headers_on = True
                        elif cmd_clean == "ATH0":
                            headers_on = False
                        elif cmd_clean == "ATZ":
                            headers_on = False
                            current_header = "7E0"
                        elif cmd_clean.startswith("ATSH"):
                            current_header = cmd_clean[4:]
                            print(f"   ℹ️ Установлен CAN-заголовок запроса: {current_header}")
                        
                        # Генерируем ответ OBD-II / UDS
                        response = handle_command(cmd_clean, engine_temp, start_time, headers_on, current_header)
                        
                        # Имитируем небольшую задержку ответа реального ЭБУ (50 мс)
                        time.sleep(0.05)
                        
                        clean_response = response.replace('\r', '\\r')
                        print(f"📤 [Отправлен ответ]: '{clean_response}'")
                        # Отправляем байты обратно клиенту
                        ser.write(response.encode('utf-8'))
                        
                        # Медленно прогреваем двигатель на 0.05 градуса за запрос
                        if engine_temp < 92.0:
                            engine_temp += 0.05

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Работа эмулятора остановлена пользователем.")
    finally:
        ser.close()
        print("🔌 Порт закрыт.")

def format_response(payload_hex, headers_on, req_header):
    """
    Форматирует ответ от ЭБУ в соответствии с флагом заголовков (ATH0/ATH1).
    Автоматически рассчитывает ответный CAN-заголовок и длину payload.
    """
    if not headers_on:
        return f"{payload_hex}\r\r>"
    
    # Расчет ответного CAN-заголовка (для VAG обычно Request Header + 8 в hex)
    try:
        req_val = int(req_header, 16)
        resp_val = req_val + 8
        resp_header = f"{resp_val:03X}"
    except Exception:
        resp_header = "7E8"
        
    # Расчет длины данных в байтах
    clean_payload = payload_hex.replace(" ", "")
    num_bytes = len(clean_payload) // 2
    
    return f"{resp_header} {num_bytes:02X} {payload_hex}\r\r>"

def handle_command(cmd, temp, start_time, headers_on, req_header):
    """
    Разбирает входящие AT-команды ELM327, стандартные OBD-II запросы PIDs (Mode 01),
    запрос ошибок (Mode 03) и низкоуровневые UDS-запросы Service 0x22 (Read Data By Identifier).
    """
    # 1. Базовые команды инициализации ELM327 (выполняются самим чипом ELM327, без заголовков)
    if cmd == "ATZ":
        return "ELM327 v1.5\r\r>"
    elif cmd == "ATRV":
        return "12.4V\r\r>"
    elif cmd == "ATDPN":
        return "A6\r\r>"
    elif cmd.startswith("AT"):
        return "OK\r\r>"
        
    t = time.time() - start_time
    
    # 2. Низкоуровневые UDS запросы Service 0x22 (Read Data By Identifier)
    # Формат ответа: 62 + DID + Данные
    if cmd.startswith("22"):
        did = cmd[2:] # Например, 028C
        

        # Симулируемые параметры EV
        # Скорость: wave-like от 0 до 150 км/ч
        speed = max(0.0, 75.0 + 65.0 * math.sin(t / 10.0))
        # Заряд батареи (SOC): медленно падает с 85%
        cycle = (t // 30) % 2 # 0 = разгон, 1 = рекуперация
        base_soc = 85.0 - (t / 60.0) % 15.0
        soc = base_soc + (0.5 if cycle == 1 else 0.0)
        # Напряжение HV батареи (V)
        voltage = 396.0 - (speed / 150.0) * 20.0 + random.uniform(-1, 1)
        # Температура батареи (°C)
        battery_temp = 22.0 + 3.0 * math.sin(t / 80.0)
        # Ток батареи (A)
        if cycle == 0:
            current_amps = - (speed / 150.0) * 150.0 - random.uniform(0, 5)
        else:
            current_amps = (speed / 150.0) * 80.0 + random.uniform(0, 3) if speed > 0 else -1.0
        # Преобразуем ток в сырое значение (offset = 150000, 100A = 10000)
        current_raw = int(150000.0 + current_amps * 100.0)
        
        # Декодируем и отдаем параметры в зависимости от запрошенного DID
        if did in ["F40D", "0281"]: # Скорость (22F40D или 220281)
            raw_speed = int(speed * 100)
            a = (raw_speed >> 8) & 0xFF
            b = raw_speed & 0xFF
            data = f"62 {did[:2]} {did[2:]} {a:02X} {b:02X}"
            return format_response(data, headers_on, req_header)
            
        elif did in ["028C", "F45B"]: # SOC (22028C или 22F45B)
            raw_soc = int(soc)
            data = f"62 {did[:2]} {did[2:]} {raw_soc:02X}"
            return format_response(data, headers_on, req_header)
            
        elif did == "0289" or did == "4800" or did.startswith("1E3B") or did.startswith("01EB") or did.startswith("1D3B") or did.startswith("742F") or did.startswith("029A"): # Напряжение HV
            # VAG HV Voltage (DID 1E3B) имеет делитель 10.0, остальные 4.0
            if did.startswith("1E3B"):
                raw_volts = int(voltage * 10)
            else:
                raw_volts = int(voltage * 4)
            a = (raw_volts >> 8) & 0xFF
            b = raw_volts & 0xFF
            did_h = did[:2]
            did_l = did[2:]
            data = f"62 {did_h} {did_l} {a:02X} {b:02X}"
            return format_response(data, headers_on, req_header)
            
        elif did.startswith("1EB1") or did == "028B" or did.startswith("1E3F") or did.startswith("1E34") or did == "F405": # Температура
            # VAG Battery Temp (1EB1): Формула A - 100. Остальные A - 40.
            if did.startswith("1EB1"):
                raw_temp = int(battery_temp + 100) & 0xFF
            else:
                raw_temp = int(battery_temp + 40) & 0xFF
            did_h = did[:2]
            did_l = did[2:]
            data = f"62 {did_h} {did_l} {raw_temp:02X}"
            return format_response(data, headers_on, req_header)
            
        elif did.startswith("1E3D") or did == "028A" or did.startswith("1E3C") or did.startswith("01EC"): # Ток
            a = (current_raw >> 16) & 0xFF
            b = (current_raw >> 8) & 0xFF
            c = current_raw & 0xFF
            did_h = did[:2]
            did_l = did[2:]
            data = f"62 {did_h} {did_l} {a:02X} {b:02X} {c:02X}"
            return format_response(data, headers_on, req_header)
            
        else:
            # Для других DID возвращаем пустой UDS ответ с кодом 62 + DID + 00
            did_h = did[:2]
            did_l = did[2:]
            data = f"62 {did_h} {did_l} 00"
            return format_response(data, headers_on, req_header)

    # 3. Запрос кодов ошибок DTC (Режим 03)
    elif cmd == "03":
        # Возвращаем симулированные ошибки P0101 и P0300 для логгера
        data = "43 01 01 03 00"
        return format_response(data, headers_on, req_header)

    # 4. Стандартные запросы параметров OBD-II (Режим 01)
    elif cmd == "0100":
        data = "41 00 BE 3E A8 13"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "0101":
        data = "41 01 00 07 E5 A5"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "010C": # RPM ДВС
        rpm = int(3000 + 2000 * math.sin(t / 5.0))
        hex_val = int(rpm * 4)
        a = (hex_val >> 8) & 0xFF
        b = hex_val & 0xFF
        data = f"41 0C {a:02X} {b:02X}"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "010D": # Скорость автомобиля ДВС
        speed = int(90 + 50 * math.sin(t / 8.0))
        data = f"41 0D {speed:02X}"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "0105": # Температура ДВС
        hex_temp = int(temp + 40) & 0xFF
        data = f"41 05 {hex_temp:02X}"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "0140":
        data = "41 40 00 00 00 20"
        return format_response(data, headers_on, req_header)
        
    elif cmd == "015B": # SOC гибридной батареи
        soc_val = max(15.0, 85.0 - (t / 60.0) % 15.0)
        hex_charge = int(soc_val * 255 / 100) & 0xFF
        data = f"41 5B {hex_charge:02X}"
        return format_response(data, headers_on, req_header)

    else:
        return "NO DATA\r\r>"

if __name__ == "__main__":
    # По умолчанию запускаем на COM10 (для Windows). Пользователь может передать другой порт в аргументах
    port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
    run_emulator(port)
