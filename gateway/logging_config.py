import logging
from logstash_async.handler import AsynchronousLogstashHandler
from logstash_async.formatter import LogstashFormatter


def setup_logging():
    logger = logging.getLogger('python-logstash-logger')

    # Установить уровень логирования на DEBUG
    logger.setLevel(logging.DEBUG)

    # Настройка обработчика для отправки логов в Logstash через TCP
    logstash_handler = AsynchronousLogstashHandler(
        host='elk',
        port=5044,
        database_path=':memory:'  # Используем временную базу данных в памяти
    )

    # Форматирование логов в формат JSON, который Logstash может обработать
    logstash_handler.setFormatter(LogstashFormatter())

    # Добавляем обработчик
    logger.addHandler(logstash_handler)

    logger.info("Test message before sending to Logstash")
    print("Test message before sending to Logstash")

    return logger
