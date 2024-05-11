import websockets
import random
from PIL import Image
import configparser
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WebSocketImageClient:
    def __init__(self, config_file_path: str):
        self.config_file_path = config_file_path
        self.load_config()

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.host: str = config['client']['host']
        self.port: int = int(config['client']['port'])
        self.send_short_hex: bool = config['client'].getboolean('send_short_hex')
        self.send_pixels_by_row: bool = config['client'].getboolean('send_pixels_by_row')
        logging.info(f"Config loaded from {self.config_file_path}. "
                     f"Host: {self.host},"
                     f"Port: {self.port}, "
                     f"Send short hex: {self.send_short_hex}, "
                     f"Send pixels by row: {self.send_pixels_by_row}")

    async def send_random_image(self):
        uri = f"ws://{self.host}:{self.port}/ws"
        websocket_messages_sent = 0
        logging.info(f"Sending random image to {uri}")
        async with websockets.connect(uri) as websocket:
            await self.send_image_size(websocket, 100, 100, combine=True)
            if self.send_pixels_by_row:
                pixels = []
                for _ in range(100 * 100):
                    pixels.append(self.generate_random_color())
                websocket_messages_sent = await self.send_multiple_rows(websocket, pixels, 100, 100, rows_per_message=2)

            else:
                for _ in range(100 * 100):
                    color = self.generate_random_color()
                    logging.info(f"Sending color: {color}")
                    await websocket.send(color)
                    websocket_messages_sent += 1
        logging.info(f"Sent {websocket_messages_sent} messages")
        response = await websocket.recv()
        logging.info(f"Received from server: {response}")

    async def send_image_size(self, websocket, width: int, height: int, combine: bool):
        if combine:
            combined_width_height = self.get_combined_width_height_string(width, height)
            await websocket.send(combined_width_height)
            logging.info(f"Sent combined width and height: {combined_width_height}")
        else:
            await websocket.send(str(width))
            logging.info(f"Sent width: {width}")
            await websocket.send(str(height))
            logging.info(f"Sent height: {height}")

    def generate_random_color(self) -> tuple:
        """Return a color like the same format of image.getdata()"""
        return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

    @staticmethod
    def get_combined_width_height_string(width: int, height: int) -> str:
        return f"[{width}; {height}]"

    async def send_multiple_rows(self, websocket, pixels, width, height, rows_per_message=2):
        # Ensure rows_per_message is at least 1 and not greater than the image height
        rows_per_message = max(1, min(rows_per_message, height))
        websocket_messages_sent = 0

        # Iterate over each row in steps of rows_per_message
        for y in range(0, height, rows_per_message):
            combined_row_colors = ''

            # Process up to rows_per_message rows or whatever remains
            for delta in range(rows_per_message):
                current_row = y + delta
                if current_row >= height:  # Check if we've exceeded the image height
                    break

                row_start = current_row * width
                row_end = row_start + width
                row_colors = ''.join([self.rgb_to_hex(rgb) for rgb in pixels[row_start:row_end]])

                # Combine rows into a single string
                combined_row_colors += row_colors

            # Log and send the combined row colors
            logging.info(f"Sending combined row colors: {combined_row_colors}")
            await websocket.send(combined_row_colors)
            websocket_messages_sent += 1

        return websocket_messages_sent

    async def send_image_from_file(self, image_path: str):
        image_path = os.path.abspath(image_path)

        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"send_image_from_file() - Image file not found: {image_path}")

        image = Image.open(image_path).convert("RGB")
        width, height = image.size
        logging.info(f"Image size: {width}x{height} ({width * height} pixels)")
        uri = f"ws://{self.host}:{self.port}/ws"

        logging.info(f"Sending image from file {image_path} to {uri}")

        websocket_messages_sent = 0
        async with websockets.connect(uri) as websocket:
            await self.send_image_size(websocket, width, height, combine=True)
            pixels = list(image.getdata())

            if self.send_pixels_by_row:
                websocket_messages_sent = await self.send_multiple_rows(websocket, pixels, width, height,
                                                                        rows_per_message=2)
            else:
                for pixel in pixels:
                    color = self.rgb_to_hex(pixel)
                    logging.info(f"Sending color: {color}")
                    await websocket.send(color)
                    websocket_messages_sent += 1
        logging.info(f"Sent {websocket_messages_sent} messages")
        response = await websocket.recv()
        logging.info(f"Received from server: {response}")

    def rgb_to_hex(self, rgb: tuple) -> str:
        if self.send_short_hex:
            return f"#{rgb[0] // 16:X}{rgb[1] // 16:X}{rgb[2] // 16:X}"
        else:
            return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
