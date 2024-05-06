import asyncio
import websockets
import random
from PIL import Image

PORT = 8765  # Same port as the server
SEND_SHORT_HEX = False  # Set to True to send short-form hex codes

class WebSocketImageClient:
    def __init__(self, port: int):
        self.port = port

    async def send_random_image(self):
        uri = f"ws://localhost:{self.port}"
        async with websockets.connect(uri) as websocket:
            await self.send_image_size(websocket, 100, 100, combine=True)
            for _ in range(100 * 100):
                color = self.generate_random_color()
                print(f"Sending color: {color}")
                await websocket.send(color)

    async def send_image_size(self, websocket, width: int, height: int, combine: bool):
        if combine:
            combined_width_height = self.get_combined_width_height_string(width, height)
            await websocket.send(combined_width_height)
            print(f"Sent combined width and height: {combined_width_height}")
        else:
            await websocket.send(str(width))
            print(f"Sent width: {width}")
            await websocket.send(str(height))
            print(f"Sent height: {height}")

    def generate_random_color(self) -> str:
        if SEND_SHORT_HEX:
            return f"#{random.randint(0, 15):X}{random.randint(0, 15):X}{random.randint(0, 15):X}"
        else:
            return f"#{random.randint(0, 255):02X}{random.randint(0, 255):02X}{random.randint(0, 255):02X}"

    def get_combined_width_height_string(self, width: int, height: int) -> str:
        return f"[{width}; {height}]"

    async def send_image_from_file(self, image_path: str):
        image = Image.open(image_path)
        width, height = image.size
        print(f"Image size: {width}x{height}")
        uri = f"ws://localhost:{self.port}"
        async with websockets.connect(uri) as websocket:
            await self.send_image_size(websocket, width, height, combine=True)
            pixels = list(image.getdata())
            for pixel in pixels:
                color = self.rgb_to_hex(pixel)
                print(f"Sending color: {color}")
                await websocket.send(color)

    def rgb_to_hex(self, rgb: tuple) -> str:
        if SEND_SHORT_HEX:
            return f"#{rgb[0] // 16:X}{rgb[1] // 16:X}{rgb[2] // 16:X}"
        else:
            return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

if __name__ == "__main__":
    client = WebSocketImageClient(PORT)
    # Use this line to send random colors
    # asyncio.run(client.send_random_image())

    # Use this line to send an image from a file
    asyncio.run(client.send_image_from_file("sampleimage.png"))
