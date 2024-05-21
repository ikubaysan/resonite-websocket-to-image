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

        self.app = Flask(__name__)
        # Endpoint will look like: http://localhost:5000/upload_image?width=100&height=100&room=1
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
                # If we have a current color, add it to the list
                if current_color:
                    colors.append(current_color)
                # Start a new color
                current_color = "#"
            else:
                # Add the character to the current color
                current_color += char

        if current_color:
            colors.append(current_color)

        erroneous_colors = [color for color in colors if len(color) not in [4, 7]]

        return colors

    def save_image(self, pixels: List[str], width: int, height: int, room_number: int) -> str:
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
                # TODO: This hits and it's basically bugged. Makes the picture much darker than it should be.
                # Got confirmation shortform on Resonite is bugged:
                # https://wiki.resonite.com/ProtoFlux:Color_To_Hex_Code#cite_note-1
                # "This is currently bugged and produces incorrect results"
                return tuple(int(hex_str[i] * 2, 16) for i in range(1, 4))
            else:
                # Full #RRGGBB format
                return tuple(int(hex_str[i:i + 2], 16) for i in range(1, 7, 2))
        except Exception as e:
            logging.error(f"Error converting hex string {hex_str} to RGB: {e}")
            return 0, 0, 0

    def upload_image(self):
        pixel_data = request.get_data(as_text=True)
        width = int(request.args.get('width'))
        height = int(request.args.get('height'))
        room_number = int(request.args.get('room', 0))

        pixels = self.parse_hex_colors(pixel_data)
        if len(pixels) == width * height:
            save_image_path = self.save_image(pixels, width, height, room_number)
            filename = os.path.basename(save_image_path)
            image_url = f"http://{self.domain}:{self.port}/images/room_{room_number}/{filename}"
            logging.info(f"Image uploaded successfully: {image_url}")
            return image_url, 200

        return jsonify({'error': f'Pixel data does not match the given dimensions of {width}x{height}. Received {len(pixels)} pixels, '
                                    f'expected {width * height}'}), 400

    def serve_image(self, filename):
        return send_from_directory(self.image_store_path, filename)

    def start_server(self):
        self.app.run(host=self.host, port=self.port)


if __name__ == '__main__':
    config_file_path = 'path_to_config.ini'
    image_store_path = 'path_to_image_store'
    server = FlaskImageServer(config_file_path, image_store_path)
    server.start_server()
