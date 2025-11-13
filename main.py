from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
import urllib.parse
import mimetypes
import pathlib
import json
import logging
from datetime import datetime
from multiprocessing import Process
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import time

# Налаштування
BASE_DIR = pathlib.Path()
HTTP_HOST = '0.0.0.0'
HTTP_PORT = 3000
SOCKET_HOST = '0.0.0.0'
SOCKET_PORT = 5000
MONGO_URL = "mongodb://mongo:27017/"
DB_NAME = "web_project_db"
COLLECTION_NAME = "messages"

# HTTP сервер
class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pr_url = urllib.parse.urlparse(self.path)

        if pr_url.path == '/':
            self.send_html_file('index.html')
        elif pr_url.path == '/message':
            self.send_html_file('message.html')
        else:
            # Спроба знайти статичний файл
            file_path = BASE_DIR.joinpath(pr_url.path[1:])
            if file_path.exists():
                self.send_static_file(file_path)
            else:
                self.send_html_file('error.html', 404)

    def do_POST(self):
        # Обробка форми з message.html
        if self.path == '/message':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            # Відправляємо дані на Socket-сервер
            self.send_to_socket_server(post_data)

            # Редірект на головну сторінку
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.send_html_file('error.html', 404)

    def send_html_file(self, filename, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        try:    
            with open(filename, 'rb') as fd:
                self.wfile.write(fd.read())
        except FileNotFoundError:
            logging.error(f"HTML файл не знайдено: {filename}")
            self.wfile.write(b"<html><body><h1>File Not Found</h1></body></html>")

    def send_static_file(self, filepath, status=200):
        self.send_response(status)
        mt = mimetypes.guess_type(filepath)
        if mt:
            self.send_header("Content-type", mt[0])
        else:
            self.send_header("Content-type", 'text/plain')
        self.end_headers()
        try:
            with open(filepath, 'rb') as file:
                self.wfile.write(file.read())
        except FileNotFoundError:
            logging.error(f"Статичний файл не знайдено: {filepath}")
            self.wfile.write(b"File Not Found")

    def send_to_socket_server(self, data):
        # Використовуємо UDP сокет для відправки
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_socket.sendto(data, ('127.0.0.1', SOCKET_PORT))
        client_socket.close()


def run_http_server():
    logging.info(f"Запуск HTTP сервера на http://{HTTP_HOST}:{HTTP_PORT}")
    server_address = (HTTP_HOST, HTTP_PORT)
    http = HTTPServer(server_address, HttpHandler)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
        logging.info("HTTP сервер зупинено")

# Socket Сервер (UDP)
def run_socket_server():
    logging.info(f"Запуск Socket сервера на udp://{SOCKET_HOST}:{SOCKET_PORT}")

    client = None
    # Спроба підключитися до MongoDB з повторами
    max_retries = 10
    retry_delay = 5

    for i in range(max_retries):
        try:
            client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
            client.server_info() # Перевірка з'єднання
            logging.info("Socket сервер успішно підключився до MongoDB")
            break
        except ConnectionFailure:
            logging.warning(f"Не вдалося підключитися до MongoDB. Спроба {i+1}/{max_retries}. Повтор через {retry_delay} сек...")
            time.sleep(retry_delay)

    if not client:
        logging.error("Не вдалося підключитися до MongoDB після всіх спроб. Socket сервер зупиняється")
        return
    
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SOCKET_HOST, SOCKET_PORT))

    try:
        while True:
            data, addr = sock.recvfrom(1024)
            logging.info(f"Socket сервер отримав дані від {addr}")

            try:
                # Декодуємо байт-рядок
                data_str = data.decode('utf-8')

                # Парсимо URL-encoded рядок в словник
                data_dict = urllib.parse.parse_qs(data_str)

                # Готуємо документ для MongoDB
                # parse_qs повертає список значень, беремо перше [0]
                username = data_dict.get('username', [''])[0]
                message = data_dict.get('message', [''])[0]

                if username and message:
                    document = {
                        "date": datetime.now().isoformat(),
                        "username": username,
                        "message": message
                    }
                    
                    # Зберігаємо в MongoDB
                    collection.insert_one(document)
                    logging.info(f"Документ збережено в MongoDB: {document}")
                else:
                    logging.warning(f"Отримано пусті дані: username='{username}', message='{message}'")

            except Exception as e:
                logging.error(f"Помилка обробки даних у Socket сервері: {e}")

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        client.close()
        logging.info("Socket сервер зупинено")

# Головний запуск
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Запускаємо HTTP сервер в одному процесі
    http_process = Process(target=run_http_server, name="HttpServerProcess")
    http_process.start()

    # Запускаємо Socket сервер в іншому процесі
    socket_process = Process(target=run_socket_server, name="SocketServerProcess")
    socket_process.start()

    # Чекаємо на завершення процесів
    http_process.join()
    socket_process.join()