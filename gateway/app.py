import sys
sys.path.append('/app/proto')
from flask import Flask, jsonify, request
import grpc
import redis
import json
import pika
from prometheus_client import Counter, generate_latest
from proto import service_pb2, service_pb2_grpc

app = Flask(__name__)

# Redis client for caching
redis_client = redis.Redis(host="redis", port=6379)

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])


# Setup RabbitMQ connection
def send_to_rabbitmq(queue_name, message):
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name)
    channel.basic_publish(exchange='', routing_key=queue_name, body=message)
    connection.close()


# Route for creating a supplier (POST)
@app.route('/suppliers', methods=['POST'])
def create_supplier():
    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Prepare message to be sent to RabbitMQ for asynchronous processing
    message = json.dumps({
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })

    # Send to RabbitMQ queue for asynchronous processing
    send_to_rabbitmq('create_supplier', message)

    # Clear or update the cached suppliers to force the next GET request to fetch fresh data
    redis_client.delete('suppliers')  # Clear the cache

    # Return acknowledgment to client
    return jsonify({"message": "Supplier creation request accepted for processing"}), 202


# Route for updating a supplier (PUT)
@app.route('/suppliers/<int:id>', methods=['PUT'])
def update_supplier(id):
    data = request.get_json()
    company_name = data.get('company_name')
    contact_person = data.get('contact_person')
    phone = data.get('phone')

    # Prepare message to be sent to RabbitMQ for asynchronous processing
    message = json.dumps({
        "id": id,
        "company_name": company_name,
        "contact_person": contact_person,
        "phone": phone
    })

    # Send to RabbitMQ queue for asynchronous processing
    send_to_rabbitmq('update_supplier', message)

    # Clear the cached suppliers to force the next GET request to fetch fresh data
    redis_client.delete('suppliers')  # Clear the cache

    # Return acknowledgment to client
    return jsonify({"message": f"Supplier {id} update request accepted for processing"}), 202


# Route for deleting a supplier (DELETE)
@app.route('/suppliers/<int:id>', methods=['DELETE'])
def delete_supplier(id):
    # Prepare message to be sent to RabbitMQ for asynchronous processing
    message = json.dumps({"id": id})

    # Send to RabbitMQ queue for asynchronous processing
    send_to_rabbitmq('delete_supplier', message)

    # Clear the cached suppliers to force the next GET request to fetch fresh data
    redis_client.delete('suppliers')  # Clear the cache

    # Return acknowledgment to client
    return jsonify({"message": f"Supplier {id} delete request accepted for processing"}), 202


# Route for getting supplier data (GET)
@app.route('/suppliers', methods=['GET'])
def get_suppliers():
    REQUEST_COUNT.labels(method='GET', endpoint='/suppliers').inc()
    cached = redis_client.get('suppliers')

    if cached:
        return jsonify({"data": cached.decode('utf-8')})

    with grpc.insecure_channel("domain-service:50051") as channel:
        stub = service_pb2_grpc.SupplierServiceStub(channel)
        response = stub.GetSuppliers(service_pb2.Empty())
        suppliers = [{"id": s.id, "company_name": s.company_name} for s in response.suppliers]

        # Set a new cache with an expiration time (e.g., 60 seconds)
        redis_client.setex('suppliers', 60, str(suppliers))

        return jsonify({"data": suppliers})


# Metrics route for Prometheus
@app.route('/metrics', methods=['GET'])
def metrics():
    return generate_latest(), 200, {'Content-Type': 'text/plain'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
