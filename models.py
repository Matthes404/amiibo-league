from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Amiibo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    current_elo = db.Column(db.Integer, default=1500)
    peak_elo = db.Column(db.Integer, default=1500)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player1_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'))
    player2_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'))
    winner_id = db.Column(db.Integer, db.ForeignKey('amiibo.id'))
    round_no = db.Column(db.Integer, default=1)
