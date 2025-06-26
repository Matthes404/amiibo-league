from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Amiibo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    current_elo = db.Column(db.Integer, default=1500)
    peak_elo = db.Column(db.Integer, default=1500)
    league = db.Column(db.String(20), default="")
    ko_titles = db.Column(db.String(120), default="")
    waiting = db.Column(db.Boolean, default=False)
    profile_pic = db.Column(db.String(120), default="")

    @property
    def title(self) -> str:
        """Return the highest achieved title according to Elo and KO wins."""
        def bracket_level(bracket: str) -> int:
            letters = [ord(c.upper()) - 65 for c in bracket if c.isalpha()]
            return min(letters) if letters else 100

        wins = [b.strip() for b in self.ko_titles.split(',') if b.strip()]
        levels = [bracket_level(b) for b in wins]

        gm = self.peak_elo >= 2000 and sum(1 for l in levels if l <= bracket_level('A')) >= 3
        im = self.peak_elo >= 1900 and sum(1 for l in levels if l <= bracket_level('C')) >= 2
        fm = self.peak_elo >= 1800 and any(l <= bracket_level('E') for l in levels)

        if gm:
            return "GM"
        if im:
            return "IM"
        if fm:
            return "FM"
        return ""

    def record(self, last_n: int | None = None) -> tuple[int, int, int]:
        """Return (wins, draws, losses) optionally limited to last_n matches."""
        query = Match.query.filter(
            (Match.player1_id == self.id) | (Match.player2_id == self.id)
        ).order_by(Match.id.desc())
        if last_n:
            matches = query.limit(last_n).all()
        else:
            matches = query.all()
        wins = draws = losses = 0
        for m in matches:
            if m.draw:
                draws += 1
            elif m.winner_id == self.id:
                wins += 1
            else:
                losses += 1
        return wins, draws, losses

    def win_percentage(self, last_n: int | None = None) -> float:
        wins, draws, losses = self.record(last_n)
        total = wins + draws + losses
        if total == 0:
            return 0.0
        return round(((wins + 0.5 * draws) / total) * 100, 1)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'))
    winner_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'), nullable=True)
    draw = db.Column(db.Boolean, default=False)
    round_no = db.Column(db.Integer, default=1)
