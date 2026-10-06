import os
import re
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, or_, func
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
database_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'scribe_italia.db'))
if database_url.startswith('postgres://'):
    database_url = 'postgresql://' + database_url[len('postgres://'):]
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Devi effettuare il login per accedere a questa pagina.'

ROLE_ADMIN = 'admin'
ROLE_PREFECT = 'prefect'
ROLE_OFFICER = 'officer'


class Province(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    cities = db.relationship('City', backref='province', lazy=True, cascade='all, delete-orphan')


class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=False)
    __table_args__ = (UniqueConstraint('name', 'province_id', name='uq_city_province'),)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_OFFICER)
    approved = db.Column(db.Boolean, default=False, nullable=False)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'))
    requested_province_id = db.Column(db.Integer, db.ForeignKey('province.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    province = db.relationship('Province', foreign_keys=[province_id])
    requested_province = db.relationship('Province', foreign_keys=[requested_province_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class CityAuthorization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'), nullable=False)
    user = db.relationship('User', backref='city_authorizations')
    city = db.relationship('City')
    __table_args__ = (UniqueConstraint('user_id', 'city_id', name='uq_user_city_auth'),)


class Enemy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(80), nullable=False)
    province_id = db.Column(db.Integer, db.ForeignKey('province.id'), nullable=False)
    note = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    province = db.relationship('Province')
    __table_args__ = (UniqueConstraint('nickname', 'province_id', name='uq_enemy_province'),)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city_id = db.Column(db.Integer, db.ForeignKey('city.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    raw_people = db.Column(db.Text, default='')
    raw_groups = db.Column(db.Text, default='')
    raw_armies = db.Column(db.Text, default='')
    raw_sightings = db.Column(db.Text, default='')
    parsed_people_json = db.Column(db.Text, default='[]')
    parsed_groups_json = db.Column(db.Text, default='[]')
    parsed_sightings_json = db.Column(db.Text, default='[]')
    bbcode = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    city = db.relationship('City')
    author = db.relationship('User')
    __table_args__ = (UniqueConstraint('city_id', 'report_date', name='uq_report_city_date'),)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def parse_people(text):
    """Parse the citizen list copied directly from Renaissance Kingdoms.

    The browser may copy the table as tab-separated text, plain aligned text,
    or Markdown-like rows depending on the environment. We therefore do not
    rely on a specific column separator: we locate the PR value first and use
    the text before it as the name cell.
    """
    results = []
    seen = set()

    for raw in text.splitlines():
        line = raw.replace('\xa0', ' ').strip()
        if not line:
            continue

        # Ignore table separators / headers.
        if set(line) <= {'|', '-', ':', ' ', '\t'}:
            continue

        pr_match = re.search(r'(?<!\d)(\d{1,3})\s*PR\b', line, flags=re.I)
        if not pr_match:
            continue

        # Everything before the PR belongs to the first/name column plus any
        # harmless table separators introduced by copy/paste.
        before_pr = line[:pr_match.start()].strip()
        before_pr = before_pr.strip('|').strip()

        # If copied from an HTML table, columns are normally separated by tabs.
        # Keep the first non-empty cell.
        tab_cells = [c.strip(' |') for c in before_pr.split('\t') if c.strip(' |')]
        if tab_cells:
            name_part = tab_cells[0]
        else:
            # Markdown-like tables use | separators.
            pipe_cells = [c.strip() for c in before_pr.split('|') if c.strip()]
            name_part = pipe_cells[0] if pipe_cells else before_pr

        # RK nicknames do not contain spaces. Titles, noble names and other
        # descriptive text may follow the login, therefore the nickname ends
        # at the first comma OR the first whitespace, whichever comes first.
        nickname = name_part.split(',', 1)[0].strip()
        nickname = re.sub(r'^[-–—•]+\s*', '', nickname).strip()
        nickname = nickname.split()[0] if nickname.split() else ''

        if not nickname or nickname.lower() in {'nome', 'nickname', 'personaggio'}:
            continue

        key = nickname.casefold()
        if key in seen:
            continue
        seen.add(key)
        results.append({'nickname': nickname, 'pr': int(pr_match.group(1))})

    return results


def _clean_enemy_candidate(value):
    value = re.sub(r'[*`]', '', value or '').strip()
    value = re.sub(r'^[\s\-–—•]+', '', value).strip()
    value = re.sub(r'\s+', ' ', value)
    return value.strip()


def parse_enemy_bulk(text):
    """Extract current nicknames from pasted enemy lists.

    Supports Markdown copies from the RK forum such as:
    1. [*Maso_donati Maso_donati*](https://...) ... già noto come Leonard_da_vinci

    Previous aliases are deliberately ignored. The parser also tolerates
    plain-text copies where the nickname is repeated twice.
    """
    results = []
    seen = set()

    for raw in text.splitlines():
        line = raw.replace('\xa0', ' ').strip()
        if not line:
            continue

        # Drop anything after an old-alias marker before analysing the current name.
        line = re.split(r'\bgi[àa]\s+noto\s+come\b', line, maxsplit=1, flags=re.I)[0].strip()

        candidate = ''
        # Preferred format: Markdown link label.
        md = re.search(r'\[\s*\*?([^]\n]+?)\*?\s*\]\s*\(', line)
        if md:
            candidate = _clean_enemy_candidate(md.group(1))
        else:
            # Plain-text fallback: remove numbering, URLs and image markers.
            plain = re.sub(r'^\s*\d+[.)]\s*', '', line)
            plain = re.sub(r'https?://\S+', ' ', plain)
            plain = re.sub(r'\(\s*image\s*\)', ' ', plain, flags=re.I)
            plain = re.sub(r'\[[^]]*image[^]]*\]', ' ', plain, flags=re.I)
            plain = _clean_enemy_candidate(plain)
            if plain:
                candidate = plain

        if not candidate:
            continue

        # Forum lists commonly repeat the current nickname twice. If the two
        # halves are identical, retain only one copy.
        tokens = candidate.split()
        if len(tokens) >= 2 and len(tokens) % 2 == 0:
            half = len(tokens) // 2
            left = ' '.join(tokens[:half])
            right = ' '.join(tokens[half:])
            if left.casefold() == right.casefold():
                candidate = left
        elif len(tokens) == 2 and tokens[0].casefold() == tokens[1].casefold():
            candidate = tokens[0]

        # Nicknames in RK do not contain spaces in the examples we support.
        # If noise remains after the first token, prefer the first token.
        if ' ' in candidate:
            first, rest = candidate.split(' ', 1)
            if first.casefold() in rest.casefold().split():
                candidate = first

        candidate = candidate.strip()
        if not candidate or candidate.lower() in {'image', 'nickname', 'nome'}:
            continue

        key = candidate.casefold()
        if key not in seen:
            seen.add(key)
            results.append(candidate)

    return results


def parse_groups(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    groups = []
    i = 0
    while i < len(lines):
        line = re.sub(r'<br\s*/?>', ' ', lines[i], flags=re.I)
        if line.lower().startswith(('gruppo armato di ', 'corpo d\'armi di ', 'lancia di ', 'gruppo di ')):
            if ' di ' in line:
                group_type, members_part = line.split(' di ', 1)
                members = [m.strip() for m in members_part.split(',') if m.strip()]
                access = ''
                if i + 1 < len(lines):
                    access = re.sub(r'[*_]', '', lines[i + 1]).strip()
                groups.append({
                    'type': group_type.strip(),
                    'leader': members[0] if members else '',
                    'members': members,
                    'access_mode': access,
                    'raw': line,
                })
        i += 1
    return groups


def parse_armies(text):
    cleaned = text.strip()
    if not cleaned or cleaned.lower() == 'nessuno':
        return []
    return [{'raw': cleaned}]


def parse_sightings(text):
    clean = ' '.join(ln.strip() for ln in text.splitlines() if ln.strip())
    if not clean:
        return []
    # Pattern base, volutamente prudente per l'MVP.
    match = re.search(r'avete\s+(?:visto|incrociato)\s+(.+)', clean, flags=re.I)
    if not match:
        return []
    tail = match.group(1).strip().rstrip('.')
    tail = re.sub(r'\be\s+l[’\']esercito.*$', '', tail, flags=re.I)
    parts = re.split(r'\s*,\s*|\s+e\s+', tail)
    names = []
    for part in parts:
        p = part.strip(' .,:;')
        if p and not p.lower().startswith(('l\'esercito', 'un esercito', 'esercito')):
            names.append(p)
    return names


def _load_people_from_report(report):
    if not report:
        return []
    import json
    try:
        return json.loads(report.parsed_people_json or '[]')
    except (TypeError, ValueError):
        return []


def compare_with_previous_report(city_id, report_date, people):
    previous = (Report.query
                .filter(Report.city_id == city_id, Report.report_date < report_date)
                .order_by(Report.report_date.desc(), Report.created_at.desc())
                .first())
    if not previous:
        return previous, [], [], []

    previous_people = _load_people_from_report(previous)
    current_map = {p['nickname'].casefold(): p['nickname'] for p in people}
    previous_map = {p['nickname'].casefold(): p['nickname'] for p in previous_people}

    new_keys = current_map.keys() - previous_map.keys()
    departed_keys = previous_map.keys() - current_map.keys()
    existing_keys = current_map.keys() & previous_map.keys()

    new_people = [current_map[k] for k in current_map if k in new_keys]
    departed_people = [previous_map[k] for k in previous_map if k in departed_keys]
    existing_people = [current_map[k] for k in current_map if k in existing_keys]
    return previous, new_people, departed_people, existing_people


def enemies_present_for(city, people):
    enemy_rows = Enemy.query.filter_by(province_id=city.province_id).all()
    enemy_map = {e.nickname.casefold(): e for e in enemy_rows}
    present = []
    for person in people:
        enemy = enemy_map.get(person['nickname'].casefold())
        if enemy:
            present.append(enemy)
    return present


def generate_bbcode(city, report_date, raw_sightings, people, groups, armies,
                    previous_report=None, new_people=None, departed_people=None, existing_people=None, enemies_present=None):
    new_people = new_people or []
    departed_people = departed_people or []
    existing_people = existing_people or []
    enemies_present = enemies_present or []

    lines = [
        '[quote]',
        f'[center][b][size=18]{city.name}[/size]',
        f'Rapporto di dogana/marechaussée del {report_date.strftime("%d/%m/%Y")}[/b][/center]',
        '',
        '[color=darkred][size=14][b][u]MEMORIA E AVVISTAMENTI DEL MARESCIALLO-DOGANIERE DI GUARDIA[/u][/b][/size][/color]',
        '',
        '[quote][b]',
        raw_sightings.strip() or 'Nessun avvistamento segnalato.',
        '[/b][/quote]',
        '',
    ]

    lines.append(f'[color=darkred][size=14][b][u]PERSONE IN LISTA NEMICI[/u] :[/b][/size][/color][color=blue][b]{len(enemies_present)}[/b][/color]')
    lines.append('')
    for enemy in enemies_present:
        enemy_line = f'[color=red][b][char]{enemy.nickname}[/char][/b][/color]'
        if enemy.note:
            enemy_line += f' - [b]Motivo:[/b] {enemy.note}'
        lines.append(enemy_line)
    if not enemies_present:
        lines.append('Nessuna persona in lista nemici presente.')

    lines += ['', '[color=darkred][size=14][b][u]MOVIMENTI RISPETTO ALL’ULTIMO RAPPORTO[/u][/b][/size][/color]', '']
    if previous_report:
        lines.append(f'[b]Rapporto precedente:[/b] {previous_report.report_date.strftime("%d/%m/%Y")}')
        lines.append('')
        lines.append(f'[b]Arrivati:[/b] {len(new_people)}')
        for nickname in new_people:
            lines.append(f'[char]{nickname}[/char]')
        lines.append('')
        lines.append(f'[b]Partiti:[/b] {len(departed_people)}')
        for nickname in departed_people:
            lines.append(f'[char]{nickname}[/char]')
        lines.append('')
        lines.append(f'[b]Già presenti nel rapporto precedente:[/b] {len(existing_people)}')
    else:
        lines.append('Nessun rapporto precedente disponibile per il confronto.')

    lines += [
        '',
        f'[color=darkred][size=14][b][u]PERSONE IN CITTÀ[/u] :[/b][/size][/color][color=blue][b]{len(people)}[/b][/color]',
        '',
    ]
    for p in people:
        lines.append(f'[char]{p["nickname"]}[/char]')

    lines += [
        '',
        '[color=darkred][size=14][b][u]ESERCITI, GRUPPI E LANCE[/u][/b][/size][/color]',
        '',
        '[b][color=darkred]Eserciti:[/color][/b]',
        '',
    ]
    if armies:
        for army in armies:
            lines.append(army['raw'])
    else:
        lines.append('Nessun esercito presente.')

    lines += ['', '[b][color=darkred]Gruppi:[/color][/b]', '']
    if groups:
        for g in groups:
            lines.append(g['raw'])
            if g['access_mode']:
                lines.append(g['access_mode'])
    else:
        lines.append('Nessun gruppo presente.')

    lines += [
        '',
        '[color=darkred][size=14][b][u]NOTE[/u][/b][/size][/color]',
        '',
    ]
    if enemies_present:
        details = []
        for enemy in enemies_present:
            if enemy.note:
                details.append(f'{enemy.nickname} ({enemy.note})')
            else:
                details.append(enemy.nickname)
        lines.append('[color=red][b]ATTENZIONE:[/b][/color] Nel rapporto risultano presenti persone in lista nemici: ' + ', '.join(details) + '.')
    lines.append('[/quote]')
    return '\n'.join(lines)


def authorized_cities_for(user):
    if user.role == ROLE_ADMIN:
        return City.query.order_by(City.name).all()
    if user.role == ROLE_PREFECT and user.province_id:
        return City.query.filter_by(province_id=user.province_id).order_by(City.name).all()
    return [a.city for a in CityAuthorization.query.filter_by(user_id=user.id).all()]


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    provinces = Province.query.order_by(Province.name).all()
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        password = request.form.get('password', '')
        province_id = request.form.get('province_id', type=int)
        if not nickname or not password or not province_id:
            flash('Compila tutti i campi.', 'danger')
        elif User.query.filter(db.func.lower(User.nickname) == nickname.lower()).first():
            flash('Questo nickname è già registrato.', 'danger')
        else:
            user = User(nickname=nickname, role=ROLE_OFFICER, approved=False, requested_province_id=province_id)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Registrazione completata. Il tuo account è in attesa di approvazione.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', provinces=provinces)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter(db.func.lower(User.nickname) == nickname.lower()).first()
        if not user or not user.check_password(password):
            flash('Nickname o password non corretti.', 'danger')
        elif not user.approved and user.role == ROLE_OFFICER:
            flash('Il tuo account è ancora in attesa di approvazione.', 'warning')
        else:
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout effettuato.', 'success')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == ROLE_OFFICER:
        return redirect(url_for('new_report'))
    pending = []
    if current_user.role == ROLE_ADMIN:
        pending = User.query.filter_by(role=ROLE_OFFICER, approved=False).all()
    elif current_user.role == ROLE_PREFECT:
        pending = User.query.filter_by(role=ROLE_OFFICER, approved=False, requested_province_id=current_user.province_id).all()
    cities = authorized_cities_for(current_user)
    return render_template('dashboard.html', pending=pending, cities=cities)


@app.route('/reports/new', methods=['GET', 'POST'])
@login_required
def new_report():
    cities = authorized_cities_for(current_user)
    allowed_ids = {c.id for c in cities}
    if request.method == 'POST':
        city_id = request.form.get('city_id', type=int)
        if city_id not in allowed_ids:
            abort(403)
        if current_user.role == ROLE_OFFICER:
            report_date = date.today()
        else:
            date_str = request.form.get('report_date', '')
            try:
                report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Data non valida.', 'danger')
                return render_template('report_form.html', cities=cities, today=date.today().isoformat())

        if Report.query.filter_by(city_id=city_id, report_date=report_date).first():
            flash('Esiste già un rapporto per questa città e questa data.', 'danger')
            return render_template('report_form.html', cities=cities, today=report_date.isoformat())

        raw_people = request.form.get('people', '')
        raw_groups = request.form.get('groups', '')
        raw_armies = request.form.get('armies', '')
        raw_sightings = request.form.get('sightings', '')
        people = parse_people(raw_people)
        groups = parse_groups(raw_groups)
        armies = parse_armies(raw_armies)
        sightings = parse_sightings(raw_sightings)

        # Do not save a broken report if a citizen list was pasted but none of
        # its rows could be recognized. This makes parser problems visible
        # immediately instead of silently producing a 0-person report.
        if raw_people.strip() and not people:
            flash('Non sono riuscito a riconoscere nessuna persona nella lista incollata. Il rapporto non è stato salvato.', 'danger')
            return render_template(
                'report_form.html',
                cities=cities,
                today=report_date.isoformat(),
                form_data={
                    'city_id': city_id,
                    'people': raw_people,
                    'groups': raw_groups,
                    'armies': raw_armies,
                    'sightings': raw_sightings,
                },
            )

        city = db.session.get(City, city_id)
        previous_report, new_people, departed_people, existing_people = compare_with_previous_report(city_id, report_date, people)
        enemies_present = enemies_present_for(city, people)
        bbcode = generate_bbcode(
            city, report_date, raw_sightings, people, groups, armies,
            previous_report=previous_report,
            new_people=new_people,
            departed_people=departed_people,
            existing_people=existing_people,
            enemies_present=enemies_present,
        )

        import json
        report = Report(
            city_id=city_id,
            author_id=current_user.id,
            report_date=report_date,
            raw_people=raw_people,
            raw_groups=raw_groups,
            raw_armies=raw_armies,
            raw_sightings=raw_sightings,
            parsed_people_json=json.dumps(people, ensure_ascii=False),
            parsed_groups_json=json.dumps(groups, ensure_ascii=False),
            parsed_sightings_json=json.dumps(sightings, ensure_ascii=False),
            bbcode=bbcode,
        )
        db.session.add(report)
        db.session.commit()
        flash('Rapporto creato correttamente.', 'success')
        return redirect(url_for('view_report', report_id=report.id))

    return render_template('report_form.html', cities=cities, today=date.today().isoformat())


@app.route('/reports')
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def reports():
    q = Report.query.join(City)
    if current_user.role == ROLE_PREFECT:
        q = q.filter(City.province_id == current_user.province_id)
    elif current_user.role == ROLE_OFFICER:
        ids = [c.id for c in authorized_cities_for(current_user)]
        q = q.filter(Report.city_id.in_(ids or [-1]))
    items = q.order_by(Report.report_date.desc(), Report.created_at.desc()).all()
    return render_template('reports.html', reports=items)


@app.route('/reports/<int:report_id>')
@login_required
def view_report(report_id):
    report = db.session.get(Report, report_id) or abort(404)
    if current_user.role == ROLE_PREFECT and report.city.province_id != current_user.province_id:
        abort(403)
    if current_user.role == ROLE_OFFICER:
        if report.city_id not in {c.id for c in authorized_cities_for(current_user)}:
            abort(403)
    return render_template('report_view.html', report=report)


@app.route('/reports/<int:report_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def delete_report(report_id):
    report = db.session.get(Report, report_id) or abort(404)
    if current_user.role == ROLE_PREFECT and report.city.province_id != current_user.province_id:
        abort(403)
    city_name = report.city.name
    report_date = report.report_date.strftime('%d/%m/%Y')
    db.session.delete(report)
    db.session.commit()
    flash(f'Rapporto di {city_name} del {report_date} eliminato.', 'success')
    return redirect(url_for('reports'))


@app.route('/enemies', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def enemies():
    preview_names = []
    preview_existing = []
    bulk_text = ''
    selected_province_id = current_user.province_id if current_user.role == ROLE_PREFECT else None

    if request.method == 'POST':
        action = request.form.get('action', 'single')
        if current_user.role == ROLE_PREFECT:
            province_id = current_user.province_id
        else:
            province_id = request.form.get('province_id', type=int)
        selected_province_id = province_id

        if action == 'single':
            nickname = request.form.get('nickname', '').strip()
            note = request.form.get('note', '').strip()
            if not nickname or not province_id:
                flash('Inserisci nickname e provincia.', 'danger')
            else:
                duplicate = Enemy.query.filter(
                    Enemy.province_id == province_id,
                    func.lower(Enemy.nickname) == nickname.lower()
                ).first()
                if duplicate:
                    flash('Questa persona è già presente nella lista nemici della provincia.', 'warning')
                else:
                    db.session.add(Enemy(nickname=nickname, province_id=province_id, note=note))
                    db.session.commit()
                    flash(f'{nickname} aggiunto alla lista nemici.', 'success')
            return redirect(url_for('enemies'))

        if action in {'bulk_preview', 'bulk_import'}:
            bulk_text = request.form.get('bulk_text', '')
            if action == 'bulk_import':
                # The preview is intentionally editable. Empty fields are
                # treated as rows the user chose to discard. As RK nicknames
                # cannot contain spaces, keep only the first token.
                parsed = []
                seen_edited = set()
                for raw_name in request.form.getlist('parsed_names'):
                    cleaned = _clean_enemy_candidate(raw_name)
                    cleaned = cleaned.split()[0] if cleaned.split() else ''
                    if cleaned and cleaned.casefold() not in seen_edited:
                        seen_edited.add(cleaned.casefold())
                        parsed.append(cleaned)
            else:
                parsed = parse_enemy_bulk(bulk_text)

            if not province_id:
                flash('Seleziona una provincia.', 'danger')
            elif not parsed:
                flash('Non sono riuscito a riconoscere alcun nickname nella lista incollata.', 'danger')
            else:
                existing_rows = Enemy.query.filter_by(province_id=province_id).all()
                existing_map = {e.nickname.casefold(): e.nickname for e in existing_rows}
                preview_existing = [n for n in parsed if n.casefold() in existing_map]
                preview_names = [n for n in parsed if n.casefold() not in existing_map]

                if action == 'bulk_import':
                    for nickname in preview_names:
                        db.session.add(Enemy(nickname=nickname, province_id=province_id, note=''))
                    db.session.commit()
                    flash(
                        f'Importazione completata: {len(preview_names)} nuovi nominativi aggiunti, '
                        f'{len(preview_existing)} già presenti ignorati.',
                        'success'
                    )
                    return redirect(url_for('enemies'))

    provinces = Province.query.order_by(Province.name).all() if current_user.role == ROLE_ADMIN else []
    q = Enemy.query.join(Province)
    if current_user.role == ROLE_PREFECT:
        q = q.filter(Enemy.province_id == current_user.province_id)
    items = q.order_by(Province.name, Enemy.nickname).all()
    return render_template(
        'enemies.html', enemies=items, provinces=provinces,
        preview_names=preview_names, preview_existing=preview_existing,
        bulk_text=bulk_text, selected_province_id=selected_province_id
    )


@app.route('/enemies/<int:enemy_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def delete_enemy(enemy_id):
    enemy = db.session.get(Enemy, enemy_id) or abort(404)
    if current_user.role == ROLE_PREFECT and enemy.province_id != current_user.province_id:
        abort(403)
    nickname = enemy.nickname
    db.session.delete(enemy)
    db.session.commit()
    flash(f'{nickname} rimosso dalla lista nemici.', 'success')
    return redirect(url_for('enemies'))


@app.route('/account/password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not current_user.check_password(current_password):
            flash('La password attuale non è corretta.', 'danger')
        elif len(new_password) < 8:
            flash('La nuova password deve contenere almeno 8 caratteri.', 'danger')
        elif new_password != confirm_password:
            flash('Le nuove password non coincidono.', 'danger')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password aggiornata correttamente.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')


@app.route('/users')
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def users():
    if current_user.role == ROLE_ADMIN:
        items = User.query.order_by(User.created_at.desc()).all()
    else:
        items = User.query.filter(
            or_(User.province_id == current_user.province_id, User.requested_province_id == current_user.province_id)
        ).order_by(User.created_at.desc()).all()
    provinces = Province.query.order_by(Province.name).all() if current_user.role == ROLE_ADMIN else []
    return render_template('users.html', users=items, provinces=provinces)


@app.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def approve_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.role != ROLE_OFFICER:
        abort(400)
    if current_user.role == ROLE_PREFECT and user.requested_province_id != current_user.province_id:
        abort(403)
    user.approved = True
    user.province_id = user.requested_province_id
    db.session.commit()
    flash(f'{user.nickname} approvato.', 'success')
    return redirect(request.referrer or url_for('users'))


@app.route('/users/<int:user_id>/reject', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def reject_user(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if current_user.role == ROLE_PREFECT and user.requested_province_id != current_user.province_id:
        abort(403)
    db.session.delete(user)
    db.session.commit()
    flash('Richiesta rifiutata e account eliminato.', 'success')
    return redirect(request.referrer or url_for('users'))


@app.route('/users/<int:user_id>/role', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN)
def set_user_role(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash('Per sicurezza non puoi modificare il ruolo del tuo stesso account da questa schermata.', 'warning')
        return redirect(url_for('users'))

    role = request.form.get('role', '').strip()
    province_id = request.form.get('province_id', type=int)
    if role not in {ROLE_ADMIN, ROLE_PREFECT, ROLE_OFFICER}:
        abort(400)
    if role in {ROLE_PREFECT, ROLE_OFFICER} and not province_id:
        flash('Per Prefetti e Doganieri devi selezionare una provincia.', 'danger')
        return redirect(url_for('users'))
    if province_id and not db.session.get(Province, province_id):
        abort(400)

    CityAuthorization.query.filter_by(user_id=user.id).delete()
    user.role = role
    user.approved = True
    if role == ROLE_ADMIN:
        user.province_id = None
        user.requested_province_id = None
    else:
        user.province_id = province_id
        user.requested_province_id = province_id
    db.session.commit()
    labels = {ROLE_ADMIN: 'Admin Centrale', ROLE_PREFECT: 'Prefetto', ROLE_OFFICER: 'Doganiere'}
    flash(f'Ruolo di {user.nickname} aggiornato a {labels[role]}.', 'success')
    return redirect(url_for('users'))


@app.route('/users/<int:user_id>/authorizations', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_PREFECT)
def user_authorizations(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.role != ROLE_OFFICER:
        abort(400)
    province_id = user.province_id or user.requested_province_id
    if current_user.role == ROLE_PREFECT and province_id != current_user.province_id:
        abort(403)
    cities = City.query.filter_by(province_id=province_id).order_by(City.name).all()
    if request.method == 'POST':
        selected = {int(x) for x in request.form.getlist('city_ids')}
        valid = {c.id for c in cities}
        selected &= valid
        CityAuthorization.query.filter_by(user_id=user.id).delete()
        for city_id in selected:
            db.session.add(CityAuthorization(user_id=user.id, city_id=city_id))
        db.session.commit()
        flash('Autorizzazioni aggiornate.', 'success')
        return redirect(url_for('users'))
    current = {a.city_id for a in CityAuthorization.query.filter_by(user_id=user.id).all()}
    return render_template('authorizations.html', user=user, cities=cities, current=current)


@app.route('/admin/locations', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN)
def locations():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'province':
            name = request.form.get('province_name', '').strip()
            if name and not Province.query.filter(db.func.lower(Province.name) == name.lower()).first():
                db.session.add(Province(name=name))
                db.session.commit()
                flash('Provincia creata.', 'success')
        elif action == 'city':
            name = request.form.get('city_name', '').strip()
            province_id = request.form.get('province_id', type=int)
            if name and province_id:
                db.session.add(City(name=name, province_id=province_id))
                try:
                    db.session.commit()
                    flash('Città creata.', 'success')
                except Exception:
                    db.session.rollback()
                    flash('Questa città esiste già nella provincia selezionata.', 'danger')
    provinces = Province.query.order_by(Province.name).all()
    cities = City.query.order_by(City.name).all()
    return render_template('locations.html', provinces=provinces, cities=cities)


@app.cli.command('seed')
def seed():
    db.create_all()
    if Province.query.count() == 0:
        firenze = Province(name='Repubblica Fiorentina')
        siena = Province(name='Repubblica di Siena')
        db.session.add_all([firenze, siena])
        db.session.flush()
        db.session.add_all([
            City(name='Firenze', province_id=firenze.id),
            City(name='Pisa', province_id=firenze.id),
            City(name='Piombino', province_id=firenze.id),
            City(name='Siena', province_id=siena.id),
        ])
        db.session.commit()
    firenze = Province.query.filter_by(name='Repubblica Fiorentina').first()
    if not User.query.filter_by(nickname='admin').first():
        admin = User(nickname='admin', role=ROLE_ADMIN, approved=True)
        admin.set_password('admin123!')
        db.session.add(admin)
    if not User.query.filter_by(nickname='prefetto_demo').first():
        u = User(nickname='prefetto_demo', role=ROLE_PREFECT, approved=True, province_id=firenze.id)
        u.set_password('demo123!')
        db.session.add(u)
    if not User.query.filter_by(nickname='doganiere_demo').first():
        u = User(nickname='doganiere_demo', role=ROLE_OFFICER, approved=True, province_id=firenze.id, requested_province_id=firenze.id)
        u.set_password('demo123!')
        db.session.add(u)
        db.session.flush()
        city = City.query.filter_by(name='Firenze', province_id=firenze.id).first()
        db.session.add(CityAuthorization(user_id=u.id, city_id=city.id))
    if not User.query.filter_by(nickname='in_attesa_demo').first():
        u = User(nickname='in_attesa_demo', role=ROLE_OFFICER, approved=False, requested_province_id=firenze.id)
        u.set_password('demo123!')
        db.session.add(u)
    db.session.commit()
    print('Dati demo creati.')
    print('Admin: admin / admin123!')
    print('Prefetto: prefetto_demo / demo123!')
    print('Doganiere: doganiere_demo / demo123!')


with app.app_context():
    db.create_all()
    bootstrap_password = os.environ.get('BOOTSTRAP_ADMIN_PASSWORD')
    if bootstrap_password and not User.query.filter(func.lower(User.nickname) == os.environ.get('BOOTSTRAP_ADMIN_NICKNAME', 'admin').lower()).first():
        bootstrap_nickname = os.environ.get('BOOTSTRAP_ADMIN_NICKNAME', 'admin').strip() or 'admin'
        bootstrap_admin = User(nickname=bootstrap_nickname, role=ROLE_ADMIN, approved=True)
        bootstrap_admin.set_password(bootstrap_password)
        db.session.add(bootstrap_admin)
        db.session.commit()


if __name__ == '__main__':
    app.run(debug=True)
