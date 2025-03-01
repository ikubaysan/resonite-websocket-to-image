import asyncio
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image
import os
import time
import configparser
import logging
import websockets
from typing import List, Tuple, Union
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class FlaskImageServer:
    def __init__(self, config_file_path: str, image_store_path: str):
        self.config_file_path = os.path.abspath(config_file_path)
        self.image_store_path = os.path.abspath(image_store_path)

        logging.info(f"Config file path: {self.config_file_path}")
        logging.info(f"Image store path: {self.image_store_path}")

        self.load_config()

        self.app = Flask(__name__)
        self.app.add_url_rule('/upload_image', 'upload_image', self.upload_image_endpoint, methods=['POST'])
        self.app.add_url_rule('/images/<path:filename>', 'serve_image', self.serve_image)
        self.app.add_url_rule('/latest_images', 'get_latest_images', self.get_latest_images_endpoint)

        self.websocket_clients = set()
        self.websocket_server = None

    def get_latest_images(self, room_id: int, num_images: int) -> str:
        room_folder_path = os.path.join(self.image_store_path, f"room_{room_id}")
        if not os.path.exists(room_folder_path):
            return jsonify({'error': f'Room {room_id} does not exist'}), 404

        files = [f for f in os.listdir(room_folder_path) if f.endswith('.png')]

        # Sort by creation time, oldest first
        files.sort(key=lambda x: os.path.getctime(os.path.join(room_folder_path, x)), reverse=False)

        # Get the last num_images files
        latest_images = [f"http://{self.domain}:{self.rest_api_port}/images/room_{room_id}/{file}" for file in files[-num_images:]]

        while len(latest_images) < num_images:
            latest_images.insert(0, "")

        return '|'.join(latest_images)

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.rest_api_port: int = int(config['server']['rest_api_port'])
        self.websocket_port: int = int(config['server']['websocket_port'])
        self.host: str = config['server']['host']
        self.domain: str = config['server']['domain']
        self.print_received_messages: bool = config['server'].getboolean('print_received_messages')
        self.pixel_receipt_timeout_seconds: int = int(config['server']['pixel_receipt_timeout_seconds'])
        self.max_images_per_room: int = int(config['server']['max_images_per_room'])

        logging.info(f"Config loaded from {self.config_file_path}. REST API Port: {self.rest_api_port}, "
                     f"WebSocket Port: {self.websocket_port}, Host: {self.host}, "
                     f"Domain: {self.domain}, "
                     f"Print received messages: {self.print_received_messages}, "
                     f"Pixel receipt timeout seconds: {self.pixel_receipt_timeout_seconds}, "
                     f"Max images per room: {self.max_images_per_room}")

    def parse_hex_colors(self, input_string: str) -> List[str]:
        colors = []
        current_color = ""
        is_first_char = True

        for char in input_string:
            if char == '#':
                if current_color != "":
                    colors.append(current_color)
                current_color = "#"
            elif char == "|":
                if is_first_char:
                    current_color = "#000000"
                colors.append(current_color)
            else:
                current_color += char

            if is_first_char:
                is_first_char = False

        if current_color:
            colors.append(current_color)

        return colors

    def save_image(self, pixels: List[str], width: int, height: int, room_number: int, notify_clients: bool) -> str:
        image = Image.new("RGB", (width, height))
        pixel_data = [self.hex_to_rgb(hex_color) for hex_color in pixels]
        image.putdata(pixel_data)
        filename = f"{int(time.time())}.png"

        save_image_path = os.path.abspath(os.path.join(self.image_store_path, f"room_{room_number}", filename))
        os.makedirs(os.path.dirname(save_image_path), exist_ok=True)
        logging.info(f"Saving image to {save_image_path}")
        image.save(save_image_path)
        logging.info(f"{width}x{height} image with {len(pixel_data)} pixels saved to {save_image_path}")

        self.cleanup_old_images(room_number)

        if notify_clients:
            loop = asyncio.get_running_loop()
            loop.create_task(self.notify_clients(room_number))

        return save_image_path

    def cleanup_old_images(self, room_number: int):
        room_folder_path = os.path.join(self.image_store_path, f"room_{room_number}")
        if not os.path.exists(room_folder_path):
            return

        files = [f for f in os.listdir(room_folder_path) if f.endswith('.png')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(room_folder_path, x)))

        if len(files) > self.max_images_per_room:
            files_to_delete = files[:-self.max_images_per_room]
            for file in files_to_delete:
                os.remove(os.path.join(room_folder_path, file))
                logging.info(f"Deleted old image: {file}")

    def hex_to_rgb(self, hex_str: str) -> Tuple[int, int, int]:
        try:
            if len(hex_str) == 4:  # #RGB format
                return tuple(int(hex_str[i] * 2, 16) for i in range(1, 4))
            elif len(hex_str) == 5:  # #RGBA format, ignore the alpha
                return tuple(int(hex_str[i] * 2, 16) for i in range(1, 4))
            else:
                return tuple(int(hex_str[i:i + 2], 16) for i in range(1, 7, 2))
        except Exception as e:
            logging.error(f"Error converting hex string {hex_str} to RGB: {e}")
            return 0, 0, 0

    def upload_image(self, pixel_data: str, width: int, height: int, room_number: int, notify_clients: bool) -> Union[str, Tuple[dict, int]]:
        pixels = self.parse_hex_colors(pixel_data)
        if len(pixels) == width * height:
            save_image_path = self.save_image(pixels, width, height, room_number, notify_clients)
            filename = os.path.basename(save_image_path)
            image_url = f"http://{self.domain}:{self.rest_api_port}/images/room_{room_number}/{filename}"
            logging.info(f"Image uploaded successfully: {image_url}")
            return image_url

        error_str = f'Pixel data does not match the given dimensions of {width}x{height}. Received {len(pixels)} pixels, expected {width * height}'
        logging.error(error_str)
        return {'error': error_str}, 400

    def upload_image_endpoint(self):
        pixel_data = request.get_data(as_text=True)
        width = int(request.args.get('width'))
        height = int(request.args.get('height'))
        room_number = int(request.args.get('room', 0))
        response = self.upload_image(pixel_data, width, height, room_number, notify_clients=False)
        if isinstance(response, str):
            return response, 200
        else:
            return jsonify(response), 400

    def serve_image(self, filename):
        return send_from_directory(self.image_store_path, filename)

    def get_latest_images_endpoint(self):
        try:
            num_images = int(request.args.get('num_images', 10))
            room_id = int(request.args.get('room_id', 0))
            response = self.get_latest_images(room_id, num_images)
            return response, 200
        except Exception as e:
            logging.error(f"Error getting latest images: {e}")
            return jsonify({'error': f'Error getting latest images: {e}'}), 400

    async def websocket_handler(self, websocket):
        self.websocket_clients.add(websocket)
        logging.info(f"New WebSocket connection: {websocket.remote_address}")
        try:
            async for message in websocket:
                await self.handle_websocket_message(websocket, message)
        finally:
            self.websocket_clients.remove(websocket)
            logging.info(f"WebSocket connection closed: {websocket.remote_address}")

    async def handle_websocket_message(self, websocket, message):
        try:
            if message.startswith("upload_image"):
                # Example message: "upload_image?width=100&height=100&room=1, body=#FF0000#00FF00#0000FF"
                params, body = message.split(", body=", 1)
                logging.info(f"Received upload_image websocket message from client {websocket.remote_address} with params: {params}")
                query_params = dict(param.split('=') for param in params.split('?')[1].split('&'))
                width = int(query_params.get('width'))
                height = int(query_params.get('height'))
                room_id = int(query_params.get('room_id', 0))
                response = self.upload_image(body, width, height, room_id, notify_clients=True)
                if isinstance(response, str):
                    await websocket.send("upload_image_response=" + response)
                else:
                    await websocket.send(json.dumps(response))
            elif message.startswith("latest_images"):
                # Example message: "latest_images?room_id=1&num_images=10"
                params = message.split('?')[1]
                logging.info(f"Received latest_images websocket message from client {websocket.remote_address} with params: {params}")
                room_id = int(params.split('&')[0].split('=')[1])
                num_images = int(params.split('&')[1].split('=')[1])
                response = self.get_latest_images(room_id, num_images)
                await websocket.send("latest_images_response=" + response)
        except Exception as e:
            logging.error(f"Error handling WebSocket message: {e}")
            try:
                await websocket.send(f"Error handling WebSocket message: {e}")
            except Exception as e:
                logging.error(f"Error sending error message to WebSocket client: {e}")

    async def notify_clients(self, room_number: int):
        if self.websocket_clients:
            message = str(room_number)
            logging.info(f"Sending WebSocket message: {message}")
            await asyncio.gather(*[client.send(message) for client in self.websocket_clients])

    def start_rest_api_server(self):
        self.app.run(host=self.host, port=self.rest_api_port)

    async def start_websocket_server(self):
        # Set max_size and read limit for a message to 1MB
        self.websocket_server = await websockets.serve(handler=self.websocket_handler,
                                                       host=self.host,
                                                       port=self.websocket_port,
                                                       max_size=1048576 * 4,
                                                       write_limit=1048576 * 4)
        logging.info(f"WebSocket server started at ws://{self.host}:{self.websocket_port}")
        await self.websocket_server.wait_closed()

    async def start_servers(self):
        await asyncio.gather(
            asyncio.to_thread(self.start_rest_api_server),
            self.start_websocket_server()
        )


if __name__ == '__main__':
    config_file_path = 'path_to_config.ini'
    image_store_path = 'path_to_image_store'
    server = FlaskImageServer(config_file_path, image_store_path)
    asyncio.run(server.start_servers())
