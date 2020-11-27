import json
import logging
import trio
from trio_websocket import open_websocket_url

_BAD_MESSAGES = {
    'no bus id': {
                'lat': 50.50,
                'lng': 30.30,
                'route': '42-K',
    },
    'wrong lattitude': {
                'busId': 'good',
                'lat': 'not a digit',
                'lng': 30.30,
                'route': '42-K',
    },
    'wrong longitude': {
                'busId': 'good',
                'lat': 50.50,
                'lng': 'string in longitude',
                'route': '42-K',
    },
    'no route specified': {
                'busId': 'good',
                'lat': 50.50,
                'lng': 30.30,
    },
}

async def main():
    try:
        async with open_websocket_url('ws://127.0.0.1:8080/ws') as ws:
            logging.info(f'Sending different bad messages to server')
            for desc, message in _BAD_MESSAGES.items():
                logging.info(f'Sending message "{desc}"')
                await ws.send_message(json.dumps(message, ensure_ascii=False))
                message = await ws.get_message()
                logging.info(f'Received answer: {message}')
    except OSError as ose:
        logging.error(f'Connection attempt failed: {ose }')

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s :: %(levelname)s :: %(message)s', level=logging.INFO)
    trio.run(main)