import globals

class Peer:
    input_peer = None
    time_when_duel_started=None
    id = None
    name = ""
    pvp_mode_on = False
    first_player = None
    second_player = None
    counter = 0
    messages_with_spoon_ids = []
    delete_immediately = False
    clear_after_duel = False
    tournament = False

    def __init__(self, _id, _name, _delete_immediately, _clear_after_duel):
        self.id = _id
        self.name = _name
        self.delete_immediately = _delete_immediately
        self.clear_after_duel

    def reset(self):
        self.pvp_mode_on=False
        self.tournament=False
        self.counter=0
        self.first_player=None
        self.second_player=None
        self.time_when_duel_started=None