"""Input handler for chat."""
import logging
import telepot
import enum
from squashbot.names import GAME_RESULTS
from fuzzywuzzy import process
from telepot.namedtuple import ReplyKeyboardMarkup, ReplyKeyboardRemove
from datetime import datetime
import pendulum
from squashbot.utils import previous_days, grouper, markdown_link, custom_xrange as time_range
from kortovnet import KortovNet
from telepot.exception import TelegramError
import gettext
import os

MSK = 'Europe/Moscow'
LOCALE = 'ru_RU'
CHAT_MEMBERS = ['left_chat_member', 'new_chat_member']


pendulum.set_locale('ru')
localedir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'locale')
translate = gettext.translation('squashbot', localedir, fallback=True)
_ = translate.gettext

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


class GameInputHandler(telepot.aio.helper.ChatHandler):
    """Class for handling chat input."""

    def __init__(self, *args, **kwargs):
        self._admin_chat = kwargs.pop('admin_chat', None)
        super(GameInputHandler, self).__init__(*args, **kwargs)
        self.players = None
        self.locations = None
        self.api = KortovNet()
        self.league = 1010
        self._stage = GameInputStage.start
        # TODO: Create game class
        self._location = None
        self._time = None
        self._player1 = None
        self._player2 = None
        self._result = None

    async def move_to(self, stage, keyboard=None):
        """Change state of chat to a specified stage."""
        self._stage = stage
        if self._stage == GameInputStage.location:
            if not self.locations:
                self.locations = {
                    p['title']: p['id']
                    for p in self.api.get_locations()
                }
            markup = ReplyKeyboardMarkup(
                keyboard=grouper(sorted(self.locations.keys()), 1)
            )
            await self.sender.sendMessage(
                _('Hi fellow squasher! Please choose the location of the game.'),
                reply_markup=markup
            )
        elif self._stage == GameInputStage.time:
            time_strs = []
            if self._time.is_today():
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
            else:
                period = self._time.end_of('day') - self._time
                time_strs = [
                    t.strftime('%H:%M')
                    for t in period.range('minutes', 30)
                ]
            markup = ReplyKeyboardMarkup(
                keyboard=grouper(
                    time_strs,
                    n=3
                )
            )
            await self.sender.sendMessage(
                _('You played on {date}.\nWhat time have the game ended?').format(
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
                 _("Courts are good at {}.\nWhen game is played? Let's start with date.").format(self._location),
                 reply_markup=ReplyKeyboardMarkup(keyboard=grouper(reversed(dates), 1))
            )
        elif self._stage == GameInputStage.first_player:
            if not self.players:
                self.players = {
                    "{} {}".format(p['last_name'], p['first_name']): p['id']
                    for p in self.api.get_players(self.league)
                }
            await self.sender.sendMessage(
                _("""Nice. The game is ended at {}.\nWho's the first player?""").format(
                    self._time.diff_for_humans()
                ),
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [p] for p in sorted(self.players.keys())
                 ])
            )
        elif self._stage == GameInputStage.second_player:
            await self.sender.sendMessage(
                _("""Well done. We like {}.\nWho was his mathup?""").format(self._player1),
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [p] for p, pid in sorted(self.players.items()) if p != self._player1
                 ])
            )
        elif self._stage == GameInputStage.result:
            await self.sender.sendMessage(
                _("""Well done.\nAnd the result of {} - {} is?""").format(self._player1, self._player2),
                reply_markup=ReplyKeyboardMarkup(keyboard=grouper(GAME_RESULTS, 3))
            )
        elif self._stage == GameInputStage.confirmation:
            await self.sender.sendMessage(
                _("""Let's check.\n{} {}\n{} - {} {}.""").format(
                    self._location,
                    self._time.format('%d.%m.%y %H:%M'),
                    self._player1,
                    self._player2,
                    self._result
                ),
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=grouper(['OK', '/back'], 1)
                )
            )

    async def is_authorized(self, user_id):
        """Check that user in the league group."""
        # TODO: add redis caching
        try:
            res = await self.bot.getChatMember(self._admin_chat, user_id)
        except TelegramError as ex:
            logging.exception(ex)
            return False
        return (res['status'] in ('creator', 'administrator', 'member')) or (res['status'] == 'left')

    async def on_chat_message(self, msg):
        """Handle chat message."""
        logging.debug(msg)
        content_type, chat_type, chat_id = telepot.glance(msg)

        logging.debug(content_type)

        if chat_type == 'group':
            if content_type not in CHAT_MEMBERS:
                await self.sender.sendMessage(_("Sorry, I work only in private chats."))
            return

        if content_type != 'text':
            if content_type not in CHAT_MEMBERS:
                await self.sender.sendMessage(_("Sorry, I don't understand only text."))
            return

        user_id = msg['from']['id']

        text = msg['text']

        if text[0] == '/':
            # hadling commands
            command = text.strip().lower()
            if command == '/newgame':
                is_authorized = await self.is_authorized(user_id)
                if is_authorized:
                    if self._stage == GameInputStage.start:
                            await self.move_to(GameInputStage.location)
                    else:
                        await self.sender.sendMessage(
                            _('You are already in process of entering the results!')
                        )
                else:
                    await self.sender.sendMessage(
                        _('Sorry, bro, but you are not a member of the league chat.')
                    )
            elif command == '/cancel':
                if self._stage == GameInputStage.start:
                    await self.sender.sendMessage(
                        _("Nothing to cancel. You don't even started")
                    )
                else:
                    self._stage = GameInputStage.start
                    await self.sender.sendMessage(
                        _("Ok. Full Reset! Start enter new game with /newgame")
                    )
            elif command == '/back':
                if self._stage != GameInputStage.start:
                    await self.move_to(GameInputStage(self._stage.value - 1))
                else:
                    await self.sender.sendMessage(
                        _("Oh, we can't go back darling. We've just started... Do you mean /cancel?")
                    )
        else:
            # Basic messages
            if self._stage == GameInputStage.location:
                text = text.strip()
                if text in self.locations:
                    self._location = text
                    await self.move_to(GameInputStage.date)
                else:
                    await self.sender.sendMessage(
                        _("""Sorry, I don't know about this place.
                        If this place is new, please contact administrators to add this court to our list.""")
                    )
            elif self._stage == GameInputStage.date:
                text = text.strip()
                try:
                    time = pendulum.from_format(text, "%d.%m.%y", MSK)
                except ValueError as ex:
                    await self.sender.sendMessage(
                        _("""Sorry, I cannot recognize the date. You can input custom date in 12.12.12 format""")
                    )
                else:
                    if time.is_future():
                        await self.sender.sendMessage(
                            _("""Looks like your game is in the future! No time travelers allowed!""")
                        )
                    else:
                        self._time = time
                        await self.move_to(GameInputStage.time)
            elif self._stage == GameInputStage.time:
                text = text.strip()
                try:
                    time = pendulum.from_format(text, "%H:%M", MSK)
                except ValueError as ex:
                    await self.sender.sendMessage(
                        _("""Sorry, I cannot recognize time. Please post something like 15:45 or 24.10.2016 13:20.""")
                    )
                else:
                    time = pendulum.combine(self._time, time.time()).timezone_(MSK)
                    if time.is_future():
                        await self.sender.sendMessage(
                            _("""Looks like your game is in the future! No time travelers allowed!""")
                        )
                    else:
                        self._time = time
                        await self.move_to(GameInputStage.first_player)
            elif self._stage == GameInputStage.first_player:
                text = text.strip()
                if text not in self.players:
                    ps = process.extract(text, self.players.keys(), limit=10)
                    await self.sender.sendMessage(
                        _("""I don't know that man!!! I suggested some names for you below"""),
                        reply_markup=ReplyKeyboardMarkup(keyboard=[
                            [p] for p, _ in ps if p != self._player1
                         ])
                    )
                else:
                    self._player1 = text
                    await self.move_to(GameInputStage.second_player)
            elif self._stage == GameInputStage.second_player:
                text = text.strip()
                if (text not in self.players) or (text == self._player1):
                    ps = process.extract(text, self.players.keys(), limit=10)
                    await self.sender.sendMessage(
                        _("""I don't know that man!!! I suggested some names for you below"""),
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
                        _("""Strange result! Try something look like 3:1.""")
                    )
                else:
                    self._result = text
                    await self.move_to(GameInputStage.confirmation)
            elif self._stage == GameInputStage.confirmation:
                text = text.strip().lower()
                if text != 'ok':
                    await self.sender.sendMessage(
                        _("""Please confirm the result!""")
                    )
                else:
                    await self.sender.sendMessage(
                        _("""Well done! We'll notify everyone about the game!\nEnter new game with /newgame."""),
                        reply_markup=ReplyKeyboardRemove()
                    )
                    from_data = msg['from']
                    name =\
                        "@{}".format(from_data['username']) if 'username' in from_data else from_data['first_name']
                    r1, r2 = [int(x) for x in self._result.split(':')]
                    data = dict(
                        lg=self.league,
                        p1=self.players[self._player1],
                        p2=self.players[self._player2],
                        r1=r1,
                        r2=r2,
                        loc=self.locations[self._location],
                        time=self._time.to_atom_string()
                    )
                    logging.debug(data)
                    result = self.api.publish_result(**data)
                    logging.debug(result)
                    await self.bot.sendMessage(
                        self._admin_chat,
                        "#result\n" +
                        _("""{} has just posted new results.\n{} {}\n{} - {}\n{}""").format(
                            name,
                            self._location,
                            self._time.format('%d.%m.%y, %H:%M'),
                            markdown_link(
                                title=self._player1,
                                url=self.api.link_for_player(self.league, self.players[self._player1])
                            ),
                            markdown_link(
                                title=self._player2,
                                url=self.api.link_for_player(self.league, self.players[self._player2])
                            ),
                            self._result
                        ),
                        parse_mode='Markdown'
                    )
                    self._stage = GameInputStage.start
