import contextvars
import json
import logging
from datetime import datetime
from functools import partial

import click
import trio
from pydantic import BaseModel, ValidationError, validator
from trio_websocket import serve_websocket, ConnectionClosed, WebSocketConnection, WebSocketRequest

logging.basicConfig(format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger('bus_server')
serve_websocket_http = partial(serve_websocket, ssl_context=None)

BUSES_DATA = {}
window_boundaties = contextvars.ContextVar('window_boundaties')

class Bus(BaseModel):
    busId: str
    lat: float
    lng: float
    route: str

class WindowBound(BaseModel):
    north_lat: float
    south_lat: float
    west_lng: float
    east_lng: float

    def is_inside(self, lat: float, lng: float) -> bool:
        """Check if the point on a map is inside current bounds."""
        inside_lat = self.south_lat < lat < self.north_lat
        inside_lng = self.west_lng < lng < self.east_lng
        return inside_lat and inside_lng

    def is_bus_inside(self, bus: Bus) -> bool:
        """Check if a bus is visible to the user with current bounds."""
        return self.is_inside(lat=bus.lat, lng=bus.lng)

    def update(self, north_lat: float, south_lat: float, west_lng: float, east_lng: float) -> None:
        """Update bounds inplace."""
        self.north_lat = north_lat
        self.south_lat = south_lat
        self.west_lng = west_lng
        self.east_lng = east_lng


class BrowserWindowMessage(BaseModel):
    """Class for validation incoming data from user."""
    msgType: str
    data: WindowBound

    @validator('msgType', pre=True)
    def check_msg_type(cls, value: str) -> str:
        if value != 'newBounds':
            raise ValueError('Wrong message type')
        return value


@click.command()
@click.option('--verbose', '-v', count=True, help='Logging level (-v, -vv)')
@click.option('--host', help='Server address', default='127.0.0.1', show_default=True,)
@click.option('--bus_port', help='Receive data from bus emulator through this port', default=8080, show_default=True)
@click.option('--browser_port', help='Communicate with browser through this port', default=8000, show_default=True, envvar='BUS_PORT')
def load_and_run(browser_port, bus_port, host, verbose):
    log_level = {
        0: logging.WARNING,  # default
        1: logging.INFO,
        2: logging.DEBUG,
    }
    verbose = 2 if verbose > 2 else verbose
    logger.setLevel(level=log_level[verbose])
    logger.debug(f'Starting server with parameters: Browser port: {browser_port} Bus port: {bus_port} Host: {host} Verbose: {verbose}')
    trio.run(run_server, browser_port, bus_port, host)


async def run_server(browser_port: int, bus_port: int, host: str) -> None:
    """
    Start two websocket servers.

    One to communicate with users.
    Another one to receive data from bus emulator.
    """
    async with trio.open_nursery() as nursery:
        nursery.start_soon(serve_websocket_http, handle_bus, host, bus_port)
        nursery.start_soon(serve_websocket_http, handle_browser, host, browser_port)
        logger.info(f'Server has booted up at {datetime.utcnow()}')


def format_errors(e: ValidationError) -> dict:
    """Structure pydantic validation errors into a dict."""
    return {
        'msgType': 'Errors',
        'errors': [{
            'loc': err['loc'],
            'msg': err['msg'],
            'type': err['type'],
        } for err in e.errors()]
    }

async def handle_bus(request: WebSocketRequest) -> None:
    """
    Receives messages with buses locations updates and update in-memory buses storage.

    message example - '{"busId": "bus-0001", "lat": 55.03332, "lng": 35.4564, "route": "14k"}'
    """
    ws = await request.accept()
    logger.debug('grab_bus: Connection established')
    while True:
        try:
            message = await ws.get_message()
            try:
                bus = Bus.parse_raw(message)
            except ValidationError as e:
                logger.error(f'grab_bus: Bad bus message - {message}')
                error_dict = format_errors(e)
                await ws.send_message(json.dumps(error_dict))
            else:
                BUSES_DATA[bus.busId] = bus
        except ConnectionClosed:
            logger.debug('grab_bus: Connection closed')
            break

async def handle_browser(request: WebSocketRequest) -> None:
    """
    Handle incoming user connection.

    When user moves the map frontend sends map boundaries.
    User receives list of buses in his visible area.
    """
    ws = await request.accept()
    user_uri = request.remote.url
    logger.debug(f'handle_browser: Incoming user connection from {user_uri}')
    window_boundaties.set(WindowBound(north_lat=0, south_lat=0, west_lng=0, east_lng=0))
    async with trio.open_nursery() as nursery:
        nursery.start_soon(listen_to_browser, ws)
        nursery.start_soon(tell_to_browser, ws)
    logger.debug(f'handle_browser: User {user_uri} has disconnected.')


async def listen_to_browser(ws: WebSocketConnection) -> None:
    """
    Listen for an incoming websocket messages with new window boundaries.

    Message format is JSON:
    {
         "msgType": "newBounds",
         "data": {
               "east_lng": 37.65563964843751,
               "north_lat": 55.77367652953477,
               "south_lat": 55.72628839374007,
               "west_lng": 37.54440307617188,
         },
    }
    """
    while True:
        try:
            message = await ws.get_message()
            try:
                new_window = BrowserWindowMessage.parse_raw(message).data
            except ValidationError as e:
                logger.error(f'listen_browser: Bad newBounds message - {message}')
                error_dict = format_errors(e)
                await ws.send_message(json.dumps(error_dict))
            else:
                current_bounds = window_boundaties.get()
                current_bounds.update(
                    south_lat=new_window.south_lat,
                    north_lat=new_window.north_lat,
                    west_lng=new_window.west_lng,
                    east_lng=new_window.east_lng,
                )
                lat1 = new_window.north_lat - new_window.south_lat
                lng1 = new_window.west_lng - new_window.east_lng
                logger.debug(f'listen_browser: Window boundaries updated lat {lat1} lng {lng1}')
        except ConnectionClosed:
            logger.debug('listen_to_browser: Connection closed')
            break

async def tell_to_browser(ws: WebSocketConnection) -> None:
    """Sends visible buses to a user."""
    while True:
        bounds = window_boundaties.get()
        buses_inside = [
            bus.dict() for bus in BUSES_DATA.values() if bounds.is_bus_inside(bus)
        ]
        response_msg = {
            'msgType': 'Buses',
            'buses': buses_inside,
        }
        # logger.debug(f'tell_to_browser: {len(buses_inside)} inside bounds')
        try:
            await ws.send_message(json.dumps(response_msg, ensure_ascii=False))
        except ConnectionClosed:
            logger.debug('tell_to_browser: connection closed')
            break
        await trio.sleep(0.1)


if __name__ == '__main__':
    load_and_run(auto_envvar_prefix='BUS')
