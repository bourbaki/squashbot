import sys
import os
import logging
import asyncio
import telepot
from telepot.aio.delegate import pave_event_space, per_chat_id, create_open

class MessageCounter(telepot.aio.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        super(MessageCounter, self).__init__(*args, **kwargs)
        self._count = 0

    async def on_chat_message(self, msg):
        self._count += 1
        await self.sender.sendMessage(self._count)

log = logging.getLogger('app')
log.setLevel(logging.DEBUG)

f = logging.Formatter(
    '[L:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s',
    datefmt='%d-%m-%Y %H:%M:%S'
)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(f)
log.addHandler(ch)

TOKEN = os.environ.get('TELEGRAM_TOKEN')  # get token from enviroment variable

if not TOKEN:
    log.critical("TELEGRAM_TOKEN not specified in environment variable.")
    sys.exit(-1)

log.debug('Initializing bot.')

bot = telepot.aio.DelegatorBot(TOKEN, [
    pave_event_space()(
        per_chat_id(), create_open, MessageCounter, timeout=10),
])

loop = asyncio.get_event_loop()
loop.create_task(bot.message_loop())

log.debug('Listening ...')

try:
    loop.run_forever()
except KeyboardInterrupt:
    log.debug('Stopping server begins.')
finally:
    loop.close()

log.debug('Stopping server ends.')
