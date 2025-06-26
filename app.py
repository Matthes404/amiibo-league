from flask import Flask, render_template, request, redirect, send_from_directory
from sqlalchemy import text
from models import db, Amiibo, Match
from werkzeug.utils import secure_filename
import os
import random

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///amiibo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()
    # ensure the 'waiting' column exists if database was created before
    try:
        db.session.execute(text('SELECT waiting FROM amiibo LIMIT 1'))
    except Exception:
        db.session.execute(text('ALTER TABLE amiibo ADD COLUMN waiting BOOLEAN DEFAULT 0'))
        db.session.commit()
    # ensure the 'draw' column exists in matches
    try:
        db.session.execute(text('SELECT draw FROM match LIMIT 1'))
    except Exception:
        db.session.execute(text('ALTER TABLE match ADD COLUMN draw BOOLEAN DEFAULT 0'))
        db.session.commit()
    # ensure 'profile_pic' column exists
    try:
        db.session.execute(text('SELECT profile_pic FROM amiibo LIMIT 1'))
    except Exception:
        db.session.execute(text("ALTER TABLE amiibo ADD COLUMN profile_pic VARCHAR(120) DEFAULT ''"))
        db.session.commit()

@app.route('/logo/<path:filename>')
def serve_logo(filename):
    """Serve images from the logo directory."""
    return send_from_directory('logo', filename)

@app.route('/profile/<path:filename>')
def serve_profile(filename):
    """Serve profile pictures."""
    return send_from_directory('profile', filename)

# Simple ELO update function
K = 32

def update_elo(player1: Amiibo, player2: Amiibo, score1: float):
    """Update ratings given score for player1 (1=win, 0=loss, 0.5=draw)."""
    expected1 = 1 / (1 + 10 ** ((player2.current_elo - player1.current_elo) / 400))
    expected2 = 1 - expected1
    player1.current_elo += int(K * (score1 - expected1))
    player2.current_elo += int(K * ((1 - score1) - expected2))
    for p in (player1, player2):
        if p.current_elo > p.peak_elo:
            p.peak_elo = p.current_elo

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
    last = request.args.get('last', type=int)
    amiibos = Amiibo.query.order_by(Amiibo.current_elo.desc()).all()
    podium = amiibos[:3]
    return render_template('leaderboard.html', amiibos=amiibos, podium=podium, last=last)

@app.route('/amiibo/<int:amiibo_id>', methods=['GET'])
def amiibo_profile(amiibo_id):
    """Display detailed profile for an Amiibo."""
    amiibo = Amiibo.query.get_or_404(amiibo_id)

    # compute rating history from match order
    matches_all = Match.query.order_by(Match.id).all()
    ratings = {a.id: 1500 for a in Amiibo.query.all()}
    history_labels = [0]
    history_values = [1500]
    count = 0
    for m in matches_all:
        r1, r2 = ratings[m.player1_id], ratings[m.player2_id]
        if m.draw:
            score1 = 0.5
        else:
            score1 = 1 if m.winner_id == m.player1_id else 0
        expected1 = 1 / (1 + 10 ** ((r2 - r1) / 400))
        expected2 = 1 - expected1
        r1 += int(K * (score1 - expected1))
        r2 += int(K * ((1 - score1) - expected2))
        ratings[m.player1_id] = r1
        ratings[m.player2_id] = r2
        if m.player1_id == amiibo_id:
            count += 1
            history_labels.append(count)
            history_values.append(r1)
        if m.player2_id == amiibo_id:
            count += 1
            history_labels.append(count)
            history_values.append(r2)

    matches = Match.query.filter((Match.player1_id == amiibo_id) | (Match.player2_id == amiibo_id)).order_by(Match.id.desc()).all()
    display = []
    for m in matches:
        opp_id = m.player2_id if m.player1_id == amiibo_id else m.player1_id
        opponent = Amiibo.query.get(opp_id)
        if m.draw:
            result = 'Draw'
        else:
            result = 'Win' if m.winner_id == amiibo_id else 'Loss'
        display.append({'id': m.id, 'opponent': opponent.name, 'result': result})

    return render_template(
        'profile.html',
        amiibo=amiibo,
        rating_labels=history_labels,
        rating_values=history_values,
        matches=display,
    )

@app.route('/add_amiibo', methods=['POST'])
def add_amiibo():
    name = request.form['name']
    cycle = league_cycle_running()
    a = Amiibo(name=name, waiting=cycle)
    if not cycle:
        players = Amiibo.query.filter_by(waiting=False).all()
        groups = sorted(set(p.league for p in players if p.league))
        if not groups:
            target = 'A'
            size = 0
        else:
            last = groups[-1]
            size = sum(1 for p in players if p.league == last)
            if size >= 4:
                target = chr(ord(last) + 1)
                size = 0
            else:
                target = last
        a.league = target
    db.session.add(a)
    db.session.commit()
    return redirect('/leaderboard')

@app.route('/add_amiibos', methods=['POST'])
def add_amiibos():
    names = request.form['names']
    for raw in names.splitlines():
        name = raw.strip()
        if not name:
            continue
        cycle = league_cycle_running()
        a = Amiibo(name=name, waiting=cycle)
        if not cycle:
            players = Amiibo.query.filter_by(waiting=False).all()
            groups = sorted(set(p.league for p in players if p.league))
            if not groups:
                target = 'A'
                size = 0
            else:
                last = groups[-1]
                size = sum(1 for p in players if p.league == last)
                if size >= 4:
                    target = chr(ord(last) + 1)
                    size = 0
                else:
                    target = last
            a.league = target
        db.session.add(a)
    db.session.commit()
    return redirect('/leaderboard')

@app.route('/upload_pic/<int:amiibo_id>', methods=['POST'])
def upload_pic(amiibo_id):
    amiibo = Amiibo.query.get(amiibo_id)
    if 'picture' not in request.files or not amiibo:
        return redirect('/leaderboard')
    file = request.files['picture']
    if file.filename:
        filename = secure_filename(file.filename)
        os.makedirs('profile', exist_ok=True)
        path = os.path.join('profile', filename)
        file.save(path)
        amiibo.profile_pic = filename
        db.session.commit()
    return redirect('/leaderboard')

current_pairs = []
current_swiss_pairs = []
swiss_round = 0
swiss_scores = {}
swiss_previous_matches = set()
league_matches = {}
league_scores = {}
knockout_brackets = {}
knockout_remaining = {}

def league_cycle_running() -> bool:
    """Return True if Swiss, league or knockout is active."""
    return swiss_round > 0 or bool(league_matches) or bool(knockout_brackets)

@app.route('/tournament', methods=['GET'])
def tournament():
    def resolve(w):
        if w == 'draw':
            return 'Draw'
        return Amiibo.query.get(w) if w else None
    pairs = [(Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w)) for p1, p2, w in current_pairs]
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
    res = request.form['winner']
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    if res == 'draw':
        update_elo(a1, a2, 0.5)
        winner_id = None
        draw = True
    else:
        winner = int(res)
        score = 1 if winner == p1 else 0
        update_elo(a1, a2, score)
        winner_id = winner
        draw = False
    match = Match(player1_id=p1, player2_id=p2, winner_id=winner_id, draw=draw)
    db.session.add(match)
    db.session.commit()
    result_flag = 'draw' if draw else winner_id
    current_pairs = [ (pp1, pp2, w if (pp1, pp2) != (p1, p2) else result_flag) for pp1, pp2, w in current_pairs]
    return redirect('/tournament')


@app.route('/swiss', methods=['GET'])
def swiss():
    def resolve(w):
        if w == 'draw':
            return 'Draw'
        return Amiibo.query.get(w) if w else None
    pairs = [(Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w)) for p1, p2, w in current_swiss_pairs]
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
    res = request.form['winner']
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    if res == 'draw':
        update_elo(a1, a2, 0.5)
        winner_id = None
        draw = True
        swiss_scores[p1] += 0.5
        swiss_scores[p2] += 0.5
    else:
        winner = int(res)
        score = 1 if winner == p1 else 0
        update_elo(a1, a2, score)
        winner_id = winner
        draw = False
        swiss_scores[winner] += 1
    match = Match(player1_id=p1, player2_id=p2, winner_id=winner_id, draw=draw, round_no=swiss_round)
    db.session.add(match)
    db.session.commit()
    swiss_previous_matches.add((p1, p2))
    result_flag = 'draw' if draw else winner_id
    current_swiss_pairs = [ (pp1, pp2, w if (pp1, pp2) != (p1, p2) else result_flag) for pp1, pp2, w in current_swiss_pairs]

    if all(w for _,_,w in current_swiss_pairs):
        if swiss_round >= 4:
            swiss_round += 1
            players = sorted(Amiibo.query.all(), key=lambda a: swiss_scores.get(a.id, 0), reverse=True)
            total = len(players)
            num_groups = (total + 3) // 4
            groups = [chr(ord('A') + i) for i in range(num_groups)]
            league_matches.clear()
            league_scores.clear()
            for idx, p in enumerate(players):
                gi = idx // 4
                if gi >= num_groups:
                    gi = num_groups - 1
                league = groups[gi]
                p.league = league
                league_scores.setdefault(league, {})[p.id] = 0
            db.session.commit()
            for league in groups:
                players_in_league = [pl for pl in players if pl.league == league]
                matches = []
                for i in range(len(players_in_league)):
                    for j in range(i+1, len(players_in_league)):
                        matches.append((players_in_league[i].id, players_in_league[j].id, None))
                league_matches[league] = matches
            current_swiss_pairs = []
        else:
            swiss_round += 1
            players = sorted(Amiibo.query.all(), key=lambda a: (-swiss_scores.get(a.id, 0), a.current_elo))
            current_swiss_pairs = generate_swiss_pairs(players, swiss_previous_matches)
    return redirect('/swiss')


@app.route('/league', methods=['GET'])
def league():
    displays = []
    for lg in sorted(league_scores.keys()):
        players = [(Amiibo.query.get(pid), score) for pid, score in league_scores[lg].items()]
        players.sort(key=lambda x: x[1], reverse=True)
        def resolve(w):
            if w == 'draw':
                return 'Draw'
            return Amiibo.query.get(w) if w else None
        matches = [
            (Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w))
            for p1, p2, w in league_matches.get(lg, [])
        ]
        displays.append((lg, players, matches))
    return render_template('league.html', leagues=displays)


@app.route('/report_league_result', methods=['POST'])
def report_league_result():
    league = request.form['league']
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    res = request.form['winner']
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    if res == 'draw':
        update_elo(a1, a2, 0.5)
        winner_id = None
        draw = True
        league_scores[league][p1] += 0.5
        league_scores[league][p2] += 0.5
    else:
        winner = int(res)
        score = 1 if winner == p1 else 0
        update_elo(a1, a2, score)
        winner_id = winner
        draw = False
        league_scores[league][winner] += 1
    matches = league_matches.get(league, [])
    for idx, m in enumerate(matches):
        if (m[0], m[1]) == (p1, p2):
            matches[idx] = (p1, p2, 'draw' if draw else winner_id)
            break
    league_matches[league] = matches
    match = Match(player1_id=p1, player2_id=p2, winner_id=winner_id, draw=draw, round_no=swiss_round)
    db.session.add(match)
    db.session.commit()
    return redirect('/league')

def promote_and_relegate():
    players = Amiibo.query.filter_by(waiting=False).all()
    groups = sorted(set(p.league for p in players))
    rankings = {}
    for g in groups:
        scores = league_scores.get(g, {})
        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        if ordered:
            rankings[g] = [pid for pid, _ in ordered]
    promotions = {}
    relegations = {}
    for i, g in enumerate(groups):
        rank = rankings.get(g)
        if not rank:
            continue
        if i > 0 and rank:
            promotions[rank[0]] = groups[i-1]
        if i < len(groups) - 1 and rank:
            relegations[rank[-1]] = groups[i+1]
    for pid, lg in promotions.items():
        Amiibo.query.get(pid).league = lg
    for pid, lg in relegations.items():
        Amiibo.query.get(pid).league = lg
    db.session.commit()

def setup_league_matches():
    league_matches.clear()
    league_scores.clear()
    players = Amiibo.query.all()
    groups = sorted(set(p.league for p in players if p.league))
    if not groups:
        groups = ['A']
    last_group = groups[-1]
    size = sum(1 for p in players if p.league == last_group and not p.waiting)
    waiting = [p for p in players if p.waiting]
    for w in waiting:
        if size >= 4:
            last_group = chr(ord(last_group) + 1)
            groups.append(last_group)
            size = 0
        w.league = last_group
        w.waiting = False
        size += 1
    db.session.commit()
    players = Amiibo.query.all()
    groups = sorted(set(p.league for p in players if p.league))
    for g in groups:
        pls = [p for p in players if p.league == g]
        league_scores[g] = {p.id: 0 for p in pls}
        matches = []
        for i in range(len(pls)):
            for j in range(i+1, len(pls)):
                matches.append((pls[i].id, pls[j].id, None))
        league_matches[g] = matches

def setup_knockouts():
    knockout_brackets.clear()
    knockout_remaining.clear()
    players = Amiibo.query.filter_by(waiting=False).all()
    groups = sorted(set(p.league for p in players))
    for i in range(0, len(groups), 2):
        if i+1 >= len(groups):
            break
        g1, g2 = groups[i], groups[i+1]
        key = g1 + g2
        contestants = [p for p in players if p.league in (g1, g2)]
        random.shuffle(contestants)
        knockout_remaining[key] = [p.id for p in contestants]
        pairs = []
        for j in range(0, len(contestants), 2):
            if j+1 < len(contestants):
                pairs.append((contestants[j].id, contestants[j+1].id, None))
        knockout_brackets[key] = pairs

def advance_knockout(key):
    winners = []
    for m in knockout_brackets[key]:
        if m[2] == 'draw':
            return
        if m[2]:
            winners.append(m[2])
    if len(winners) * 2 != len(knockout_brackets[key]) * 2:
        return
    if len(winners) == 1:
        champ = Amiibo.query.get(winners[0])
        champ.ko_titles = (champ.ko_titles + ',' if champ.ko_titles else '') + key
        db.session.commit()
        knockout_brackets[key] = []
        knockout_remaining[key] = winners
    else:
        random.shuffle(winners)
        pairs = []
        for i in range(0, len(winners), 2):
            if i+1 < len(winners):
                pairs.append((winners[i], winners[i+1], None))
        knockout_brackets[key] = pairs
        knockout_remaining[key] = winners

def check_knockouts_done():
    for k in knockout_brackets:
        if knockout_brackets[k]:
            return False
    return True

@app.route('/finish_league', methods=['POST'])
def finish_league():
    promote_and_relegate()
    setup_knockouts()
    return redirect('/knockout')

@app.route('/knockout', methods=['GET'])
def knockout():
    displays = {}
    for key, pairs in knockout_brackets.items():
        def resolve(w):
            if w == 'draw':
                return 'Draw'
            return Amiibo.query.get(w) if w else None
        pairs_disp = [(Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w)) for p1, p2, w in pairs]
        winner = None
        if not pairs and knockout_remaining.get(key):
            winner = Amiibo.query.get(knockout_remaining[key][0])
        displays[key] = {'pairs': pairs_disp, 'winner': winner}
    return render_template('knockout.html', brackets=displays)

@app.route('/report_knockout_result', methods=['POST'])
def report_knockout_result():
    key = request.form['bracket']
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    res = request.form['winner']
    a1 = Amiibo.query.get(p1)
    a2 = Amiibo.query.get(p2)
    if res == 'draw':
        update_elo(a1, a2, 0.5)
        winner_id = None
        draw = True
    else:
        winner = int(res)
        score = 1 if winner == p1 else 0
        update_elo(a1, a2, score)
        winner_id = winner
        draw = False
    matches = knockout_brackets.get(key, [])
    for idx, m in enumerate(matches):
        if (m[0], m[1]) == (p1, p2):
            matches[idx] = (p1, p2, 'draw' if draw else winner_id)
            break
    knockout_brackets[key] = matches
    db.session.commit()
    advance_knockout(key)
    if check_knockouts_done():
        setup_league_matches()
    return redirect('/knockout')

if __name__ == '__main__':
    app.run(debug=True)
