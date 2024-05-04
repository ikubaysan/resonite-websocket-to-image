import asyncio
import websockets
import datetime
from PIL import Image
import time

PORT = 8765  # Specify the WebSocket server port
EXPECT_SHORT_HEX = False  # Set to True if expecting short-form hex codes, else False

class WebSocketImageServer:
    def __init__(self, port: int):
        self.port = port
        self.width = 0
        self.height = 0
        self.pixels = []
        self.image_ready = False

    async def handler(self, websocket, path):
        async for message in websocket:
            if self.image_ready:
                continue  # Ignore messages if an image has already been formed

            if self.width == 0 or self.height == 0:
                print(f"Received message when width or height is 0: {message}")
                if self.is_combined_dimensions(message):
                    dimensions = self.parse_combined_dimensions(message)
                    self.width, self.height = dimensions
                    print(f"Received combined dimensions. Width: {self.width}, Height: {self.height}")
                    print(f"Now expecting {self.width * self.height} pixels")
                elif self.width == 0:
                    self.width = int(message)
                elif self.height == 0:
                    self.height = int(message)
                    print(f"Now expecting {self.width * self.height} pixels")
            else:
                self.pixels.append(message)
                if len(self.pixels) == self.width * self.height:
                    self.save_image()
                    self.image_ready = True

    def save_image(self):
        image = Image.new("RGB", (self.width, self.height))
        pixel_data = [self.hex_to_rgb(hex_color) for hex_color in self.pixels]
        image.putdata(pixel_data)
        filename = f"{int(time.time())}.png"
        image.save(filename)
        print(f"Image saved as {filename}")
        self.reset()

    def reset(self):
        self.width = 0
        self.height = 0
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

    async def start_server(self):
        server = await websockets.serve(self.handler, "localhost", self.port)
        await server.wait_closed()

if __name__ == "__main__":
    server = WebSocketImageServer(PORT)
    asyncio.run(server.start_server())
