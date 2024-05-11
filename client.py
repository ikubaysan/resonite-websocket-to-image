from modules.WebSocketImageClient import WebSocketImageClient
import asyncio

async def main():
    client = WebSocketImageClient(config_file_path="config.ini")
    # result = await client.send_random_image()
    # result = await client.send_image_from_file("sample_image.png")
    result = await client.get_latest_images(room_id=2)
    print("Latest Images URLs:", result)

if __name__ == "__main__":
    asyncio.run(main())
