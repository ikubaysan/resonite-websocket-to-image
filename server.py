from modules.WebSocketImageServer import WebSocketImageServer
import asyncio

if __name__ == "__main__":
    server = WebSocketImageServer(config_file_path="config.ini")
    asyncio.run(server.start_server())