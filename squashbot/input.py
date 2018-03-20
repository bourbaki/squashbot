"""Input handler for chat."""
import logging
import telepot
import enum
from squashbot.names import GAME_RESULTS
from fuzzywuzzy import process
from telepot.namedtuple import ReplyKeyboardMarkup, ReplyKeyboardRemove
from datetime import datetime
import pendulum
import redis
from squashbot.utils import previous_days, grouper, markdown_link, custom_xrange as time_range
from kortovnet import KortovNet
from telepot.exception import TelegramError
import gettext
import os

MSK = 'Europe/Moscow'
LOCALE = 'ru_RU'
CHAT_MEMBERS = ['left_chat_member', 'new_chat_member']
TOP_LOCS=3
TOP_PLAYERS=3

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
        self.api = KortovNet(token=os.getenv('LIGA_TOKEN'))
        self.redis = redis.StrictRedis.from_url(os.getenv("REDIS_URL"))
        self.league = os.getenv('LEAGUE_ID')
        self._stage = GameInputStage.start
        # TODO: Create game class
        self._location = None
        self._time = None
        self._player1 = None
        self._player2 = None
        self._result = None


    def top_locations_for_user(self, user_id):
        return [
            "🔥" + x.decode()
            for x in self.redis.zrevrange("loc:{}".format(user_id), 0, TOP_LOCS)
        ]

    def top_players_for_user(self, user_id):
        return [
            x.decode()
            for x in self.redis.zrevrange("ps:{}".format(user_id), 0, TOP_PLAYERS)
        ]

    def get_location_keyboard_for_user(self, user_id):
        top = self.top_locations_for_user(user_id)
        names = None
        
        if len(top) == 0:
            names = sorted(self.locations.keys())
        else:
            names = top + sorted([k for k in self.locations.keys() if k not in top])
        
        return ReplyKeyboardMarkup(
            keyboard=grouper(names, 1),
            one_time_keyboard=True
        )

    def get_players_keyboard_for_user(self, user_id, exclude=set()):
        top = [p for p in self.top_players_for_user(user_id) if (p in self.players)]
        names = None
        if len(top) == 0:
            names = sorted(self.players.keys())
        else:
            names = ["🔥" + x for x in top] + sorted([k for k in self.players.keys() if k not in top])

        
        return ReplyKeyboardMarkup(
            keyboard=[[p] for p in names if p.replace("🔥", "") not in exclude],
            one_time_keyboard=True
        )
        
        
        

    async def move_to(self, stage, keyboard=None, user_id=None):
        """Change state of chat to a specified stage."""
        self._stage = stage
        if self._stage == GameInputStage.location:
            if not self.locations:
                self.locations = {
                    p['title']: p['id']
                    for p in self.api.get_locations()
                }
            markup = self.get_location_keyboard_for_user(user_id)
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
                ),
                one_time_keyboard=True
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
                    "{} {}".format(p['last_name'].strip(), p['first_name'].strip()): p['id']
                    for p in self.api.get_players(self.league)
                }
            print("Here", self.top_players_for_user(user_id))
            await self.sender.sendMessage(
                _("""Nice. The game is ended at {}.\nWho's the first player?""").format(
                    self._time.diff_for_humans()
                ),
                reply_markup=self.get_players_keyboard_for_user(user_id)
            )
        elif self._stage == GameInputStage.second_player:
            await self.sender.sendMessage(
                _("""Well done. We like {}.\nWho was his mathup?""").format(self._player1),
                reply_markup=self.get_players_keyboard_for_user(
                    user_id,
                    exclude=[self._player1]
                )
            )
        elif self._stage == GameInputStage.result:
            await self.sender.sendMessage(
                _("""Well done.\nAnd the result of {} - {} is?""").format(self._player1, self._player2),
                reply_markup=ReplyKeyboardMarkup(keyboard=grouper(GAME_RESULTS, 3), one_time_keyboard=True)
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
                    keyboard=grouper(['OK', '/back'], 1),
                    one_time_keyboard=True
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

        if chat_type != 'private':
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
                            await self.move_to(GameInputStage.location, user_id=user_id)
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
                text = text.strip().replace("🔥", "")
                if text in self.locations:
                    self._location = text
                    self.redis.zadd("loc:{}".format(user_id), 1, text)
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
                        await self.move_to(GameInputStage.first_player, user_id=user_id)
            elif self._stage == GameInputStage.first_player:
                text = text.strip().replace("🔥", "")
                if text not in self.players:
                    ps = process.extract(text, self.players.keys(), limit=10)
                    await self.sender.sendMessage(
                        _("""I don't know that man!!! I suggested some names for you below"""),
                        reply_markup=ReplyKeyboardMarkup(keyboard=[
                            [p] for p, _ in ps if p != self._player1
                         ], one_time_keyboard=True)
                    )
                else:
                    self._player1 = text
                    self.redis.zadd("ps:{}".format(user_id), 1, text)
                    await self.move_to(GameInputStage.second_player, user_id=user_id)
            elif self._stage == GameInputStage.second_player:
                text = text.strip().replace("🔥", "")
                if (text not in self.players) or (text == self._player1):
                    ps = process.extract(text, self.players.keys(), limit=10)
                    await self.sender.sendMessage(
                        _("""I don't know that man!!! I suggested some names for you below"""),
                        reply_markup=ReplyKeyboardMarkup(keyboard=[
                            [p] for p, _ in ps if p != self._player1
                         ], one_time_keyboard=True)
                    )
                else:
                    self._player2 = text
                    self.redis.zadd("ps:{}".format(user_id), 1, text)
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
                        _("""{p1} - {p2}\n{result} {loc} {time}\n#result by {author}""").format(
                            author=name.replace('_', '\_'),
                            loc=self._location,
                            time=self._time.format('%d/%m %H:%M'),
                            p1=markdown_link(
                                title=self._player1,
                                url=self.api.link_for_player(self.league, self.players[self._player1])
                            ),
                            p2=markdown_link(
                                title=self._player2,
                                url=self.api.link_for_player(self.league, self.players[self._player2])
                            ),
                            result=self._result
                        ),
                        parse_mode='Markdown'
                    )
                    self._stage = GameInputStage.start
