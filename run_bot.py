"""Script for starting bot in asyncio event loop."""
import sys
import os
import logging
import asyncio
import telepot
from telepot.aio.delegate import pave_event_space, per_chat_id, create_open
from squashbot.input import GameInputHandler


# logging settings
logging.basicConfig(
    format='%(asctime)s [%(filename)s:%(lineno)s:%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG
)

TOKEN = os.environ.get('TELEGRAM_TOKEN')  # telegram token
TIMEOUT = int(os.environ.get('BOT_TIMEOUT', 60))  # session timeout for bot

if not TOKEN:
    logging.critical("TELEGRAM_TOKEN not specified in environment variable.")
    sys.exit(-1)

logging.debug('Initializing bot.')

admin_chat = int(os.environ.get('ADMIN_CHAT'))
logging.debug("Posting admin messages to group chat #{}.".format(admin_chat))

bot = telepot.aio.DelegatorBot(TOKEN, [
    pave_event_space()(
        per_chat_id(),
        create_open,
        GameInputHandler,
        timeout=TIMEOUT,
        admin_chat=admin_chat
    ),
])

loop = asyncio.get_event_loop()
loop.create_task(bot.message_loop())

logging.debug('Listening ...')

try:
    loop.run_forever()
except KeyboardInterrupt:
    logging.debug('Stopping server begins.')
finally:
    loop.close()

logging.debug('Stopping server ends.')
