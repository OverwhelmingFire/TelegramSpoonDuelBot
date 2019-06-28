import globals

class Peer:
    input_peer = None
    id = None
    name = ""
    pvp_mode_on = False  # cannot start a new Duel until it is False
    first_player = None
    second_player = None
    counter = 0  # count all spoons having been sent during the Duel by two players
    messages_with_spoon_ids = []  # contains the ids of all messages having been sent to the chat during the Duel; should be deleted!
    delete_immediately = False
    clear_after_duel = False
    tournament = False

    def __init__(self, _id):
        self.id = _id
        print("Created Peer 1")
    def __init__(self, _id, _name, _delete_immediately, _clear_after_duel):
        self.id = _id
        self.name = _name
        self.delete_immediately = _delete_immediately
        self.clear_after_duel
        print("Created Peer 2")
    def reset(self):
        self.pvp_mode_on=False
        self.tournament=False
        self.counter=0
        self.first_player=None
        self.second_player=None
        self.messages_with_spoon_ids=[]

class Player:
    id = 0
    name = ""
    kicked = 0
    tour = 0
    score = 0

    def __init__(self, _name, _id, _score, _kicked, _tour):
        self.id = _id
        self.name = _name
        self.kicked = _kicked
        self.tour = _tour
        self.score = _score


