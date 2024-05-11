import asyncio
import os.path
import websockets
import aiohttp
from aiohttp import web
import datetime
from PIL import Image
import time
import configparser
import logging
import time
from typing import List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# Only log warnings and errors from aiohttp
logging.getLogger('aiohttp').setLevel(logging.WARNING)

class WebSocketImageServer:
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
        self.chunks_received = 0
        self.pixels = []
        self.image_ready = False

    def load_config(self):
        config = configparser.ConfigParser()
        config.read(self.config_file_path)
        self.port: int = int(config['server']['port'])
        self.host: str = config['server']['host']
        self.domain: str = config['server']['domain']
        self.print_received_messages: bool = config['server'].getboolean('print_received_messages')
        self.pixel_receipt_timeout_seconds: int = int(config['server']['pixel_receipt_timeout_seconds'])
        logging.info(f"Config loaded from {self.config_file_path}. Port: {self.port}, "
                     f"Host: {self.host}, "
                     f"Domain: {self.domain}, "
                     f"Print received messages: {self.print_received_messages}, "
                     f"Pixel receipt timeout seconds: {self.pixel_receipt_timeout_seconds}")

    @staticmethod
    def parse_hex_colors(input_string) -> List[str]:
        # Initialize an empty list to store color codes
        colors = []

        # Temporary string to accumulate characters of a color code
        current_color = ""

        # Iterate over each character in the string
        for char in input_string:
            # If the character is '#', it indicates the start of a new color code
            if char == '#':
                # If there is already a color code being built, add it to the list
                if current_color:
                    colors.append(current_color)
                # Start a new color code
                current_color = "#"
            else:
                # Continue building the current color code
                current_color += char

        # Add the last color code to the list, if any
        if current_color:
            colors.append(current_color)

        return colors


    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                message = msg.data

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
                elif message in ['1', '2', '3,', '4']:
                    self.room_number = int(message)
                    logging.info(f"This image will be uploaded for room number {self.room_number}")
                elif len(message) != 7 and len(message) != 4:
                    # Client sent a row of pixels
                    self.latest_pixel_receipt_epoch = time.time()
                    row_pixels = self.parse_hex_colors(message)

                    self.pixels.extend(row_pixels)
                    self.chunks_received += 1
                    logging.info(f"Received chunk of {len(row_pixels)} pixels. "
                                 f"Total received pixels: {len(self.pixels)} Total chunks received: {self.chunks_received}")
                    if len(self.pixels) == self.width * self.height:
                        save_image_path = self.save_image()
                        filename = os.path.basename(save_image_path)
                        await ws.send_str(f"http://{self.domain}:{self.port}/images/room_{self.room_number}/{filename}")
                else:
                    # Client sent a single pixel
                    self.latest_pixel_receipt_epoch = time.time()
                    self.pixels.append(message)
                    if len(self.pixels) == self.width * self.height:
                        save_image_path = self.save_image()
                        filename = os.path.basename(save_image_path)
                        await ws.send_str(f"http://{self.domain}:{self.port}/images/room_{self.room_number}/{filename}")

    def save_image(self):
        image = Image.new("RGB", (self.width, self.height))
        pixel_data = [self.hex_to_rgb(hex_color) for hex_color in self.pixels]
        image.putdata(pixel_data)
        filename = f"{int(time.time())}.png"

        # Save path will be self.image_store_path + filename
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
        # Consider this message a start of a new image if:
        # 1. A '#' is not in the message
        # 2. It's a number or combined dimensions (meaning it contains '[' and ';')
        return '#' not in message and (message.isnumeric() or (message.startswith('[') and ';' in message))

    async def start_server(self):
        app = web.Application()
        app.router.add_route('GET', '/ws', self.websocket_handler)

        # Updated to serve images from a specific path and potentially allow directory listing
        static_route_path = '/images'  # Change the URL path to /images
        app.router.add_static(static_route_path, self.image_store_path,
                              show_index=True)  # show_index allows directory listing

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()

        logging.info(f"Server running on {self.host}:{self.port}")
        await asyncio.Event().wait()  # This will keep the server running indefinitely


    @staticmethod
    async def main(config_file_path: str, image_store_path: str):
        server = WebSocketImageServer(config_file_path, image_store_path)
        await server.start_server()
