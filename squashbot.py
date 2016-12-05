import sys
import os
import logging
import asyncio
import telepot
import enum
from telepot.aio.delegate import pave_event_space, per_chat_id, create_open
from telepot.namedtuple import KeyboardButton, ReplyKeyboardMarkup, ForceReply


SQUASH_LOCATIONS = [
    'НСЦ',
    'Звезда',
    'Мультиспорт',
    'Soul Rebel',
    'Бережковская'
]

GAME_RESULTS = [
    '3:0', '3:1', '3:2',
    '0:3', '1:3', '2:3'
]

PLAYERS = [
    'MOHAMED ELSHORBAGY',
    'KARIM ABDEL GAWAD',
    'GREGORY GAULTIER',
    'NICK MATTHEW',
    'RAMY ASHOUR',
    'MARWAN ELSHORBAGY'
]

TIMES = ['{:02d}:{:02d}'.format(h, m) for h in range(16, 17) for m in range(0, 60, 10)]


GameInputStage = enum.Enum(
    value='GameInputStage',
    names=[
        'start',
        'time',
        'location',
        'first_player',
        'second_player',
        'result'
    ]
)

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


class GameInputHandler(telepot.aio.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        super(GameInputHandler, self).__init__(*args, **kwargs)
        self._stage = GameInputStage.start
        # TODO: Create game class
        self._location = None
        self._time = None
        self._player1 = None
        self._player2 = None
        self._result = None


    async def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)

        log.debug(msg)

        if content_type != 'text':
            await self.sender.sendMessage("Sorry, I don't understand.")

        text = msg['text']

        if text[0] == '/':
            # hadling commands
            command = text.strip().lower()
            if command == '/newgame':
                if self._stage == GameInputStage.start:
                    self._stage = GameInputStage.location

                    markup = ReplyKeyboardMarkup(keyboard=[
                         SQUASH_LOCATIONS[:3],
                         SQUASH_LOCATIONS[3:],
                     ])

                    await self.sender.sendMessage(
                        'Hi fellow squasher! Please choose the location of the game.',
                        reply_markup=markup,
                    )
                else:
                    await self.sender.sendMessage(
                        'You are already in process of entering the results!'
                    )
            elif command == '/cancel':
                if self._stage == GameInputStage.start:
                    await self.sender.sendMessage(
                        "Nothing to cancel. You don't even started"
                    )
                else:
                    self._stage = GameInputStage.start
                    await self.sender.sendMessage(
                        "Ok. Full Reset! Start enter new game with /newgame"
                    )
        else:
            # Basic messages
            if self._stage == GameInputStage.location:
                text = text.strip()
                if text in SQUASH_LOCATIONS:
                    self._location = text
                    self._stage = GameInputStage.time

                    markup = ReplyKeyboardMarkup(keyboard=[
                         TIMES[:3],
                         TIMES[3:],
                     ])

                    await self.sender.sendMessage(
                         'Courts are good at {}.\nWhat time have the game ended?'.format(text),
                         reply_markup=markup,
                    )
                else:
                    await self.sender.sendMessage(
                        """Sorry, I don't know about this place.
                        If this place is new, please contact administrators to add this court to our list."""
                    )
            elif self._stage == GameInputStage.time:
                text = text.strip()





TOKEN = os.environ.get('TELEGRAM_TOKEN')  # get token from enviroment variable

if not TOKEN:
    log.critical("TELEGRAM_TOKEN not specified in environment variable.")
    sys.exit(-1)

log.debug('Initializing bot.')

bot = telepot.aio.DelegatorBot(TOKEN, [
    pave_event_space()(
        per_chat_id(), create_open, GameInputHandler, timeout=20),
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
