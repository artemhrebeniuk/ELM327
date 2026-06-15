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
        print("Убедитесь, что вы создали виртуальную пару портов (например, через com0com)")
        return

    buffer = ""
    engine_temp = 50.0  # Начальная температура двигателя для эмуляции
    start_time = time.time()
    
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
                        
                        # Генерируем ответ OBD-II
                        response = handle_command(cmd_clean, engine_temp, start_time)
                        
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

def handle_command(cmd, temp, start_time):
    """
    Разбирает входящие AT-команды ELM327 и стандартные OBD-II запросы PIDs (Mode 01).
    Возвращает строку ответа в формате ELM327 с приглашением к вводу '>' на конце.
    """
    # 1. Базовые команды инициализации ELM327
    if cmd == "ATZ":  # Сброс адаптера
        return "ELM327 v1.5\r\r>"
    elif cmd.startswith("AT"):  # Любые настройки (ATE0, ATL0, ATH0, ATSP и т.д.)
        return "OK\r\r>"
    
    # 2. Стандартные запросы параметров OBD-II (Режим 01)
    # Ответ должен иметь формат: 41 + PID + Данные в HEX + \r\r>
    
    # Запрос 0100: Поддерживаемые PIDs 1-20
    # Отправляем байты, подтверждающие поддержку: RPM (0C), Speed (0D), Coolant Temp (05), Throttle (11)
    if cmd == "0100":
        return "41 00 BE 3E A8 13\r\r>"
    
    # Запрос 010C: Обороты двигателя (Engine RPM)
    # Формула OBD: ((A * 256) + B) / 4. Мы кодируем обороты обратно в байты.
    elif cmd == "010C":
        t = time.time() - start_time
        # Генерируем волнообразные обороты от 1000 до 5500 rpm
        rpm = int(3000 + 2000 * math.sin(t / 5.0))
        hex_val = int(rpm * 4)
        a = (hex_val >> 8) & 0xFF
        b = hex_val & 0xFF
        return f"41 0C {a:02X} {b:02X}\r\r>"
        
    # Запрос 010D: Скорость автомобиля (Vehicle Speed)
    # Формула OBD: значение в км/ч совпадает с байтом A.
    elif cmd == "010D":
        t = time.time() - start_time
        # Скорость меняется волнообразно от 40 до 140 км/ч
        speed = int(90 + 50 * math.sin(t / 8.0))
        return f"41 0D {speed:02X}\r\r>"
        
    # Запрос 0105: Температура охлаждающей жидкости (Coolant Temp)
    # Формула OBD: A - 40. Кодируем обратно: байт A = temp + 40
    elif cmd == "0105":
        hex_temp = int(temp + 40) & 0xFF
        return f"41 05 {hex_temp:02X}\r\r>"
        
    # Запрос 0111: Положение дроссельной заслонки (Throttle Position)
    # Формула OBD: A * 100 / 255. Кодируем обратно.
    elif cmd == "0111":
        t = time.time() - start_time
        # Процент открытия заслонки колеблется от 15% до 85%
        throttle = int(50 + 35 * math.sin(t / 4.0))
        hex_throttle = int(throttle * 255 / 100) & 0xFF
        return f"41 11 {hex_throttle:02X}\r\r>"

    # Остальные PIDs возвращаем как неподдерживаемые
    else:
        return "NO DATA\r\r>"

if __name__ == "__main__":
    # По умолчанию запускаем на COM10 (для Windows). Пользователь может передать другой порт в аргументах
    port = sys.argv[1] if len(sys.argv) > 1 else "COM10"
    run_emulator(port)
