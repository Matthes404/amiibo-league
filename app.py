from flask import Flask, render_template, request, redirect, send_from_directory
from sqlalchemy import text
from models import db, Amiibo, Match, State
from models import Season
from werkzeug.utils import secure_filename
import os
import random
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///amiibo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# in-memory state variables (populated from DB later)
current_pairs = []
current_swiss_pairs = []
swiss_round = 0
swiss_scores = {}
swiss_previous_matches = set()
league_matches = {}
league_scores = {}
swiss_diff = {}
swiss_wins = {}
swiss_opponents = {}
league_diff = {}
league_wins = {}
league_results = {}
knockout_brackets = {}
knockout_remaining = {}
knockout_history = {}

with app.app_context():
    db.create_all()
    # utility functions for persisting state
    def get_state(key, default):
        entry = State.query.get(key)
        if not entry:
            return default
        try:
            return json.loads(entry.value)
        except Exception:
            return default

    def set_state(key, value):
        entry = State.query.get(key)
        if not entry:
            entry = State(key=key)
            db.session.add(entry)
        entry.value = json.dumps(value)

    def load_all_state():
        """Load persistent state from the database."""
        global current_pairs, current_swiss_pairs, swiss_round
        global swiss_scores, swiss_previous_matches, league_matches
        global league_scores, knockout_brackets, knockout_remaining
        global knockout_history
        global swiss_diff, swiss_wins, swiss_opponents
        global league_diff, league_wins, league_results

        current_pairs = get_state('current_pairs', [])
        current_swiss_pairs = get_state('current_swiss_pairs', [])
        swiss_round = get_state('swiss_round', 0)

        ss_raw = get_state('swiss_scores', {})
        swiss_scores = {int(k): v for k, v in ss_raw.items()}

        swiss_diff = {int(k): v for k, v in get_state('swiss_diff', {}).items()}
        swiss_wins = {int(k): v for k, v in get_state('swiss_wins', {}).items()}
        so_raw = get_state('swiss_opponents', {})
        swiss_opponents = {int(k): set(map(int, v)) for k, v in so_raw.items()}

        prev_raw = get_state('swiss_previous_matches', [])
        swiss_previous_matches = {tuple(map(int, p)) for p in prev_raw}

        lm_raw = get_state('league_matches', {})
        league_matches = {g: [tuple(p) for p in ps] for g, ps in lm_raw.items()}

        ls_raw = get_state('league_scores', {})
        league_scores = {g: {int(pid): sc for pid, sc in d.items()} for g, d in ls_raw.items()}

        ld_raw = get_state('league_diff', {})
        league_diff = {g: {int(pid): val for pid, val in d.items()} for g, d in ld_raw.items()}
        lw_raw = get_state('league_wins', {})
        league_wins = {g: {int(pid): val for pid, val in d.items()} for g, d in lw_raw.items()}
        lr_raw = get_state('league_results', {})
        league_results = {int(pid): [(int(o), r) for o, r in lst] for pid, lst in lr_raw.items()}

        kb_raw = get_state('knockout_brackets', {})
        knockout_brackets = {k: [tuple(p) for p in ps] for k, ps in kb_raw.items()}

        kr_raw = get_state('knockout_remaining', {})
        knockout_remaining = {k: [int(pid) for pid in lst] for k, lst in kr_raw.items()}

        kh_raw = get_state('knockout_history', {})
        knockout_history = {
            k: [[tuple(p) for p in rnd] for rnd in rounds]
            for k, rounds in kh_raw.items()
        }

    def save_all_state():
        """Persist in-memory state to the database."""
        set_state('current_pairs', current_pairs)
        set_state('current_swiss_pairs', current_swiss_pairs)
        set_state('swiss_round', swiss_round)
        set_state('swiss_scores', swiss_scores)
        set_state('swiss_diff', swiss_diff)
        set_state('swiss_wins', swiss_wins)
        set_state('swiss_opponents', {k: list(v) for k, v in swiss_opponents.items()})
        set_state('swiss_previous_matches', [list(p) for p in swiss_previous_matches])
        set_state('league_matches', {g: [list(p) for p in ps] for g, ps in league_matches.items()})
        set_state('league_scores', league_scores)
        set_state('league_diff', league_diff)
        set_state('league_wins', league_wins)
        set_state('league_results', {pid: [(o, r) for o, r in lst] for pid, lst in league_results.items()})
        set_state('knockout_brackets', {k: [list(p) for p in ps] for k, ps in knockout_brackets.items()})
        set_state('knockout_remaining', knockout_remaining)
        set_state('knockout_history', {
            k: [[list(p) for p in rnd] for rnd in rounds]
            for k, rounds in knockout_history.items()
        })
        db.session.commit()

    load_all_state()
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
    # ensure score columns exist
    try:
        db.session.execute(text('SELECT score1 FROM match LIMIT 1'))
    except Exception:
        db.session.execute(text('ALTER TABLE match ADD COLUMN score1 INTEGER DEFAULT 0'))
        db.session.execute(text('ALTER TABLE match ADD COLUMN score2 INTEGER DEFAULT 0'))
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

def record_match(
    player1_id: int,
    player2_id: int,
    score1: int,
    score2: int,
    round_no: int | None = None,
) -> tuple[int | None, bool]:
    """Apply a result and persist the match.

    Parameters
    ----------
    player1_id, player2_id:
        IDs of the players in the pairing order.
    score1, score2:
        Numeric result for player1 and player2.
    round_no:
        Optional round number for Swiss/league matches.

    Returns
    -------
    tuple
        ``(winner_id, draw)`` describing the stored result.
    """

    a1 = Amiibo.query.get(player1_id)
    a2 = Amiibo.query.get(player2_id)
    if score1 == score2:
        update_elo(a1, a2, 0.5)
        winner_id = None
        draw = True
    elif score1 > score2:
        update_elo(a1, a2, 1)
        winner_id = player1_id
        draw = False
    else:
        update_elo(a1, a2, 0)
        winner_id = player2_id
        draw = False
    match = Match(
        player1_id=player1_id,
        player2_id=player2_id,
        winner_id=winner_id,
        draw=draw,
        score1=score1,
        score2=score2,
    )
    if round_no is not None:
        match.round_no = round_no
    db.session.add(match)
    db.session.commit()
    return winner_id, draw

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

    show_all = request.args.get('all') == '1'
    if not show_all:
        display = display[:5]

    return render_template(
        'profile.html',
        amiibo=amiibo,
        rating_labels=history_labels,
        rating_values=history_values,
        matches=display,
        show_all=show_all,
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

def league_cycle_running() -> bool:
    """Return True if Swiss, league or knockout is active."""
    return swiss_round > 0 or bool(league_matches) or bool(knockout_brackets)

@app.route('/match', methods=['GET'])
def match():
    players = Amiibo.query.order_by(Amiibo.name).all()
    def resolve(m):
        if m.draw:
            return 'Draw'
        return Amiibo.query.get(m.winner_id) if m.winner_id else None
    recent = Match.query.order_by(Match.id.desc()).limit(10).all()
    pairs = [(Amiibo.query.get(m.player1_id), Amiibo.query.get(m.player2_id), resolve(m)) for m in recent]
    return render_template('match.html', players=players, pairs=pairs)

@app.route('/report_match', methods=['POST'])
def report_match():
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    score1 = int(request.form['score1'])
    score2 = int(request.form['score2'])
    record_match(p1, p2, score1, score2)
    save_all_state()
    return redirect('/match')


@app.route('/swiss', methods=['GET'])
def swiss():
    def resolve(w):
        if w == 'draw':
            return 'Draw'
        return Amiibo.query.get(w) if w else None
    pairs = [(Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w)) for p1, p2, w in current_swiss_pairs]
    players = Amiibo.query.all()
    buchholz = {p.id: sum(swiss_scores.get(o, 0) for o in swiss_opponents.get(p.id, [])) for p in players}
    ordered = sorted(
        players,
        key=lambda a: (
            swiss_scores.get(a.id, 0),
            swiss_diff.get(a.id, 0),
            swiss_wins.get(a.id, 0),
            buchholz[a.id],
        ),
        reverse=True,
    )
    done = swiss_round > 4
    current_round = min(swiss_round, 4)
    return render_template(
        'swiss.html',
        pairs=pairs,
        players=ordered,
        scores=swiss_scores,
        diff=swiss_diff,
        wins=swiss_wins,
        buchholz=buchholz,
        round_no=current_round,
        done=done,
    )


@app.route('/start_swiss', methods=['POST'])
def start_swiss():
    global current_swiss_pairs, swiss_round, swiss_scores, swiss_previous_matches
    global swiss_diff, swiss_wins, swiss_opponents
    players = Amiibo.query.order_by(Amiibo.current_elo.desc()).all()
    swiss_round = 1
    swiss_scores = {p.id: 0 for p in players}
    swiss_diff = {p.id: 0 for p in players}
    swiss_wins = {p.id: 0 for p in players}
    swiss_opponents = {p.id: set() for p in players}
    swiss_previous_matches = set()
    current_swiss_pairs = generate_swiss_pairs(players, swiss_previous_matches)
    save_all_state()
    return redirect('/swiss')


@app.route('/report_swiss_result', methods=['POST'])
def report_swiss_result():
    global current_swiss_pairs, swiss_scores, swiss_round, swiss_previous_matches
    global swiss_diff, swiss_wins, swiss_opponents
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    score1 = int(request.form['score1'])
    score2 = int(request.form['score2'])
    winner_id, draw = record_match(p1, p2, score1, score2, swiss_round)
    if draw:
        swiss_scores[p1] += 0.5
        swiss_scores[p2] += 0.5
    else:
        swiss_scores[winner_id] += 1
        swiss_wins[winner_id] += 1
    swiss_diff[p1] += score1 - score2
    swiss_diff[p2] += score2 - score1
    swiss_opponents.setdefault(p1, set()).add(p2)
    swiss_opponents.setdefault(p2, set()).add(p1)
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
            league_diff.clear()
            league_wins.clear()
            league_results.clear()
            for idx, p in enumerate(players):
                gi = idx // 4
                if gi >= num_groups:
                    gi = num_groups - 1
                league = groups[gi]
                p.league = league
                league_scores.setdefault(league, {})[p.id] = 0
                league_diff.setdefault(league, {})[p.id] = 0
                league_wins.setdefault(league, {})[p.id] = 0
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
    save_all_state()
    return redirect('/swiss')


@app.route('/league', methods=['GET'])
def league():
    displays = []
    for lg in sorted(league_scores.keys()):
        scores = league_scores[lg]
        diffs = league_diff.get(lg, {})
        wins = league_wins.get(lg, {})
        sb = {}
        for pid in scores:
            sb[pid] = sum(scores.get(op, 0) * pts for op, pts in league_results.get(pid, []))
        players = [
            (
                Amiibo.query.get(pid),
                scores[pid],
                diffs.get(pid, 0),
                wins.get(pid, 0),
                sb[pid],
            )
            for pid in scores
        ]
        players.sort(key=lambda x: (x[1], x[2], x[3], x[4]), reverse=True)
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
    score1 = int(request.form['score1'])
    score2 = int(request.form['score2'])
    winner_id, draw = record_match(p1, p2, score1, score2, swiss_round)
    if draw:
        league_scores[league][p1] += 0.5
        league_scores[league][p2] += 0.5
    else:
        league_scores[league][winner_id] += 1
        league_wins[league][winner_id] += 1
    league_diff[league][p1] += score1 - score2
    league_diff[league][p2] += score2 - score1
    league_results.setdefault(p1, []).append((p2, 1 if winner_id == p1 else 0.5 if draw else 0))
    league_results.setdefault(p2, []).append((p1, 1 if winner_id == p2 else 0.5 if draw else 0))
    matches = league_matches.get(league, [])
    for idx, m in enumerate(matches):
        if (m[0], m[1]) == (p1, p2):
            matches[idx] = (p1, p2, 'draw' if draw else winner_id)
            break
    league_matches[league] = matches
    # match stored via record_match
    save_all_state()
    return redirect('/league')

def promote_and_relegate():
    players = Amiibo.query.filter_by(waiting=False).all()
    groups = sorted(set(p.league for p in players))
    rankings = {}
    for g in groups:
        scores = league_scores.get(g, {})
        diffs = league_diff.get(g, {})
        wins = league_wins.get(g, {})
        sb = {}
        for pid in scores:
            sb[pid] = sum(scores.get(op, 0) * pts for op, pts in league_results.get(pid, []))
        ordered = sorted(
            scores.keys(),
            key=lambda pid: (
                scores[pid],
                diffs.get(pid, 0),
                wins.get(pid, 0),
                sb[pid],
            ),
            reverse=True,
        )
        if ordered:
            rankings[g] = list(ordered)
    # Award league titles to the top player in each group
    for g, rank in rankings.items():
        if rank:
            champ = Amiibo.query.get(rank[0])
            champ.league_titles = (
                (champ.league_titles + ',' if champ.league_titles else '') + g
            )
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
    league_diff.clear()
    league_wins.clear()
    league_results.clear()
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
        league_diff[g] = {p.id: 0 for p in pls}
        league_wins[g] = {p.id: 0 for p in pls}
        matches = []
        for i in range(len(pls)):
            for j in range(i+1, len(pls)):
                matches.append((pls[i].id, pls[j].id, None))
        league_matches[g] = matches
    save_all_state()

def setup_knockouts():
    knockout_brackets.clear()
    knockout_remaining.clear()
    knockout_history.clear()
    players = Amiibo.query.filter_by(waiting=False).all()
    players_by_group = {}
    for p in players:
        players_by_group.setdefault(p.league, []).append(p)
    groups = sorted([g for g, ps in players_by_group.items() if len(ps) == 4])
    i = 0
    while i < len(groups):
        g1 = groups[i]
        g2 = groups[i + 1] if i + 1 < len(groups) else None
        if g2:
            key = g1 + g2
            contestants = players_by_group[g1] + players_by_group[g2]
            i += 2
        else:
            key = g1
            contestants = players_by_group[g1]
            i += 1
        random.shuffle(contestants)
        knockout_remaining[key] = [p.id for p in contestants]
        pairs = []
        for j in range(0, len(contestants), 2):
            if j+1 < len(contestants):
                pairs.append((contestants[j].id, contestants[j+1].id, None))
        knockout_brackets[key] = pairs
        knockout_history[key] = [list(pairs)]
    save_all_state()

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
        knockout_history.setdefault(key, []).append([])
    else:
        random.shuffle(winners)
        pairs = []
        for i in range(0, len(winners), 2):
            if i+1 < len(winners):
                pairs.append((winners[i], winners[i+1], None))
        knockout_brackets[key] = pairs
        knockout_remaining[key] = winners
        knockout_history.setdefault(key, []).append(list(pairs))
    save_all_state()

def check_knockouts_done():
    for k in knockout_brackets:
        if knockout_brackets[k]:
            return False
    return True

def archive_current_season():
    """Store league standings and knockout history for the completed season."""
    league_serial = {
        'scores': league_scores,
        'diff': league_diff,
        'wins': league_wins,
        'results': {pid: [(o, r) for o, r in lst] for pid, lst in league_results.items()},
        'matches': {g: [list(p) for p in ps] for g, ps in league_matches.items()},
    }
    knockout_serial = {
        'history': {k: [[list(p) for p in rnd] for rnd in rounds] for k, rounds in knockout_history.items()},
        'winners': knockout_remaining,
    }
    season = Season(
        league_data=json.dumps(league_serial),
        knockout_data=json.dumps(knockout_serial),
    )
    db.session.add(season)
    db.session.commit()

@app.route('/finish_league', methods=['POST'])
def finish_league():
    promote_and_relegate()
    setup_knockouts()
    return redirect('/knockout')

@app.route('/knockout', methods=['GET'])
def knockout():
    displays = {}
    def resolve(w):
        if w == 'draw':
            return 'Draw'
        return Amiibo.query.get(w) if w else None

    for key, rounds in knockout_history.items():
        rounds_disp = []
        for pairs in rounds:
            pairs_disp = [
                (Amiibo.query.get(p1), Amiibo.query.get(p2), resolve(w))
                for p1, p2, w in pairs
            ]
            rounds_disp.append(pairs_disp)
        winner = None
        if not knockout_brackets.get(key) and knockout_remaining.get(key):
            winner = Amiibo.query.get(knockout_remaining[key][0])
        displays[key] = {'rounds': rounds_disp, 'winner': winner}
    return render_template('knockout.html', brackets=displays)

@app.route('/report_knockout_result', methods=['POST'])
def report_knockout_result():
    key = request.form['bracket']
    p1 = int(request.form['player1'])
    p2 = int(request.form['player2'])
    score1 = int(request.form['score1'])
    score2 = int(request.form['score2'])
    winner_id, draw = record_match(p1, p2, score1, score2)
    matches = knockout_brackets.get(key, [])
    for idx, m in enumerate(matches):
        if (m[0], m[1]) == (p1, p2):
            if draw:
                # keep the draw in history but schedule a rematch
                matches[idx] = (p1, p2, None)
            else:
                matches[idx] = (p1, p2, winner_id)
            break
    knockout_brackets[key] = matches
    # mirror result in history
    round_idx = len(knockout_history.get(key, [])) - 1
    if round_idx >= 0:
        hist_round = knockout_history.setdefault(key, [])[round_idx]
        for idx, m in enumerate(hist_round):
            if (m[0], m[1]) == (p1, p2):
                hist_round[idx] = (p1, p2, 'draw' if draw else winner_id)
                if draw:
                    # add a new entry for the rematch immediately after
                    hist_round.insert(idx + 1, (p1, p2, None))
                break
    db.session.commit()
    advance_knockout(key)
    if check_knockouts_done():
        archive_current_season()
        setup_league_matches()
    save_all_state()
    return redirect('/knockout')


@app.route('/seasons', methods=['GET'])
def seasons_view():
    """Display archived results of past seasons."""
    items = []
    for s in Season.query.order_by(Season.id.desc()).all():
        league = json.loads(s.league_data)
        knockout = json.loads(s.knockout_data)
        leagues_disp = []
        scores = league.get('scores', {})
        diffs = league.get('diff', {})
        wins = league.get('wins', {})
        results = {
            int(pid): [(int(o), r) for o, r in lst]
            for pid, lst in league.get('results', {}).items()
        }
        for lg in sorted(scores.keys()):
            sc = {int(pid): val for pid, val in scores[lg].items()}
            df = {int(pid): diffs.get(lg, {}).get(pid, 0) for pid in sc}
            wn = {int(pid): wins.get(lg, {}).get(pid, 0) for pid in sc}
            sb = {}
            for pid in sc:
                sb[pid] = sum(sc.get(op, 0) * pts for op, pts in results.get(pid, []))
            players = [
                (Amiibo.query.get(pid), sc[pid], df[pid], wn[pid], sb[pid])
                for pid in sc
            ]
            players.sort(key=lambda x: (x[1], x[2], x[3], x[4]), reverse=True)
            winner = players[0][0] if players else None
            leagues_disp.append((lg, winner))

        brackets = {}
        winners = knockout.get('winners', {})
        for key, w in winners.items():
            win = Amiibo.query.get(w[0]) if w else None
            brackets[key] = win

        items.append({'id': s.id, 'leagues': leagues_disp, 'brackets': brackets})

    return render_template('seasons.html', seasons=items)

if __name__ == '__main__':
    app.run(debug=True)
