from flask import Flask, request, jsonify, send_from_directory
from PIL import Image
import os
import time
import configparser
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class FlaskImageServer:
    def __init__(self, config_file_path: str, image_store_path: str):
        self.config_file_path = os.path.abspath(config_file_path)
        self.image_store_path = os.path.abspath(image_store_path)

        logging.info(f"Config file path: {self.config_file_path}")
        logging.info(f"Image store path: {self.image_store_path}")

        self.load_config()

        self.width = 0
        self.height = 0
        self.room_number = 1
        self.latest_pixel_receipt_epoch = 0
        self.pixel_receipt_start_epoch = 0
        self.chunks_received = 0
        self.pixels = []
        self.image_ready = False

        self.app = Flask(__name__)
        self.app.add_url_rule('/upload_image', 'upload_image', self.upload_image, methods=['POST'])
        self.app.add_url_rule('/images/<path:filename>', 'serve_image', self.serve_image)

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.port: int = int(config['server']['port'])
        self.host: str = config['server']['host']
        self.domain: str = config['server']['domain']
        self.print_received_messages: bool = config['server'].getboolean('print_received_messages')
        self.pixel_receipt_timeout_seconds: int = int(config['server']['pixel_receipt_timeout_seconds'])
        self.max_images_per_room: int = int(config['server']['max_images_per_room'])

        logging.info(f"Config loaded from {self.config_file_path}. Port: {self.port}, "
                     f"Host: {self.host}, "
                     f"Domain: {self.domain}, "
                     f"Print received messages: {self.print_received_messages}, "
                     f"Pixel receipt timeout seconds: {self.pixel_receipt_timeout_seconds}, "
                     f"Max images per room: {self.max_images_per_room}")

    def parse_hex_colors(self, input_string: str) -> List[str]:
        colors = []
        current_color = ""

        for char in input_string:
            if char == '#':
                if current_color:
                    colors.append(current_color)
                current_color = "#"
            else:
                current_color += char

        if current_color:
            colors.append(current_color)

        return colors

    def save_image(self) -> str:
        image = Image.new("RGB", (self.width, self.height))
        pixel_data = [self.hex_to_rgb(hex_color) for hex_color in self.pixels]
        image.putdata(pixel_data)
        filename = f"{int(time.time())}.png"

        save_image_path = os.path.abspath(os.path.join(self.image_store_path, f"room_{self.room_number}", filename))
        os.makedirs(os.path.dirname(save_image_path), exist_ok=True)
        logging.info(f"Saving image to {save_image_path}")
        image.save(save_image_path)
        logging.info(f"Image saved to {save_image_path} with {len(pixel_data)} pixels.")
        self.image_ready = True
        return save_image_path

    def reset(self):
        logging.info("Resetting server state for new image.")
        self.width = 0
        self.height = 0
        self.chunks_received = 0
        self.room_number = 1
        self.pixels = []
        self.image_ready = False

    def hex_to_rgb(self, hex_str: str) -> Tuple[int, int, int]:
        if len(hex_str) == 4:
            return tuple(int(hex_str[i] * 2, 16) for i in range(1, 4))
        else:
            return tuple(int(hex_str[i:i + 2], 16) for i in range(1, 7, 2))

    def upload_image(self):
        data = request.get_json()
        pixel_data = data.get('pixel_data')
        self.width = int(request.args.get('width'))
        self.height = int(request.args.get('height'))
        self.room_number = int(request.args.get('room', 1))

        self.pixels = self.parse_hex_colors(pixel_data)
        if len(self.pixels) == self.width * self.height:
            save_image_path = self.save_image()
            filename = os.path.basename(save_image_path)
            image_url = f"http://{self.domain}:{self.port}/images/room_{self.room_number}/{filename}"
            response = {'image_url': image_url}
            logging.info(f"Image uploaded successfully: {image_url}")
            return jsonify(response), 200

        return jsonify({'error': 'Pixel data does not match the given dimensions'}), 400

    def serve_image(self, filename):
        return send_from_directory(self.image_store_path, filename)

    def start_server(self):
        self.app.run(host=self.host, port=self.port)


if __name__ == '__main__':
    config_file_path = 'path_to_config.ini'
    image_store_path = 'path_to_image_store'
    server = FlaskImageServer(config_file_path, image_store_path)
    server.start_server()
