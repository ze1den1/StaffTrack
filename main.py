import hashlib
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from sqlalchemy import func, or_, extract

from data.db_models.db_session import global_init, create_session
from data.db_models.shifts import Shift
from data.db_models.users import User

ITEMS_PER_PAGE = 15

app = Flask(__name__)
app.config['SECRET_KEY'] = 'BE.shXML#QvZmqj"7b@n'

login_manager = LoginManager()
login_manager.init_app(app)


def paginate(query, page, per_page=ITEMS_PER_PAGE):
    """Ручная реализация пагинации для SQLAlchemy запроса"""
    total_items = query.count()
    total_pages = (total_items + per_page - 1) // per_page

    if page < 1:
        page = 1
    elif page > total_pages > 0:
        page = total_pages

    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()

    return {
        'items': items,
        'page': page,
        'total_pages': total_pages,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'prev_num': page - 1 if page > 1 else None,
        'next_num': page + 1 if page < total_pages else None
    }


@login_manager.user_loader
def load_user(user_id):
    db_sess = create_session()
    return db_sess.get(User, user_id)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


@app.route('/')
def index():
    current_shift = None
    session = create_session()

    if current_user.is_authenticated and current_user.role == 'worker':
        current_shift = session.query(Shift).filter_by(
            user_id=current_user.id,
            end_time=None
        ).first()
    return render_template('index.html', current_shift=current_shift)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        session = create_session()

        user = session.query(User).filter_by(username=username).first()

        if user and hashlib.md5(password.encode()).digest() == user.hashed_password:
            login_user(user)
            flash('Вы успешно вошли в систему!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'danger')

    return render_template('login.html')


@app.route('/start_shift', methods=['POST'])
@login_required
def start_shift():
    session = create_session()

    if current_user.role != 'worker':
        flash('Эта функция доступна только сотрудникам', 'danger')
        return redirect(url_for('index'))

    active_shift = session.query(Shift).filter_by(user_id=current_user.id, end_time=None).first()
    if active_shift:
        flash('У вас уже есть активная смена', 'warning')
        return redirect(url_for('index'))

    new_shift = Shift(
        user_id=current_user.id,
        start_time=datetime.now()
    )

    session.add(new_shift)
    session.commit()

    flash('Смена успешно открыта!', 'success')
    return redirect(url_for('index'))


@app.route('/end_shift', methods=['POST'])
@login_required
def end_shift():
    session = create_session()

    if current_user.role != 'worker':
        flash('Эта функция доступна только сотрудникам', 'danger')
        return redirect(url_for('index'))

    active_shift = session.query(Shift).filter_by(user_id=current_user.id, end_time=None).first()
    if not active_shift:
        flash('У вас нет активной смены', 'warning')
        return redirect(url_for('index'))

    active_shift.end_time = datetime.now()
    duration = (active_shift.end_time - active_shift.start_time).total_seconds() / 3600
    active_shift.duration = round(duration, 2)

    session.commit()

    flash(f'Смена успешно закрыта! Отработано: {active_shift.duration} час(-ов)', 'success')
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    session = create_session()

    total_shifts = len(current_user.shifts)
    total_hours = sum(s.duration or 0 for s in current_user.shifts if s.duration)

    current_shift = None
    current_duration = 0
    if current_user.role == 'worker':
        current_shift = session.query(Shift).filter_by(
            user_id=current_user.id,
            end_time=None
        ).first()
        if current_shift:
            current_duration = (datetime.now() - current_shift.start_time).total_seconds() / 3600

    recent_shifts = current_user.shifts[-5:] if current_user.shifts else []

    return render_template('profile.html',
                           total_shifts=total_shifts,
                           total_hours=total_hours,
                           current_shift=current_shift,
                           current_duration=current_duration,
                           recent_shifts=recent_shifts)


@app.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    if request.method == 'POST':
        session = create_session()

        name = request.form.get('name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        department = request.form.get('department')
        post = request.form.get('post')

        user = session.query(User).filter(User.id == current_user.id).first()

        user.name = name
        user.email = email if email else None
        user.phone_number = phone_number if phone_number else None

        if current_user.role == 'worker':
            user.department = department if department else None
            user.post = post if post else None

        session.commit()

        flash('Данные профиля успешно обновлены!', 'success')
        return redirect(url_for('profile'))

    return redirect(url_for('profile'))


@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    if request.method == 'POST':
        session = create_session()

        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_new_password')

        user = session.query(User).filter(User.id == current_user.id).first()

        if not user.hashed_password == hashlib.md5(current_password.encode()).digest():
            flash('Текущий пароль неверен', 'danger')
            return redirect(url_for('profile'))

        if new_password != confirm_password:
            flash('Новые пароли не совпадают', 'danger')
            return redirect(url_for('profile'))

        if len(new_password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'danger')
            return redirect(url_for('profile'))

        user.hashed_password = hashlib.md5(new_password.encode()).digest()
        session.commit()

        flash('Пароль успешно изменен!', 'success')
        return redirect(url_for('profile'))

    return redirect(url_for('profile'))


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    total_workers = session.query(User).filter_by(role='worker').count()
    active_shifts = session.query(Shift).filter_by(end_time=None).count()

    today = datetime.now().date()
    total_shifts_today = session.query(Shift).filter(
        func.date(Shift.start_time) == today
    ).count()

    completed_shifts = session.query(Shift).filter(Shift.end_time.isnot(None)).all()
    avg_hours = 0
    if completed_shifts:
        avg_hours = sum(s.duration or 0 for s in completed_shifts) / len(completed_shifts)

    current_shifts = session.query(Shift).filter_by(end_time=None).all()

    recent_activities = [
        {'icon': 'user-plus', 'message': 'Добавлен новый сотрудник: Петров Петр', 'time': datetime.now()},
        {'icon': 'door-open', 'message': 'Иванов Иван открыл смену', 'time': datetime.now()},
        {'icon': 'door-closed', 'message': 'Сидоров Сидор закрыл смену (8.5 ч)', 'time': datetime.now()},
    ]

    return render_template('admin_dashboard.html',
                           total_workers=total_workers,
                           active_shifts=active_shifts,
                           total_shifts_today=total_shifts_today,
                           avg_hours=round(avg_hours, 1),
                           current_shifts=current_shifts,
                           recent_activities=recent_activities)


@app.route('/workers')
@login_required
def view_workers():
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')

    query = session.query(User)

    if search:
        query = query.filter(
            or_(
                User.name.ilike(f'%{search}%'),
                User.username.ilike(f'%{search}%')
            )
        )

    if role_filter:
        query = query.filter_by(role=role_filter)

    pagination = paginate(query.order_by(User.created_at.desc()), page)

    return render_template('view_workers.html',
                           workers=pagination['items'],
                           page=pagination['page'],
                           total_pages=pagination['total_pages'],
                           has_prev=pagination['has_prev'],
                           has_next=pagination['has_next'],
                           prev_num=pagination['prev_num'],
                           next_num=pagination['next_num'],
                           search_query=search,
                           role_filter=role_filter)


@app.route('/workers/<int:user_id>')
@login_required
def view_worker(user_id):
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    worker = session.query(User).get(user_id)

    total_shifts = len(worker.shifts)
    total_hours = sum(s.duration or 0 for s in worker.shifts if s.duration)

    avg_duration = 0
    completed_shifts = [s for s in worker.shifts if s.duration]
    if completed_shifts:
        avg_duration = sum(s.duration for s in completed_shifts) / len(completed_shifts)

    active_shift = session.query(Shift).filter_by(user_id=worker.id, end_time=None).first()
    current_duration = 0
    if active_shift:
        current_duration = (datetime.now() - active_shift.start_time).total_seconds() / 3600

    now = datetime.now()
    month_shifts = session.query(Shift).filter(
        Shift.user_id == worker.id,
        extract('month', Shift.start_time) == now.month,
        extract('year', Shift.start_time) == now.year
    ).count()

    month_hours = sum(
        s.duration or 0 for s in session.query(Shift).filter(
            Shift.user_id == worker.id,
            extract('month', Shift.start_time) == now.month,
            extract('year', Shift.start_time) == now.year
        ).all() if s.duration
    )

    last_shift = session.query(Shift).filter_by(user_id=worker.id).order_by(Shift.start_time.desc()).first()
    last_shift_date = last_shift.start_time.strftime('%d.%m.%Y') if last_shift else None

    longest_shift = max([s.duration or 0 for s in worker.shifts], default=0)

    recent_shifts = worker.shifts[-5:] if worker.shifts else []

    return render_template('view_worker.html',
                           worker=worker,
                           total_shifts=total_shifts,
                           total_hours=total_hours,
                           avg_duration=avg_duration,
                           active_shift=active_shift,
                           current_duration=current_duration,
                           month_shifts=month_shifts,
                           month_hours=month_hours,
                           last_shift_date=last_shift_date,
                           longest_shift=longest_shift,
                           recent_shifts=recent_shifts)


@app.route('/workers/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_worker(user_id):
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    worker = session.query(User).get(user_id)

    if request.method == 'POST':
        worker.name = request.form.get('name')
        worker.username = request.form.get('username')
        worker.role = request.form.get('role')

        worker.email = request.form.get('email') or None
        worker.phone_number = request.form.get('phone_number') or None
        if worker.role == 'worker':
            worker.department = request.form.get('department') or None
            worker.post = request.form.get('post') or None

        new_password = request.form.get('new_password')
        if new_password:
            if len(new_password) < 6:
                flash('Пароль должен содержать минимум 6 символов', 'danger')
                return redirect(url_for('edit_worker', user_id=user_id))

            confirm_password = request.form.get('confirm_password')
            if new_password != confirm_password:
                flash('Пароли не совпадают', 'danger')
                return redirect(url_for('edit_worker', user_id=user_id))

            worker.password = hashlib.md5(new_password.encode()).digest()
            flash('Пароль успешно изменен', 'success')

        session.commit()
        flash('Данные сотрудника обновлены!', 'success')
        return redirect(url_for('view_worker', user_id=user_id))

    return render_template('edit_worker.html', worker=worker)


@app.route('/workers/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_worker(user_id):
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    worker = session.query(User).get(user_id)

    if worker.id == current_user.id:
        flash('Вы не можете удалить свою собственную учетную запись', 'danger')
        return redirect(url_for('view_worker', user_id=user_id))

    session.query(Shift).filter_by(user_id=user_id).delete()

    session.delete(worker)
    session.commit()

    flash(f'Сотрудник {worker.name} успешно удален', 'success')
    return redirect(url_for('view_workers'))


@app.route('/shifts')
@login_required
def view_shifts():
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    status_filter = request.args.get('status', '')

    query = session.query(Shift).join(User)

    if user_filter:
        query = query.filter(Shift.user_id == user_filter)

    if date_from:
        query = query.filter(func.date(Shift.start_time) >= date_from)

    if date_to:
        query = query.filter(func.date(Shift.start_time) <= date_to)

    if status_filter == 'active':
        query = query.filter(Shift.end_time.is_(None))
    elif status_filter == 'completed':
        query = query.filter(Shift.end_time.isnot(None))

    shifts = paginate(query.order_by(Shift.start_time.desc()), page)

    total_hours = sum(s.duration or 0 for s in shifts['items'] if s.duration)
    avg_duration = 0
    if shifts['items']:
        completed = [s for s in shifts['items'] if s.duration]
        if completed:
            avg_duration = sum(s.duration for s in completed) / len(completed)

    active_shifts_count = session.query(Shift).filter_by(end_time=None).count()

    return render_template('view_shifts.html',
                           shifts=shifts['items'],
                           all_users=session.query(User).all(),
                           user_filter=user_filter,
                           date_from=date_from,
                           date_to=date_to,
                           status_filter=status_filter,
                           page=page,
                           total_pages=shifts['total_pages'],
                           total_hours=total_hours,
                           avg_duration=avg_duration,
                           active_shifts_count=active_shifts_count)


@app.route('/shifts/<int:shift_id>')
@login_required
def view_shift(shift_id):
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    shift = session.query(Shift).get(shift_id)

    current_duration = 0
    current_time = datetime.now()
    if not shift.end_time:
        current_duration = (current_time - shift.start_time).total_seconds() / 3600

    return render_template('view_shift.html',
                           shift=shift,
                           current_duration=current_duration,
                           current_time=current_time)


@app.route('/shifts/<int:shift_id>/end', methods=['POST'])
@login_required
def admin_end_shift(shift_id):
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    shift = session.query(Shift).get(shift_id)

    if shift.end_time:
        flash('Эта смена уже завершена', 'warning')
        return redirect(url_for('view_shift', shift_id=shift_id))

    shift.end_time = datetime.now()
    duration = (shift.end_time - shift.start_time).total_seconds() / 3600
    shift.duration = round(duration, 2)

    session.commit()

    flash(f'Смена сотрудника {shift.user.name} завершена. Отработано: {shift.duration} часов', 'success')
    return redirect(url_for('view_shift', shift_id=shift_id))


@app.route('/reports')
@login_required
def reports():
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    period = request.args.get('period', 'month')
    user_filter = request.args.get('user', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    # TODO: Здесь должна быть логика расчета статистики за период
    # TODO: Это примерные данные для демонстрации

    return render_template('reports.html',
                           period=period,
                           user_filter=user_filter,
                           start_date=start_date,
                           end_date=end_date,
                           all_users=session.query(User).all(),
                           total_hours=156.5,
                           shift_count=24,
                           avg_duration=6.5,
                           max_duration=10.2,
                           min_duration=3.1,
                           top_workers=[
                               {'user': session.query(User).get(2), 'total_hours': 45.5, 'shift_count': 7},
                               {'user': session.query(User).get(3), 'total_hours': 38.2, 'shift_count': 6},
                               {'user': session.query(User).get(4), 'total_hours': 32.8, 'shift_count': 5},
                           ],
                           day_stats=[
                               {'day': 'Понедельник', 'hours': 22.5},
                               {'day': 'Вторник', 'hours': 24.3},
                               {'day': 'Среда', 'hours': 20.1},
                               {'day': 'Четверг', 'hours': 25.8},
                               {'day': 'Пятница', 'hours': 23.9},
                               {'day': 'Суббота', 'hours': 15.2},
                               {'day': 'Воскресенье', 'hours': 10.7},
                           ],
                           max_day_hours=25.8)


@app.route('/workers/add', methods=['GET', 'POST'])
@login_required
def add_worker():
    session = create_session()

    if current_user.role != 'admin':
        flash('Доступ запрещен', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        role = request.form.get('role')

        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('add_worker'))

        if session.query(User).filter_by(username=username).first():
            flash('Пользователь с таким логином уже существует', 'danger')
            return redirect(url_for('add_worker'))

        new_user = User(
            username=username,
            hashed_password=hashlib.md5(password.encode()).digest(),
            name=name,
            role=role
        )

        session.add(new_user)
        session.commit()

        flash(f'Сотрудник {name} успешно добавлен!', 'success')
        return redirect(url_for('view_workers'))

    return render_template('add_worker.html')


@app.route('/my_shifts')
@login_required
def my_shifts():
    session = create_session()

    if current_user.role != 'worker':
        flash('Эта страница доступна только сотрудникам', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    month = request.args.get('month', datetime.now().month, type=int)
    year = request.args.get('year', datetime.now().year, type=int)

    query = session.query(Shift).filter(
        Shift.user_id == current_user.id,
        extract('month', Shift.start_time) == month,
        extract('year', Shift.start_time) == year
    )

    shifts = paginate(query.order_by(Shift.start_time.desc()), page)

    current_month_shifts = session.query(Shift).filter(
        Shift.user_id == current_user.id,
        extract('month', Shift.start_time) == datetime.now().month,
        extract('year', Shift.start_time) == datetime.now().year
    ).count()

    current_month_hours = sum(
        s.duration or 0 for s in session.query(Shift).filter(
            Shift.user_id == current_user.id,
            extract('month', Shift.start_time) == datetime.now().month,
            extract('year', Shift.start_time) == datetime.now().year
        ).all() if s.duration
    )

    avg_duration = 0
    completed_shifts = [s for s in shifts['items'] if s.duration]
    if completed_shifts:
        avg_duration = sum(s.duration for s in completed_shifts) / len(completed_shifts)

    current_shift = session.query(Shift).filter_by(
        user_id=current_user.id,
        end_time=None
    ).first()

    months = []
    for i in range(1, 13):
        months.append({
            'value': i,
            'name': ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                     'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'][i - 1],
            'selected': i == month
        })

    current_year = datetime.now().year
    years = list(range(current_year - 4, current_year + 1))

    return render_template('my_shifts.html',
                           shifts=shifts['items'],
                           page=page,
                           total_pages=shifts['total_pages'],
                           selected_month=month,
                           selected_year=year,
                           months=months,
                           years=years,
                           current_month_shifts=current_month_shifts,
                           current_month_hours=current_month_hours,
                           avg_duration=avg_duration,
                           current_shift=current_shift)


def create_tables():
    session = create_session()

    with app.app_context():
        if not session.query(User).filter_by(username='admin').first():
            admin = User(
                username='admin',
                hashed_password=hashlib.md5('admin123'.encode()).digest(),
                name='Администратор',
                role='admin'
            )
            session.add(admin)

            worker = User(
                username='worker1',
                hashed_password=hashlib.md5('worker123'.encode()).digest(),
                name='Иванов Иван',
                role='worker'
            )
            session.add(worker)
            worker = User(
                username='worker2',
                hashed_password=hashlib.md5('worker123'.encode()).digest(),
                name='Кириллов Кирилл',
                role='worker'
            )
            session.add(worker)
            worker = User(
                username='worker3',
                hashed_password=hashlib.md5('worker123'.encode()).digest(),
                name='Петров Петр',
                role='worker'
            )
            session.add(worker)

            session.commit()


if __name__ == '__main__':
    global_init('db/database.db')
    create_tables()
    app.run('127.0.0.1', 500, debug=True)
