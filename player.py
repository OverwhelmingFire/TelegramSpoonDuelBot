import globals

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


