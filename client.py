from modules.WebSocketImageClient import WebSocketImageClient
from modules.RestImageClient import RestImageClient
import asyncio

async def main():
    #client = WebSocketImageClient(config_file_path="config.ini")
    #result = await client.send_random_image()
    #result = await client.send_image_from_file("sample_image.png")
    #result = await client.get_latest_images(room_id=1)
    #print("Latest Images URLs:", result)

    client = RestImageClient(config_file_path="config.ini")
    #client.send_random_image()
    client.send_image_from_file("sample_image.png")


if __name__ == "__main__":
    asyncio.run(main())
