import json
import logging
import trio
from trio_websocket import open_websocket_url



async def main():
    try:
        async with open_websocket_url('ws://127.0.0.1:8000/ws') as ws:
            message = {
                "msgType": "newBoundss",
                "data": {
                    "east_lng": 37.65563964843751,
                    "north_lat": 55.77367652953477,
                    "south_lat": 55.72628839374007,
                    "west_lng": 37.54440307617188,
                },
            }
            await ws.send_message(json.dumps(message, ensure_ascii=False))
            for _ in range(5):
                message = await ws.get_message()
                if 'Errors' in message:
                    logging.error('Received message: %s', message)

    except OSError as ose:
        logging.error('Connection attempt failed: %s', ose)

if __name__ == '__main__':
    trio.run(main)