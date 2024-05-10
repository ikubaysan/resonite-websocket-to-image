from modules.WebSocketImageClient import WebSocketImageClient
import asyncio


if __name__ == "__main__":
    client = WebSocketImageClient(config_file_path="config.ini")
    # Use this line to send random colors
    # asyncio.run(client.send_random_image())

    # Use this line to send an image from a file
    asyncio.run(client.send_image_from_file("sample_image.png"))