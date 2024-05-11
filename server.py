from modules.WebSocketImageServer import WebSocketImageServer
import asyncio
import os

if __name__ == "__main__":
    image_store_path = os.path.abspath("image_store")
    config_file_path = os.path.abspath("config.ini")
    asyncio.run(WebSocketImageServer.main(config_file_path, image_store_path))