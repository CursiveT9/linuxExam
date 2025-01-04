import sys
sys.path.append('/app/proto')
from flask import Flask, jsonify, request
import grpc
import redis
import json
import pika
import socket  # Добавляем импорт socket
from prometheus_client import Counter, generate_latest
from proto import service_pb2, service_pb2_grpc
# Убрали импорт logging_config

app = Flask(__name__)

# Клиент Redis для кеширования
redis_client = redis.Redis(host="redis", port=6379)

# Метрики для Prometheus
REQUEST_COUNT = Counter('http_requests_total', 'Общее количество HTTP-запросов', ['method', 'endpoint'])

# Функция для отправки сообщений в RabbitMQ
def send_to_rabbitmq(queue_name, message):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name)
    channel.basic_publish(exchange='', routing_key=queue_name, body=message)
    connection.close()

# Функция отправки сообщений в Logstash
def send_to_logstash(message):
    host = 'logstash'  # Имя контейнера Logstash
    port = 5044
    try:
        # Создаём TCP-сокет и подключаемся к Logstash
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(message.encode('utf-8'))
            print(f"Сообщение отправлено на {host}:{port}")
    except Exception as e:
        # Обработка ошибок
        print(f"Ошибка при отправке сообщения в Logstash: {e}")

# Маршрут для создания поставщика (POST)
@app.route('/suppliers', methods=['POST'])
def create_supplier():
    REQUEST_COUNT.labels(method='POST', endpoint='/suppliers').inc()  # Добавляем инкремент для POST

    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Логируем запрос (выводим в консоль)
    print(f"Получен запрос на создание поставщика: {company_name}, {contact_person}, {phone}")

    # Подготавливаем сообщение для отправки в RabbitMQ для асинхронной обработки
    message = json.dumps({
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })

    # Отправляем в очередь RabbitMQ для асинхронной обработки
    send_to_rabbitmq('create_supplier', message)

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "create_supplier",
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    # Очищаем или обновляем кеш поставщиков, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('suppliers')  # Очищаем кеш

    # Логируем успешное завершение (выводим в консоль)
    print(f"Запрос на создание поставщика принят в обработку: {company_name}")

    # Отправляем подтверждение клиенту
    return jsonify({"message": "Запрос на создание поставщика принят в обработку"}), 202

# Маршрут для обновления поставщика (PUT)
@app.route('/suppliers/<int:id>', methods=['PUT'])
def update_supplier(id):
    REQUEST_COUNT.labels(method='PUT', endpoint='/suppliers').inc()  # Добавляем инкремент для PUT

    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Логируем запрос (выводим в консоль)
    print(f"Получен запрос на обновление поставщика {id}: {company_name}, {contact_person}, {phone}")

    # Подготавливаем сообщение для отправки в RabbitMQ для асинхронной обработки
    message = json.dumps({
        "id": id,
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })

    # Отправляем в очередь RabbitMQ для асинхронной обработки
    send_to_rabbitmq('update_supplier', message)

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "update_supplier",
        "id": id,
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    # Очищаем кеш поставщиков, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('suppliers')  # Очищаем кеш

    # Логируем успешное завершение (выводим в консоль)
    print(f"Запрос на обновление поставщика {id} принят в обработку")

    # Отправляем подтверждение клиенту
    return jsonify({"message": f"Запрос на обновление поставщика {id} принят в обработку"}), 202

# Маршрут для удаления поставщика (DELETE)
@app.route('/suppliers/<int:id>', methods=['DELETE'])
def delete_supplier(id):
    REQUEST_COUNT.labels(method='DELETE', endpoint='/suppliers').inc()  # Добавляем инкремент для DELETE

    # Логируем запрос (выводим в консоль)
    print(f"Получен запрос на удаление поставщика {id}")

    # Подготавливаем сообщение для отправки в RabbitMQ для асинхронной обработки
    message = json.dumps({"id": id})

    # Отправляем в очередь RabbitMQ для асинхронной обработки
    send_to_rabbitmq('delete_supplier', message)

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "delete_supplier",
        "id": id
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    # Очищаем кеш поставщиков, чтобы следующий GET-запрос получил актуальные данные
    redis_client.delete('suppliers')  # Очищаем кеш

    # Логируем успешное завершение (выводим в консоль)
    print(f"Запрос на удаление поставщика {id} принят в обработку")

    # Отправляем подтверждение клиенту
    return jsonify({"message": f"Запрос на удаление поставщика {id} принят в обработку"}), 202

# Маршрут для получения данных о поставщиках (GET)
@app.route('/suppliers', methods=['GET'])
def get_suppliers():
    REQUEST_COUNT.labels(method='GET', endpoint='/suppliers').inc() # Добавляем инкремент для GET
    cached = redis_client.get('suppliers')

    if cached:
        # Логируем получение данных из кеша (выводим в консоль)
        print('Возвращаем данные из кеша поставщиков')
        return jsonify({"data": cached.decode('utf-8')})

    with grpc.insecure_channel("domain-service:50051") as channel:
        stub = service_pb2_grpc.SupplierServiceStub(channel)
        response = stub.GetSuppliers(service_pb2.Empty())
        suppliers = [{"id": s.id, "company_name": s.company_name} for s in response.suppliers]

        # Устанавливаем новый кеш с временем жизни (например, 60 секунд)
        redis_client.setex('suppliers', 60, str(suppliers))

        # Логируем успешное получение данных (выводим в консоль)
        print('Получены данные о поставщиках из сервисов домена')

        # Отправляем в Logstash сообщение о том, что данные получены из сервиса
        logstash_message = json.dumps({
            "event": "get_suppliers",
            "status": "fetched_from_service",
            "data": suppliers
        })
        send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

        return jsonify({"data": suppliers})

# Маршрут для метрик Prometheus
@app.route('/metrics', methods=['GET'])
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
