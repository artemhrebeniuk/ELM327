import obd
import time
import logging
import sys

# Настройка базового логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scan_ports():
    """
    Сканирует доступные последовательные порты и выводит их список.
    """
    logging.info("Сканирование доступных COM/tty портов...")
    ports = obd.scan_serial()
    if ports:
        logging.info(f"Найдены порты: {', '.join(ports)}")
    else:
        logging.warning("Порты не найдены. Убедитесь, что Bluetooth-адаптер сопряжен с ПК.")
    return ports

def connect_to_adapter(port=None):
    """
    Инициализирует подключение к адаптеру ELM327.
    """
    try:
        # Включаем детальное логирование самой библиотеки obd, если нужно отладить соединение
        # obd.logger.setLevel(obd.logging.DEBUG) 

        if port:
            logging.info(f"Попытка подключения к указанному порту: {port}")
            # fast=False отключает агрессивную оптимизацию команд при старте, 
            # что повышает стабильность на некоторых китайских клонах ELM327
            connection = obd.OBD(port, fast=False)
        else:
            logging.info("Попытка автоматического подключения (поиск по всем портам)...")
            connection = obd.OBD(fast=False)

        if connection.is_connected():
            logging.info(f"Успешное подключение к ELM327 на порту: {connection.port_name()}")
            return connection
        else:
            logging.error("Не удалось подключиться к OBD-II адаптеру. Проверьте питание и Bluetooth-соединение.")
            return None
            
    except Exception as e:
        logging.error(f"Критическая ошибка при подключении: {e}")
        return None

def monitor_data(connection):
    """
    В бесконечном цикле считывает обороты (RPM) и скорость (Speed).
    """
    # Подготавливаем команды OBD
    cmd_speed = obd.commands.SPEED
    cmd_rpm = obd.commands.RPM

    # Проверяем, поддерживаются ли эти команды конкретно нашим автомобилем (ЭБУ)
    if not connection.supports(cmd_speed) or not connection.supports(cmd_rpm):
        logging.warning("Внимание: Автомобиль может не поддерживать команды SPEED или RPM.")

    logging.info("Запуск мониторинга данных. Нажмите Ctrl+C для остановки.")
    
    try:
        while True:
            # Считываем скорость
            speed_response = connection.query(cmd_speed)
            # Считываем обороты двигателя
            rpm_response = connection.query(cmd_rpm)

            # Извлекаем значения (magnitude). Если ответ пустой (is_null), выводим "N/A"
            speed_val = speed_response.value.magnitude if not speed_response.is_null() else "N/A"
            rpm_val = rpm_response.value.magnitude if not rpm_response.is_null() else "N/A"

            # Форматированный вывод в консоль (с перезаписью текущей строки для красоты)
            sys.stdout.write(f"\r[Данные ЭБУ] Скорость: {speed_val} км/ч | Обороты: {rpm_val} об/мин    ")
            sys.stdout.flush()

            # Адекватная задержка (0.5 сек). ELM327 не любит, когда его спамят запросами без пауз
            time.sleep(0.5) 

    except KeyboardInterrupt:
        print() # Перенос строки после \r
        logging.info("Мониторинг остановлен пользователем (Ctrl+C).")
    except obd.OBDError as e:
        print()
        logging.error(f"Ошибка протокола OBD: {e}")
    except Exception as e:
        print()
        logging.error(f"Непредвиденная ошибка во время чтения данных: {e}")
    finally:
        # Безопасное закрытие соединения с портом
        connection.close()
        logging.info("Соединение с адаптером закрыто.")

def main():
    """
    Точка входа в приложение.
    """
    # Позволяем пользователю передать порт явно через аргумент командной строки (например, python app.py /dev/tty.OBD)
    port = sys.argv[1] if len(sys.argv) > 1 else None
    
    if not port:
        scan_ports()
        logging.info("Если автоподключение зависает, укажите порт вручную: python obd_monitor.py <ПОРТ>")
    
    connection = connect_to_adapter(port)
    
    if connection:
        monitor_data(connection)
    else:
        logging.error("Завершение работы из-за ошибки подключения.")

if __name__ == "__main__":
    main()
