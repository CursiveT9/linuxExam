import sys
sys.path.append('/app/proto')
from concurrent import futures
import grpc
import psycopg2
import pika
import json
from proto import service_pb2, service_pb2_grpc

DATABASE = {
    "dbname": "main_db",
    "user": "postgres",
    "password": "example",
    "host": "db",
    "port": 5432,
}


def get_db_connection():
    return psycopg2.connect(**DATABASE)


class SupplierService(service_pb2_grpc.SupplierServiceServicer):
    # GET suppliers (synchronous)
    def GetSuppliers(self, request, context):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM suppliers")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        suppliers = [service_pb2.Supplier(id=row[0], company_name=row[1], contact_person=row[2], phone=row[3]) for row
                     in rows]
        return service_pb2.SuppliersResponse(suppliers=suppliers)

    # CREATE supplier (asynchronous via RabbitMQ with gRPC binary)
    def create_supplier_from_message(self, message):
        grpc_request = service_pb2.CreateSupplierRequest.FromString(message)
        company_name = grpc_request.company_name
        contact_person = grpc_request.contact_person
        phone = grpc_request.phone

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO suppliers (company_name, contact_person, phone) VALUES (%s, %s, %s) RETURNING id",
                    (company_name, contact_person, phone))
        supplier_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        print(f"Supplier created: {supplier_id}")

    # UPDATE supplier (asynchronous via RabbitMQ with gRPC binary)
    def update_supplier_from_message(self, message):
        grpc_request = service_pb2.UpdateSupplierRequest.FromString(message)
        supplier_id = grpc_request.id
        company_name = grpc_request.company_name
        contact_person = grpc_request.contact_person
        phone = grpc_request.phone

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE suppliers SET company_name = %s, contact_person = %s, phone = %s WHERE id = %s",
                    (company_name, contact_person, phone, supplier_id))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Supplier updated: {supplier_id}")

    # DELETE supplier (asynchronous via RabbitMQ with gRPC binary)
    def delete_supplier_from_message(self, message):
        grpc_request = service_pb2.DeleteSupplierRequest.FromString(message)
        supplier_id = grpc_request.id

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM suppliers WHERE id = %s", (supplier_id,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Supplier deleted: {supplier_id}")


# RabbitMQ consumer function
def rabbitmq_consumer():
    connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
    channel = connection.channel()

    # Declare queues
    channel.queue_declare(queue='create_supplier')
    channel.queue_declare(queue='update_supplier')
    channel.queue_declare(queue='delete_supplier')

    def callback_create_supplier(ch, method, properties, body):
        print("Received Create Supplier gRPC message")
        SupplierService().create_supplier_from_message(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_update_supplier(ch, method, properties, body):
        print("Received Update Supplier gRPC message")
        SupplierService().update_supplier_from_message(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def callback_delete_supplier(ch, method, properties, body):
        print("Received Delete Supplier gRPC message")
        SupplierService().delete_supplier_from_message(body)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue='create_supplier', on_message_callback=callback_create_supplier)
    channel.basic_consume(queue='update_supplier', on_message_callback=callback_update_supplier)
    channel.basic_consume(queue='delete_supplier', on_message_callback=callback_delete_supplier)

    print('Waiting for messages...')
    channel.start_consuming()


def serve():
    # Start gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service_pb2_grpc.add_SupplierServiceServicer_to_server(SupplierService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()

    # Start RabbitMQ consumer in parallel
    rabbitmq_consumer()

    server.wait_for_termination()


if __name__ == '__main__':
    serve()
