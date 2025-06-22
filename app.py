from flask import Flask, render_template, request, redirect
from models import db, Amiibo, Match
import random

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///amiibo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# Simple ELO update function
K = 32

def update_elo(winner: Amiibo, loser: Amiibo):
    expected_win = 1 / (1 + 10 ** ((loser.current_elo - winner.current_elo)/400))
    winner.current_elo += int(K * (1 - expected_win))
    loser.current_elo += int(K * (0 - (1 - expected_win)))
    if winner.current_elo > winner.peak_elo:
        winner.peak_elo = winner.current_elo
    if loser.current_elo > loser.peak_elo:
        loser.peak_elo = loser.current_elo

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/leaderboard', methods=['GET'])
def leaderboard():
    amiibos = Amiibo.query.order_by(Amiibo.current_elo.desc()).all()
    return render_template('leaderboard.html', amiibos=amiibos)

@app.route('/add_amiibo', methods=['POST'])
def add_amiibo():
    name = request.form['name']
    a = Amiibo(name=name)
    db.session.add(a)
    db.session.commit()
    return redirect('/leaderboard')

current_pairs = []

@app.route('/tournament', methods=['GET'])
def tournament():
    pairs = [(Amiibo.query.get(p1), Amiibo.query.get(p2), Amiibo.query.get(w) if w else None) for p1, p2, w in current_pairs]
    return render_template('tournament.html', pairs=pairs)

@app.route('/start_tournament', methods=['POST'])
def start_tournament():
    global current_pairs
    players = Amiibo.query.order_by(Amiibo.current_elo.desc()).limit(8).all()
    random.shuffle(players)
    current_pairs = []
    for i in range(0, len(players), 2):
        if i+1 < len(players):
            current_pairs.append((players[i].id, players[i+1].id, None))
    return redirect('/tournament')

@app.route('/report_result', methods=['POST'])
def report_result():
    global current_pairs
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    winner = int(request.form['winner'])
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    win_obj = a1 if winner == p1 else a2
    lose_obj = a2 if winner == p1 else a1
    update_elo(win_obj, lose_obj)
    match = Match(player1_id=p1, player2_id=p2, winner_id=winner)
    db.session.add(match)
    db.session.commit()
    current_pairs = [ (pp1, pp2, w if (pp1, pp2) != (p1, p2) else winner) for pp1, pp2, w in current_pairs]
    return redirect('/tournament')

if __name__ == '__main__':
    app.run(debug=True)
