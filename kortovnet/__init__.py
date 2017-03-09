"""Kortov.net API implementation."""
import requests as reqs


class KortovNet(object):
    """docstring for KortovNet."""

    def __init__(self, host="http://msliga.ru/api/v0"):
        """Init."""
        super(KortovNet, self).__init__()
        self.host = host

    def link_for_player(self, league, player):
        """Generate link for players page in the league."""
        return "http://msliga.ru/competitors/{}/leagues/{}/".format(player, league)

    def get_leagues(self):
        """Return list of active leagues."""
        return reqs.get("{host}/leagues/".format(
            host=self.host,
        )).json()

    def get_players(self, league_id):
        """Return active player list for specified league."""
        return reqs.get("{host}/leagues/{league_id}/players/".format(
            host=self.host,
            league_id=league_id
        )).json()

    def get_locations(self):
        """Return list of available locations."""
        return reqs.get("{host}/locations/".format(
            host=self.host,
        )).json()

    def publish_result(self, lg, p1, p2, r1, r2, loc, time):
        """Publish game result to the league."""
        url = "{host}/games/".format(
            host=self.host
        )
        return reqs.post(
            url,
            json=dict(
                player1=p1,
                player2=p2,
                result1=r1,
                result2=r2,
                location=loc,
                league=lg,
                end_datetime=time
            )
        ).json()
