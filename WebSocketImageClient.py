import asyncio
import websockets
import random

PORT = 8765  # Same port as the server
SEND_SHORT_HEX = True  # Set to True to send short-form hex codes

class WebSocketImageClient:
    def __init__(self, port: int):
        self.port = port
        self.width = 100
        self.height = 100

    async def send_random_image(self):
        uri = f"ws://localhost:{self.port}"
        async with websockets.connect(uri) as websocket:
            await websocket.send(str(self.width))
            print(f"Sent width: {self.width}")
            await websocket.send(str(self.height))
            print(f"Sent height: {self.height}")
            for _ in range(self.width * self.height):
                if SEND_SHORT_HEX:
                    color = f"#{random.randint(0, 15):X}{random.randint(0, 15):X}{random.randint(0, 15):X}"
                else:
                    color = f"#{random.randint(0, 255):02X}{random.randint(0, 255):02X}{random.randint(0, 255):02X}"
                print(f"Sending color: {color}")
                await websocket.send(color)

if __name__ == "__main__":
    client = WebSocketImageClient(PORT)
    asyncio.run(client.send_random_image())
