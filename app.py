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

def generate_swiss_pairs(players, previous_matches):
    """Pair players for a Swiss round avoiding rematches."""
    unpaired = players[:]
    pairs = []
    while len(unpaired) > 1:
        p1 = unpaired.pop(0)
        idx = None
        for i, p2 in enumerate(unpaired):
            if (p1.id, p2.id) not in previous_matches and (p2.id, p1.id) not in previous_matches:
                idx = i
                break
        if idx is None:
            p2 = unpaired.pop(0)
        else:
            p2 = unpaired.pop(idx)
        pairs.append((p1.id, p2.id, None))
    # bye if odd number of players
    if unpaired:
        bye = unpaired.pop(0)
        swiss_scores[bye.id] += 1
    return pairs

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
current_swiss_pairs = []
swiss_round = 0
swiss_scores = {}
swiss_previous_matches = set()

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


@app.route('/swiss', methods=['GET'])
def swiss():
    pairs = [(Amiibo.query.get(p1), Amiibo.query.get(p2), Amiibo.query.get(w) if w else None) for p1, p2, w in current_swiss_pairs]
    players = Amiibo.query.all()
    ordered = sorted(players, key=lambda a: swiss_scores.get(a.id, 0), reverse=True)
    done = swiss_round > 4
    current_round = min(swiss_round, 4)
    return render_template('swiss.html', pairs=pairs, players=ordered, scores=swiss_scores, round_no=current_round, done=done)


@app.route('/start_swiss', methods=['POST'])
def start_swiss():
    global current_swiss_pairs, swiss_round, swiss_scores, swiss_previous_matches
    players = Amiibo.query.order_by(Amiibo.current_elo.desc()).all()
    swiss_round = 1
    swiss_scores = {p.id: 0 for p in players}
    swiss_previous_matches = set()
    current_swiss_pairs = generate_swiss_pairs(players, swiss_previous_matches)
    return redirect('/swiss')


@app.route('/report_swiss_result', methods=['POST'])
def report_swiss_result():
    global current_swiss_pairs, swiss_scores, swiss_round, swiss_previous_matches
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    winner = int(request.form['winner'])
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    win_obj = a1 if winner == p1 else a2
    lose_obj = a2 if winner == p1 else a1
    update_elo(win_obj, lose_obj)
    match = Match(player1_id=p1, player2_id=p2, winner_id=winner, round_no=swiss_round)
    db.session.add(match)
    db.session.commit()
    swiss_scores[winner] += 1
    swiss_previous_matches.add((p1, p2))
    current_swiss_pairs = [ (pp1, pp2, w if (pp1, pp2) != (p1, p2) else winner) for pp1, pp2, w in current_swiss_pairs]

    if all(w for _,_,w in current_swiss_pairs):
        if swiss_round >= 4:
            swiss_round += 1
            players = sorted(Amiibo.query.all(), key=lambda a: swiss_scores.get(a.id, 0), reverse=True)
            total = len(players)
            per_group = (total + 3) // 4
            groups = ['A', 'B', 'C', 'D']
            for idx, p in enumerate(players):
                gi = min(idx // per_group, 3)
                p.league = groups[gi]
            db.session.commit()
            current_swiss_pairs = []
        else:
            swiss_round += 1
            players = sorted(Amiibo.query.all(), key=lambda a: (-swiss_scores.get(a.id, 0), a.current_elo))
            current_swiss_pairs = generate_swiss_pairs(players, swiss_previous_matches)
    return redirect('/swiss')

if __name__ == '__main__':
    app.run(debug=True)
