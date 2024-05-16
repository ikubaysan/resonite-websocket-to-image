import requests
import random
from PIL import Image
import configparser
import logging
import os
from typing import List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class RestImageClient:
    def __init__(self, config_file_path: str):
        self.config_file_path = config_file_path
        self.load_config()
        self.uri = f"http://{self.domain}:{self.port}/upload_image"

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.host: str = config['client']['host']
        self.domain: str = config['client']['domain']
        self.port: int = int(config['client']['port'])
        self.send_short_hex: bool = config['client'].getboolean('send_short_hex')
        self.send_pixels_by_row: bool = config['client'].getboolean('send_pixels_by_row')
        logging.info(f"Config loaded from {self.config_file_path}. "
                     f"Host: {self.host},"
                     f"Port: {self.port}, "
                     f"Send short hex: {self.send_short_hex}, "
                     f"Send pixels by row: {self.send_pixels_by_row}")

    def get_latest_images(self, room_id: int) -> str:
        response = requests.get(f"http://{self.domain}:{self.port}/images?room_id={room_id}")
        return response.text

    def send_random_image(self):
        logging.info(f"Sending random image to {self.uri}")
        width, height = 100, 100
        pixels = [self.generate_random_color() for _ in range(width * height)]
        pixel_data = ''.join([self.rgb_to_hex(rgb) for rgb in pixels])

        logging.info(f"Sending image to {self.uri}")

        response = requests.post(self.uri, json={
            'pixel_data': pixel_data
        }, params={'width': width, 'height': height, 'room': 1})

        if response.status_code == 200:
            logging.info(f"Image successfully uploaded: {response.json()['image_url']}")
        else:
            logging.error(f"Failed to upload image: {response.text}")

    def send_image_from_file(self, image_path: str):
        image_path = os.path.abspath(image_path)

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"send_image_from_file() - Image file not found: {image_path}")

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        logging.info(f"Image size: {width}x{height} ({width * height} pixels)")

        logging.info(f"Sending image from file {image_path} to {self.uri}")

        pixels = list(image.getdata())
        pixel_data = ''.join([self.rgb_to_hex(rgb) for rgb in pixels])

        logging.info(f"Sending image to {self.uri}")

        response = requests.post(self.uri, json={
            'pixel_data': pixel_data
        }, params={'width': width, 'height': height, 'room': 1})

        if response.status_code == 200:
            logging.info(f"Image successfully uploaded: {response.json()['image_url']}")
        else:
            logging.error(f"Failed to upload image: {response.text}")

    def generate_random_color(self) -> tuple:
        return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    def rgb_to_hex(self, rgb: tuple) -> str:
        if self.send_short_hex:
            return f"#{rgb[0] // 16:X}{rgb[1] // 16:X}{rgb[2] // 16:X}"
        else:
            return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


if __name__ == '__main__':
    config_file_path = 'path_to_config.ini'
    client = RestImageClient(config_file_path)
    client.send_random_image()
    # client.send_image_from_file('path_to_image_file.png')
