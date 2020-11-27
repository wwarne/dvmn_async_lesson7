import json
import logging
import trio
from trio_websocket import open_websocket_url

_BAD_MESSAGES = {
    'wrong msgType': {
                'msgType': 'notSoNewBound',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                }
    },
    'wrong east_lng': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': '37.65563964843751-string',
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                }
    },
    'wrong north_lat': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 'not-digit-55.77367652953477',
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                },
    },
    'wrong south_lat': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'south_lat': 'not-digit-55.72628839374007',
                    'west_lng': 37.54440307617188,
                },
    },
    'wrong west_lng': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                    'west_lng': 'not-digit-37.54440307617188',
                },
    },
    'empty message': {},
    'wrong structure': {'query': 'passwords'},
    'without msgType': {
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                },
    },
    'without data': {
                'msgType': 'newBounds',
    },
    'without data->east_lng': {
                'msgType': 'newBounds',
                'data': {
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                },
    },
    'without data->north_lat': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'south_lat': 55.72628839374007,
                    'west_lng': 37.54440307617188,
                },
    },
    'without data->south_lat': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'west_lng': 37.54440307617188,
                },
    },
    'without data->west_lng': {
                'msgType': 'newBounds',
                'data': {
                    'east_lng': 37.65563964843751,
                    'north_lat': 55.77367652953477,
                    'south_lat': 55.72628839374007,
                },
    }
}


async def main():
    try:
        async with open_websocket_url('ws://127.0.0.1:8000/ws') as ws:
            logging.info(f'Sending different bad messages to server')
            for desc, message in _BAD_MESSAGES.items():
                logging.info(f'Sending message "{desc}"')
                await ws.send_message(json.dumps(message, ensure_ascii=False))
                # note - server sends not only errors but buses positions too.
                # so if we just use ws.get_message() we will get just  'msgType': 'Buses' message
                with trio.move_on_after(2) as cancel_scope:
                    message = ''
                    while 'Errors' not in message:
                        message = await ws.get_message()
                    logging.info(f'Received answer: {message}')
                if cancel_scope.cancelled_caught:
                    logging.error('Server should returned error message but it didn\'t!')
    except OSError as ose:
        logging.error(f'Connection attempt failed: {ose}')

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s :: %(levelname)s :: %(message)s', level=logging.INFO)
    trio.run(main)