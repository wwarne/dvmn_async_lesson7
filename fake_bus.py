import json
import logging
import pathlib
import random
import sys
from functools import wraps
from itertools import cycle
from typing import Callable, List, Optional, Union

import click
import trio
from trio_websocket import ConnectionClosed, HandshakeError, open_websocket_url

logging.basicConfig(format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger('fake_bus')


@click.command()
@click.option('-v', '--verbose', count=True, help='Logging level (-v, -vv)')
@click.option('--refresh_timeout', '-t', type=int, default=1, help='Delay between coordinates switch.')
@click.option('--emulator_id', '-e', type=str, default='', help='busId prefix in case few bus emulators will run in parallel')
@click.option('--websockets_number', '-w', type=int, default=5, help='Number of opened websocket connections.')
@click.option('--buses_per_route', '-x', type=int, default=1, help='Number of buses on each route.')
@click.option('--routes_number', '-r', type=int, help='Number of routes (If not set all avail. routes will be used).')
@click.option('--server', default='ws://127.0.0.1:8080/ws', help='Server address.')
def bus_faker(server, routes_number, buses_per_route, websockets_number, emulator_id, refresh_timeout, verbose):
    """Check arguments and runs bus emulator."""
    log_level = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    verbose = 2 if verbose > 2 else verbose
    logger.setLevel(level=log_level[verbose])
    max_routes = sum(1 for _ in pathlib.Path('routes').glob('*.json'))
    if not routes_number:
        logger.warning(f'Number of routes is not set - using all possbile routes - {max_routes} routes.')
        routes_number = max_routes
    if routes_number > max_routes:
        logger.error(f'We have information only about {max_routes} different routes. You have specified {routes_number} routes.')
        sys.exit()
    trio.run(main, server, routes_number, buses_per_route, websockets_number, emulator_id, refresh_timeout)


async def main(server_url: str,
               routes_number: int,
               buses_per_route: int,
               websockets_number: int,
               emulator_id: str,
               refresh_timeout: Union[int, float],
               ) -> None:
    """Entrypoint to run all async machinery."""
    send_channels = []
    async with trio.open_nursery() as nursery:
        logger.info(f'Open {websockets_number} channels.')
        for _ in range(websockets_number):
            snd_channel, rcv_channel = trio.open_memory_channel(0)
            send_channels.append(snd_channel)
            nursery.start_soon(send_bus_updates, server_url, rcv_channel)  # consumer
        logger.info(f'Start emulating {routes_number} buses.')
        channel_choice = cycle(send_channels)
        for route in load_routes(max_routes=routes_number):
            for bus_num in range(buses_per_route):
                start_offset = random.randint(0, len(route['coordinates']) - 1)
                bus_id = generate_bus_id(route_id=route['name'], bus_index=bus_num, prefix=emulator_id)
                bus_send_channel = next(channel_choice)
                nursery.start_soon(run_bus,
                                   bus_send_channel,
                                   bus_id,
                                   route['name'],
                                   route['coordinates'],
                                   start_offset,
                                   refresh_timeout,
                                   )
        logger.warning('Booted up. Sending fake data')

def generate_bus_id(route_id: str, bus_index: int, prefix=''):
    return f'{prefix}{route_id}-{bus_index}'

def load_routes(directory_path: str = 'routes', max_routes: Optional[int] = None):
    dir_path = pathlib.Path(directory_path)
    for file_num, route_file in enumerate(dir_path.glob('*.json'), start=1):
        if max_routes and file_num > max_routes:
            break
        yield json.loads(route_file.read_text())


def relaunch_on_disconnect(delay: Union[int, float]) -> Callable:
    def deco(a_func):
        @wraps(a_func)
        async def wrapped(*args, **kwargs):
            while True:
                try:
                    await a_func(*args, **kwargs)
                except ConnectionClosed as cc:
                    reason = '<no reason>' if cc.reason.reason is None else f'"{cc.reason.reason}"'
                    logger.error(f'Websocket closed: {cc.reason.code}/{cc.reason.name} {reason}')
                    await trio.sleep(delay)
                except HandshakeError as he:
                    logger.error(f'Websocket connection attempt failed {he}')
                    await trio.sleep(delay)
        return wrapped
    return deco


@relaunch_on_disconnect(delay=1)
async def send_bus_updates(server_address: str,
                           receive_channel: trio.MemoryReceiveChannel) -> None:
    """Consume updates from trio channel and send them to a server via websockets."""
    async with open_websocket_url(server_address) as ws:
        logger.debug(f'Established connection with {server_address}')
        async for message in receive_channel:
            await ws.send_message(json.dumps(message, ensure_ascii=False))


async def run_bus(bus_channel: trio.MemorySendChannel,
                  bus_id: str,
                  route_name: str,
                  route: List[List[float]],
                  start_offset: int,
                  refresh_timeout: Union[float, int],
                  ) -> None:
    """
    Run bus through its route.

    :param bus_channel: Trio channel to send coordinate updates
    :param bus_id: Unique bus id
    :param route_name: Name of bus route (on one route can be many buses)
    :param route: A list of coordinates on a route.
    :param start_offset: Start bus from point with this index on a route
    :param refresh_timeout: Pause between coordinate updates
    """
    async with bus_channel:
        while True:
            for lat, lng in route[start_offset:]:
                message = {
                    'busId': bus_id,
                    'lat': lat,
                    'lng': lng,
                    'route': route_name,
                }
                try:
                    await bus_channel.send(message)
                except trio.BrokenResourceError:
                    logger.error('run_bus: Bus coordinates consumer has closed. No point of sending them.')
                    return
                await trio.sleep(refresh_timeout)
            start_offset = 0  # After reaching the end of route the bus starts from the beginning.


if __name__ == '__main__':
    bus_faker(auto_envvar_prefix='FAKE')
