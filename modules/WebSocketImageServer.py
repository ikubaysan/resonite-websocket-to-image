import asyncio
import os.path
import websockets
import datetime
from PIL import Image
import time
import configparser
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WebSocketImageServer:
    def __init__(self, config_file_path: str, image_store_path: str):
        self.config_file_path = os.path.abspath(config_file_path)
        self.image_store_path = os.path.abspath(image_store_path)

        logging.info(f"Config file path: {self.config_file_path}")
        logging.info(f"Image store path: {self.image_store_path}")

        self.load_config()

        self.width = 0
        self.height = 0
        self.latest_pixel_receipt_epoch = 0
        self.rows_received = 0
        self.pixels = []
        self.image_ready = False

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.port: int = int(config['server']['port'])
        self.expect_short_hex: bool = config['server'].getboolean('expect_short_hex')
        self.host: str = config['server']['host']
        self.print_received_messages: bool = config['server'].getboolean('print_received_messages')
        self.pixel_receipt_timeout_seconds: int = int(config['server']['pixel_receipt_timeout_seconds'])
        logging.info(f"Config loaded from {self.config_file_path}. Port: {self.port}, "
                     f"Host: {self.host}, "
                     f"Expect short hex: {self.expect_short_hex}, "
                     f"Print received messages: {self.print_received_messages}, "
                     f"Pixel receipt timeout seconds: {self.pixel_receipt_timeout_seconds}")


    async def handler(self, websocket, path):
        async for message in websocket:

            if self.print_received_messages:
                logging.info(message)

            # Reset condition based on time elapsed since the last pixel was received
            if len(self.pixels) > 1 and (time.time() - self.latest_pixel_receipt_epoch) > self.pixel_receipt_timeout_seconds:
                logging.info("Pixel receipt timeout. Resetting.")
                self.reset()

            if self.image_ready and not self.is_start_of_new_image(message):
                continue  # Ignore messages if an image has been formed and it's not a start of a new image

            if self.is_start_of_new_image(message):
                self.reset()  # Reset for new image when a new image is indicated by a start message

            if self.width == 0 or self.height == 0:
                logging.info(f"Received message when width or height is 0: {message}")
                if self.is_combined_dimensions(message):
                    dimensions = self.parse_combined_dimensions(message)
                    self.width, self.height = dimensions
                    logging.info(f"Received combined dimensions. Width: {self.width}, Height: {self.height}")
                    logging.info(f"Now expecting {self.width * self.height} pixels")
                elif self.width == 0:
                    self.width = int(message)
                elif self.height == 0:
                    self.height = int(message)
                    logging.info(f"Now expecting {self.width * self.height} pixels")
            elif len(message) != 7 and len(message) != 4:
                # Client sent a row of pixels
                self.latest_pixel_receipt_epoch = time.time()
                row_pixels = []

                i = 0
                while i < len(message):
                    if self.expect_short_hex:
                        row_pixels.append(message[i:i+5])
                        i += 4
                    else:
                        row_pixels.append(message[i:i+8])
                        i += 7

                self.pixels.extend(row_pixels)
                self.rows_received += 1
                logging.info(f"Received row of {len(row_pixels)} pixels. "
                             f"Total received pixels: {len(self.pixels)} Total rows received: {self.rows_received}")
                if len(self.pixels) == self.width * self.height:
                    self.save_image()
                    self.image_ready = True
            else:
                # Client sent a single pixel
                self.latest_pixel_receipt_epoch = time.time()
                self.pixels.append(message)
                if len(self.pixels) == self.width * self.height:
                    self.save_image()
                    self.image_ready = True

    def save_image(self):
        image = Image.new("RGB", (self.width, self.height))
        pixel_data = [self.hex_to_rgb(hex_color) for hex_color in self.pixels]
        image.putdata(pixel_data)
        filename = f"{int(time.time())}.png"

        # Save path will be self.image_store_path + filename
        save_image_path = os.path.abspath(os.path.join(self.image_store_path, filename))
        os.makedirs(self.image_store_path, exist_ok=True)

        image.save(save_image_path)
        logging.info(f"Image saved to {save_image_path} with {len(pixel_data)} pixels.")

    def reset(self):
        logging.info("Resetting server state for new image.")
        self.width = 0
        self.height = 0
        self.rows_received = 0
        self.pixels = []
        self.image_ready = False

    @staticmethod
    def hex_to_rgb(hex_str: str) -> tuple:
        if len(hex_str) == 4:  # Short-form like #FC0
            return tuple(int(hex_str[i]*2, 16) for i in range(1, 4))
        else:  # Regular form like #FFCC00
            return tuple(int(hex_str[i:i+2], 16) for i in range(1, 7, 2))

    @staticmethod
    def is_combined_dimensions(message: str) -> bool:
        return message.startswith('[') and ';' in message and message.endswith(']')

    @staticmethod
    def parse_combined_dimensions(message: str) -> tuple:
        # Assuming message format is "[width; height]"
        dimensions = message.strip('[]').split(';')
        return int(dimensions[0].strip()), int(dimensions[1].strip())

    @staticmethod
    def is_start_of_new_image(message: str) -> bool:
        # Consider it a start of a new image if it's a number or combined dimensions
        return message.isdigit() or (message.startswith('[') and ';' in message)

    async def start_server(self):
        server = await websockets.serve(self.handler, host=self.host, port=self.port)
        await server.wait_closed()
