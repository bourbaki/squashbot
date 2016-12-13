import sys
import os
import operator
import logging
import asyncio
import telepot
import enum
from names import PLAYERS, GAME_RESULTS, SQUASH_LOCATIONS
from fuzzywuzzy import process
from telepot.aio.delegate import pave_event_space, per_chat_id, create_open
from telepot.namedtuple import KeyboardButton, ReplyKeyboardMarkup, ForceReply, ReplyKeyboardRemove
from datetime import datetime, timedelta
import pendulum
from squashbot.utils import previous_days, grouper, custom_xrange as time_range

MSK = 'Europe/Moscow'
LOCALE = 'ru_RU'

GameInputStage = enum.Enum(
    value='GameInputStage',
    names=[
        'start',
        'date',
        'time',
        'location',
        'first_player',
        'second_player',
        'result',
        'confirmation'
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
        self._admin_chat = kwargs.pop('admin_chat', None)
        super(GameInputHandler, self).__init__(*args, **kwargs)
        self._stage = GameInputStage.start
        # TODO: Create game class
        self._location = None
        self._time = None
        self._player1 = None
        self._player2 = None
        self._result = None

    async def move_to(self, stage, keyboard=None):
        self._stage = stage
        if self._stage == GameInputStage.location:
            markup = ReplyKeyboardMarkup(keyboard=grouper(SQUASH_LOCATIONS, 3))
            await self.sender.sendMessage(
                'Hi fellow squasher! Please choose the location of the game.',
                reply_markup=markup
            )
        elif self._stage == GameInputStage.time:
            now = pendulum.now(tz=MSK)
            # truncate to 5 minutes
            now = now.replace(
                minute=now.minute - now.minute % 5
            )
            time_strs = [
                t.strftime('%H:%M')
                for t in time_range(
                    now.subtract(hours=2) - now,
                    unit='minutes',
                    step=10
                )
            ]
            markup = ReplyKeyboardMarkup(
                keyboard=grouper(
                    time_strs,
                    n=3
                )
            )
            await self.sender.sendMessage(
                'You played on {date}.\nWhat time have the game ended?'.format(
                    date=self._time.format('LL', formatter='alternative')
                ),
                reply_markup=markup
            )
        elif self._stage == GameInputStage.date:
            now = datetime.now()
            dates = [
                d.strftime('%d.%m.%y')
                for d in previous_days(n=90)
            ]
            await self.sender.sendMessage(
                 "Courts are good at {}.\nWhen game is played? Let's start with date.".format(self._location),
                 reply_markup=ReplyKeyboardMarkup(keyboard=grouper(reversed(dates), 1))
            )
        elif self._stage == GameInputStage.first_player:
            await self.sender.sendMessage(
                """Nice. The game is ended at {}.\nWho's the first player?""".format(
                    self._time.diff_for_humans()
                ),
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [p] for p in PLAYERS
                 ])
            )
        elif self._stage == GameInputStage.second_player:
            await self.sender.sendMessage(
                """Well done. We like {}.\nWho was his mathup?""".format(self._player1),
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [p] for p in PLAYERS if p != self._player1
                 ])
            )
        elif self._stage == GameInputStage.result:
            await self.sender.sendMessage(
                """Well done.\nAnd the result of {} - {} is?""".format(self._player1, self._player2),
                reply_markup=ReplyKeyboardMarkup(keyboard=grouper(GAME_RESULTS, 3))
            )
        elif self._stage == GameInputStage.confirmation:
            await self.sender.sendMessage(
                """Let's check.\n{} {}\n{} - {} {}.""".format(
                    self._location,
                    self._time.format('%d.%m.%y %H:%M'),
                    self._player1,
                    self._player2,
                    self._result
                ),
                reply_markup=ReplyKeyboardMarkup(keyboard=grouper(['OK', '/back'], 1))
            )


    async def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)

        log.debug(msg)

        if chat_type == 'group':
            await self.sender.sendMessage("Sorry, I work only in private...")
            return


        if content_type != 'text':
            await self.sender.sendMessage("Sorry, I don't understand.")

        text = msg['text']

        if text[0] == '/':
            # hadling commands
            command = text.strip().lower()
            if command == '/newgame':
                if self._stage == GameInputStage.start:
                    await self.move_to(GameInputStage.location)
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
            elif command == '/back':
                if self._stage != GameInputStage.start:
                    await self.move_to(GameInputStage(self._stage.value - 1))
                else:
                    await self.sender.sendMessage(
                        "Oh, we can't go back darling. We've just started... Do you mean /cancel?"
                    )
        else:
            # Basic messages
            if self._stage == GameInputStage.location:
                text = text.strip()
                if text in SQUASH_LOCATIONS:
                    self._location = text
                    await self.move_to(GameInputStage.date)
                else:
                    await self.sender.sendMessage(
                        """Sorry, I don't know about this place.
                        If this place is new, please contact administrators to add this court to our list."""
                    )
            elif self._stage == GameInputStage.date:
                text = text.strip()
                try:
                    self._time = pendulum.from_format(text, "%d.%m.%y", MSK)
                    log.debug(self._time)
                except ValueError as ex:
                    await self.sender.sendMessage(
                        """Sorry, I cannot recognize the date. You can input custom date in 12.12.12 format"""
                    )
                else:
                    await self.move_to(GameInputStage.time)
            elif self._stage == GameInputStage.time:
                text = text.strip()
                try:
                    time = pendulum.from_format(text, "%H:%M", MSK)
                    self._time = pendulum.combine(self._time, time.time())
                    log.debug(self._time)
                except ValueError as ex:
                    await self.sender.sendMessage(
                        """Sorry, I cannot recognize time. Please post something like 15:45 or 24.10.2016 13:20."""
                    )
                else:
                    await self.move_to(GameInputStage.first_player)
            elif self._stage == GameInputStage.first_player:
                text = text.strip()
                if text not in PLAYERS:
                    ps = process.extract(text, PLAYERS, limit=10)
                    await self.sender.sendMessage(
                        """I don't know that man!!! I suggested some names for you below""",
                        reply_markup=ReplyKeyboardMarkup(keyboard=[
                            [p] for p, _ in ps if p != self._player1
                         ])
                    )
                else:
                    self._player1 = text
                    await self.move_to(GameInputStage.second_player)
            elif self._stage == GameInputStage.second_player:
                text = text.strip()
                if (text not in PLAYERS) or (text == self._player1):
                    ps = process.extract(text, PLAYERS, limit=10)
                    await self.sender.sendMessage(
                        """I don't know that man!!! I suggested some names for you below""",
                        reply_markup=ReplyKeyboardMarkup(keyboard=[
                            [p] for p, _ in ps if p != self._player1
                         ])
                    )
                else:
                    self._player2 = text
                    await self.move_to(GameInputStage.result)
            elif self._stage == GameInputStage.result:
                text = text.strip()

                if (text not in GAME_RESULTS):
                    await self.sender.sendMessage(
                        """Strange result! Try something look like 3:1."""
                    )
                else:
                    self._result = text
                    await self.move_to(GameInputStage.confirmation)
            elif self._stage == GameInputStage.confirmation:
                text = text.strip().lower()
                if text != 'ok':
                    await self.sender.sendMessage(
                        """Please confirm the result!"""
                    )
                else:
                    await self.sender.sendMessage(
                        """Well done! We notify everyone about that game.!\nEnter new game with /newgame.""",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    from_data = msg['from']
                    name =\
                        "@{}".format(from_data['username']) if 'username' in from_data else from_data['first_name']
                    await self.bot.sendMessage(
                        self._admin_chat,
                        """#results\n{} has just posted new results.\n{} {}\n{} - {} {}.""".format(
                            name,
                            self._location,
                            self._time.format('%d.%m.%y, %H:%M'),
                            self._player1,
                            self._player2,
                            self._result
                        )
                    )
                    self._stage = GameInputStage.start


TOKEN = os.environ.get('TELEGRAM_TOKEN')  # get token from enviroment variable
TIMEOUT = int(os.environ.get('BOT_TIMEOUT', 60)) # session timeout for bot

if not TOKEN:
    log.critical("TELEGRAM_TOKEN not specified in environment variable.")
    sys.exit(-1)

log.debug('Initializing bot.')

admin_chat = int(os.environ.get('ADMIN_CHAT'))
log.debug("Posting admin messages to group chat #{}.".format(admin_chat))

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

log.debug('Listening ...')

try:
    loop.run_forever()
except KeyboardInterrupt:
    log.debug('Stopping server begins.')
finally:
    loop.close()

log.debug('Stopping server ends.')
