from textual.message import Message


class SportDataUpdate(Message):
    """Posted by DataManager when fresh sport data is ready."""
    def __init__(self, sport: str, groups: dict, rows: list):
        super().__init__()
        self.sport  = sport
        self.groups = groups
        self.rows   = rows