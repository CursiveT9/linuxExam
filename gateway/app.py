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

# Функция для отправки gRPC-бинарников в RabbitMQ
def send_grpc_to_rabbitmq(queue_name, grpc_message):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name)
    channel.basic_publish(exchange='', routing_key=queue_name, body=grpc_message)
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
    REQUEST_COUNT.labels(method='POST', endpoint='/suppliers').inc()

    data = request.get_json()
    grpc_message = service_pb2.CreateSupplierRequest(
        company_name=data.get('company_name'),
        contact_person=data.get('contact_person'),
        phone=data.get('phone')
    ).SerializeToString()

    send_grpc_to_rabbitmq('create_supplier', grpc_message)

    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "create_supplier",
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    redis_client.delete('suppliers')  # Очищаем кеш
    return jsonify({"message": "Запрос на создание поставщика принят в обработку"}), 202

# Маршрут для обновления поставщика (PUT)
@app.route('/suppliers/<int:id>', methods=['PUT'])
def update_supplier(id):
    REQUEST_COUNT.labels(method='PUT', endpoint='/suppliers').inc()

    data = request.get_json()
    grpc_message = service_pb2.UpdateSupplierRequest(
        id=id,
        company_name=data.get('company_name'),
        contact_person=data.get('contact_person'),
        phone=data.get('phone')
    ).SerializeToString()

    send_grpc_to_rabbitmq('update_supplier', grpc_message)

    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "update_supplier",
        "id": id,
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    redis_client.delete('suppliers')  # Очищаем кеш
    return jsonify({"message": f"Запрос на обновление поставщика {id} принят в обработку"}), 202

# Маршрут для удаления поставщика (DELETE)
@app.route('/suppliers/<int:id>', methods=['DELETE'])
def delete_supplier(id):
    REQUEST_COUNT.labels(method='DELETE', endpoint='/suppliers').inc()

    grpc_message = service_pb2.DeleteSupplierRequest(id=id).SerializeToString()
    send_grpc_to_rabbitmq('delete_supplier', grpc_message)

    # Отправляем в Logstash
    logstash_message = json.dumps({
        "event": "delete_supplier",
        "id": id
    })
    send_to_logstash(logstash_message)  # Отправляем сообщение в Logstash

    redis_client.delete('suppliers')  # Очищаем кеш
    return jsonify({"message": f"Запрос на удаление поставщика {id} принят в обработку"}), 202

# Маршрут для получения данных о поставщиках (GET)
@app.route('/suppliers', methods=['GET'])
def get_suppliers():
    REQUEST_COUNT.labels(method='GET', endpoint='/suppliers').inc()  # Добавляем инкремент для GET
    cached = redis_client.get('suppliers')

    if cached:
        # Логируем получение данных из кеша (выводим в консоль)
        print('Возвращаем данные из кеша поставщиков')
        return jsonify({"data": cached.decode('utf-8')})

    try:
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
    except Exception as e:
        print(f"Ошибка при получении данных о поставщиках: {e}")
        return jsonify({"error": "Ошибка сервера, не удалось получить данные о поставщиках"}), 500

# Маршрут для метрик Prometheus
@app.route('/metrics', methods=['GET'])
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
