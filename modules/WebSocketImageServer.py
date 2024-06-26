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
        self.pixel_receipt_start_epoch = 0
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
        self.max_images_per_room: int = int(config['server']['max_images_per_room'])

        logging.info(f"Config loaded from {self.config_file_path}. Port: {self.port}, "
                     f"Host: {self.host}, "
                     f"Domain: {self.domain}, "
                     f"Print received messages: {self.print_received_messages}, "
                     f"Pixel receipt timeout seconds: {self.pixel_receipt_timeout_seconds}, "
                     f"Max images per room: {self.max_images_per_room}")

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

    def get_latest_images(self, room_id: int) -> str:
        """
        Returns a comma-separated string of URLs for the latest <max_images_per_room> images for a given room.
        If the room folder does not exist or contains no images, returns an empty string.
        """
        room_folder_path = os.path.join(self.image_store_path, f"room_{room_id}")
        if not os.path.exists(room_folder_path):
            logging.info(f"No folder found for room {room_id}.")
            return ""

        # List all png files in the folder
        try:
            files = [f for f in os.listdir(room_folder_path) if f.endswith('.png')]
            # Sort files by modification time in descending order ([0] will be the newest file)
            # files.sort(reverse=True, key=lambda x: os.path.getmtime(os.path.join(room_folder_path, x)))

            # Sort files by modification time in ascending order ([0] will be the oldest file)
            files.sort(reverse=False, key=lambda x: os.path.getmtime(os.path.join(room_folder_path, x)))

            if not files:
                logging.info(f"No images found in the folder for room {room_id}.")
                return ""

            # If there are more than <self.max_images_per_room> files, delete the oldest ones, and then update the files list
            deletions = 0
            if len(files) > self.max_images_per_room:
                logging.info(f"More than {self.max_images_per_room} images found for room {room_id}. Deleting the oldest images.")
                for file in files[self.max_images_per_room:]:
                    os.remove(os.path.join(room_folder_path, file))
                    deletions += 1
                files = files[:self.max_images_per_room]
                logging.info(f"Deleted {deletions} oldest images for room {room_id}. "
                             f"There are now {self.max_images_per_room} images in the folder.")

            urls = [f"http://{self.domain}:{self.port}/images/room_{room_id}/{file}" for file in files if file.endswith('.png')]
            #urls_string = ', '.join(urls)
            urls_string = '|'.join(urls)
            logging.info(f"Latest images for room {room_id}: {urls_string}")
            return urls_string
        except Exception as e:
            logging.error(f"Error fetching images for room {room_id}: {str(e)}")
            return ""

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                message = msg.data

                if self.print_received_messages:
                    logging.info(message)


                if message.startswith("get_latest_images"):
                    # Get the latest images for a room
                    # Message must be in the format "get_latest_images <room_id>"
                    latest_images = self.get_latest_images(int(message.split()[-1]))
                    await ws.send_str(latest_images)
                    logging.info(f"Sent latest images to client: {latest_images}")
                    continue

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
                        self.pixel_receipt_start_epoch = time.time()
                    elif self.width == 0:
                        self.width = int(message)
                    elif self.height == 0:
                        self.height = int(message)
                        logging.info(f"Now expecting {self.width * self.height} pixels")
                        self.pixel_receipt_start_epoch = time.time()
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
                        message_to_send = f"http://{self.domain}:{self.port}/images/room_{self.room_number}/{filename}"
                        await ws.send_str(message_to_send)
                        logging.info(f"Sent message to client: {message_to_send}")
                        runtime_seconds = round(time.time() - self.pixel_receipt_start_epoch, 2)
                        logging.info(f"Total runtime for image creation: {runtime_seconds} seconds")
                else:
                    # Client sent a single pixel
                    self.latest_pixel_receipt_epoch = time.time()
                    self.pixels.append(message)
                    if len(self.pixels) == self.width * self.height:
                        save_image_path = self.save_image()
                        filename = os.path.basename(save_image_path)
                        message_to_send = f"http://{self.domain}:{self.port}/images/room_{self.room_number}/{filename}"
                        await ws.send_str(message_to_send)
                        logging.info(f"Sent message to client: {message_to_send}")
                        runtime_seconds = round(time.time() - self.pixel_receipt_start_epoch, 2)
                        logging.info(f"Total runtime for image creation: {runtime_seconds} seconds")

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

        logging.info(f"Server running on host: {self.host}:{self.port}")
        logging.info(f"Websocket server running on ws://{self.domain}:{self.port}/ws")
        logging.info(f"Images served from http://{self.domain}:{self.port}/images/room_<room_number>/")
        await asyncio.Event().wait()  # This will keep the server running indefinitely


    @staticmethod
    async def main(config_file_path: str, image_store_path: str):
        server = WebSocketImageServer(config_file_path, image_store_path)
        await server.start_server()
