from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import sqlite3, os, random, time, hashlib, functools

app = Flask(__name__)
app.secret_key = 'tracer-alumni-secret-2024-umm'

BASE_DIR    = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_PATH     = os.path.join(INSTANCE_DIR, 'alumni_system.db')
os.makedirs(INSTANCE_DIR, exist_ok=True)

if os.path.exists(DB_PATH):
    try: os.chmod(DB_PATH, 0o664)
    except: pass

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS alumni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL, nim TEXT,
            tahun_masuk INTEGER, tanggal_lulus TEXT,
            fakultas TEXT, prodi TEXT,
            universitas TEXT DEFAULT 'Universitas Muhammadiyah Malang',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tracer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumni_id INTEGER NOT NULL,
            linkedin TEXT, instagram TEXT, facebook TEXT, tiktok TEXT,
            email TEXT, no_hp TEXT,
            tempat_bekerja TEXT, alamat_bekerja TEXT,
            posisi TEXT, jenis_pekerjaan TEXT, sosmed_tempat_bekerja TEXT,
            status TEXT DEFAULT 'Belum Dilacak',
            traced_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (alumni_id) REFERENCES alumni(id)
        );
        CREATE INDEX IF NOT EXISTS idx_alumni_nama     ON alumni(nama);
        CREATE INDEX IF NOT EXISTS idx_alumni_fakultas ON alumni(fakultas);
        CREATE INDEX IF NOT EXISTS idx_tracer_id       ON tracer(alumni_id);
        """)
        # default admin
        conn.execute("INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)",
                     ('admin', hash_pw('admin123'), 'admin'))

# ═══════ AUTH ════════════════════════════════════════

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        uname = request.form.get('username','').strip()
        pw    = request.form.get('password','')
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND password_hash=?",
                                (uname, hash_pw(pw))).fetchone()
        if user:
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['role']     = user['role']
            return redirect(url_for('index'))
        error = 'Username atau password salah.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ═══════ DASHBOARD ════════════════════════════════════

@app.route('/')
@login_required
def index():
    with get_db() as conn:
        ta  = conn.execute("SELECT COUNT(*) FROM alumni").fetchone()[0]
        td  = conn.execute("SELECT COUNT(DISTINCT alumni_id) FROM tracer WHERE status='Ditemukan'").fetchone()[0]
        tb  = conn.execute("SELECT COUNT(DISTINCT alumni_id) FROM tracer WHERE status='Tidak Ditemukan'").fetchone()[0]
        fak = conn.execute("SELECT fakultas, COUNT(*) c FROM alumni WHERE fakultas IS NOT NULL GROUP BY fakultas ORDER BY c DESC LIMIT 8").fetchall()
        jp  = conn.execute("SELECT jenis_pekerjaan, COUNT(*) c FROM tracer WHERE status='Ditemukan' AND jenis_pekerjaan IS NOT NULL GROUP BY jenis_pekerjaan").fetchall()
        recent = conn.execute("""
            SELECT a.nama, a.prodi, a.fakultas, t.status, t.tempat_bekerja, t.posisi, t.traced_at
            FROM tracer t JOIN alumni a ON t.alumni_id=a.id
            ORDER BY t.traced_at DESC LIMIT 8""").fetchall()
    return render_template('index.html', total_alumni=ta, total_ditemukan=td, total_tidak=tb,
                           fak_stats=fak, jp_stats=jp, recent=recent)

# ═══════ ALUMNI LIST ══════════════════════════════════

@app.route('/alumni')
@login_required
def alumni_list():
    q    = request.args.get('q','')
    fak  = request.args.get('fakultas','')
    prodi= request.args.get('prodi','')
    stat = request.args.get('status','')
    page = max(1, int(request.args.get('page', 1)))
    per_page = 50

    sql  = "SELECT a.*, t.status as t_status FROM alumni a LEFT JOIN tracer t ON a.id=t.alumni_id WHERE 1=1"
    params = []
    if q:     sql += " AND a.nama LIKE ?";     params.append(f'%{q}%')
    if fak:   sql += " AND a.fakultas=?";      params.append(fak)
    if prodi: sql += " AND a.prodi=?";         params.append(prodi)
    if stat == 'ditemukan':       sql += " AND t.status='Ditemukan'"
    elif stat == 'tidak':         sql += " AND t.status='Tidak Ditemukan'"
    elif stat == 'belum':         sql += " AND t.status IS NULL"

    with get_db() as conn:
        total_rows = conn.execute(f"SELECT COUNT(*) FROM ({sql})", params).fetchone()[0]
        rows = conn.execute(sql + f" ORDER BY a.nama LIMIT {per_page} OFFSET {(page-1)*per_page}", params).fetchall()
        fakults = conn.execute("SELECT DISTINCT fakultas FROM alumni WHERE fakultas IS NOT NULL ORDER BY fakultas").fetchall()
        prodis  = conn.execute("SELECT DISTINCT prodi FROM alumni WHERE prodi IS NOT NULL ORDER BY prodi").fetchall()

    total_pages = (total_rows + per_page - 1) // per_page
    return render_template('alumni.html', alumni=rows, fakults=fakults, prodis=prodis,
                           q=q, fak_filter=fak, prodi_filter=prodi, stat_filter=stat,
                           page=page, total_pages=total_pages, total_rows=total_rows, per_page=per_page)

@app.route('/alumni/add', methods=['GET','POST'])
@login_required
def add_alumni():
    if request.method == 'POST':
        d = request.form
        with get_db() as conn:
            conn.execute("""INSERT INTO alumni (nama,nim,tahun_masuk,tanggal_lulus,fakultas,prodi,universitas)
                            VALUES (?,?,?,?,?,?,?)""",
                (d['nama'], d.get('nim'), d.get('tahun_masuk') or None,
                 d.get('tanggal_lulus'), d.get('fakultas'), d.get('prodi'),
                 d.get('universitas','Universitas Muhammadiyah Malang')))
        flash('Alumni berhasil ditambahkan', 'success')
        return redirect(url_for('alumni_list'))
    with get_db() as conn:
        fakults = conn.execute("SELECT DISTINCT fakultas FROM alumni WHERE fakultas IS NOT NULL ORDER BY fakultas").fetchall()
        prodis  = conn.execute("SELECT DISTINCT prodi FROM alumni WHERE prodi IS NOT NULL ORDER BY prodi").fetchall()
    return render_template('add_alumni.html', fakults=fakults, prodis=prodis)

@app.route('/alumni/<int:id>/detail')
@login_required
def alumni_detail(id):
    with get_db() as conn:
        a = conn.execute("SELECT * FROM alumni WHERE id=?", (id,)).fetchone()
        t = conn.execute("SELECT * FROM tracer WHERE alumni_id=? ORDER BY traced_at DESC LIMIT 1", (id,)).fetchone()
    if not a: return "Not found", 404
    return render_template('detail.html', a=a, t=t)

@app.route('/alumni/<int:id>/edit-tracer', methods=['POST'])
@login_required
def edit_tracer(id):
    d = request.form
    with get_db() as conn:
        conn.execute("DELETE FROM tracer WHERE alumni_id=?", (id,))
        conn.execute("""INSERT INTO tracer
            (alumni_id,linkedin,instagram,facebook,tiktok,email,no_hp,
             tempat_bekerja,alamat_bekerja,posisi,jenis_pekerjaan,sosmed_tempat_bekerja,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (id, d.get('linkedin'), d.get('instagram'), d.get('facebook'), d.get('tiktok'),
             d.get('email'), d.get('no_hp'), d.get('tempat_bekerja'), d.get('alamat_bekerja'),
             d.get('posisi'), d.get('jenis_pekerjaan'), d.get('sosmed_tempat_bekerja'),
             'Ditemukan'))
    return jsonify({'success': True})

@app.route('/alumni/delete/<int:id>', methods=['POST'])
@login_required
def delete_alumni(id):
    with get_db() as conn:
        conn.execute("DELETE FROM tracer WHERE alumni_id=?", (id,))
        conn.execute("DELETE FROM alumni WHERE id=?", (id,))
    return jsonify({'success': True})

# ═══════ TRACER ════════════════════════════════════════

PLATFORMS = ['LinkedIn','Instagram','Facebook','TikTok']
FAKE_JOBS  = ['Software Engineer','Data Scientist','Dosen','Product Manager','Peneliti',
              'Software Developer','ML Engineer','Konsultan','Backend Developer',
              'Analis','Guru','Dokter','Perawat','Akuntan','Pengacara','Wirausaha']
COMPANIES  = ['Tokopedia','Gojek','ITS','Traveloka','BRIN','Bukalapak','Shopee',
              'Accenture','Telkom','BCA','Unair','UI','Blibli','Startup Lokal',
              'Pemerintah Kota','Rumah Sakit Umum','SMA Negeri','Bank Mandiri']
LOCATIONS  = ['Surabaya','Jakarta','Bandung','Malang','Yogyakarta','Bali','Semarang','Singapore','Sidoarjo']
JP_TYPES   = ['PNS','Swasta','Wirausaha']
RATES      = {'LinkedIn':.45,'Instagram':.40,'Facebook':.35,'TikTok':.30}

def simulasi_cari(target):
    time.sleep(random.uniform(0.02, 0.08))
    slug = target['nama'].lower().replace(' ','-')
    result = {'nama': target['nama']}
    found_any = False
    # social media
    for plat in PLATFORMS:
        if random.random() < RATES[plat]:
            if plat == 'LinkedIn':    result['linkedin']  = f'https://linkedin.com/in/{slug}'
            elif plat == 'Instagram': result['instagram'] = f'https://instagram.com/{slug.replace("-","_")}'
            elif plat == 'Facebook':  result['facebook']  = f'https://facebook.com/{slug}'
            elif plat == 'TikTok':    result['tiktok']    = f'https://tiktok.com/@{slug.replace("-","_")}'
            found_any = True
    # contact
    if random.random() < 0.35:
        result['email']  = f'{slug.replace("-",".")}@gmail.com'
        found_any = True
    if random.random() < 0.28:
        result['no_hp']  = f'08{random.randint(100000000,999999999)}'
        found_any = True
    # work
    if random.random() < 0.55:
        co = random.choice(COMPANIES)
        result['tempat_bekerja']  = co
        result['alamat_bekerja']  = f'{random.choice(LOCATIONS)}, Indonesia'
        result['posisi']          = random.choice(FAKE_JOBS)
        result['jenis_pekerjaan'] = random.choice(JP_TYPES)
        cslug = co.lower().replace(' ','-')
        result['sosmed_tempat_bekerja'] = f'https://linkedin.com/company/{cslug}'
        found_any = True
    return result, found_any

@app.route('/tracer')
@login_required
def tracer():
    with get_db() as conn:
        history = conn.execute("""SELECT a.nama, t.status, t.posisi, t.tempat_bekerja, t.traced_at
            FROM tracer t JOIN alumni a ON t.alumni_id=a.id
            ORDER BY t.traced_at DESC LIMIT 20""").fetchall()
        total_alumni = conn.execute("SELECT COUNT(*) FROM alumni").fetchone()[0]
    return render_template('tracer.html', history=history, total_alumni=total_alumni)

@app.route('/api/search-alumni')
@login_required
def search_alumni_api():
    q = request.args.get('q','').strip()
    if len(q) < 2:
        return jsonify([])
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nama, prodi, fakultas, nim FROM alumni WHERE nama LIKE ? LIMIT 15",
            (f'%{q}%',)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/trace/<int:alumni_id>', methods=['POST'])
@login_required
def trace_alumni(alumni_id):
    with get_db() as conn:
        alumni = conn.execute("SELECT * FROM alumni WHERE id=?", (alumni_id,)).fetchone()
    if not alumni: return jsonify({'error':'Not found'}), 404
    result, found = simulasi_cari(dict(alumni))
    status = 'Ditemukan' if found else 'Tidak Ditemukan'
    with get_db() as conn:
        conn.execute("DELETE FROM tracer WHERE alumni_id=?", (alumni_id,))
        conn.execute("""INSERT INTO tracer
            (alumni_id,linkedin,instagram,facebook,tiktok,email,no_hp,
             tempat_bekerja,alamat_bekerja,posisi,jenis_pekerjaan,sosmed_tempat_bekerja,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (alumni_id,
             result.get('linkedin'), result.get('instagram'),
             result.get('facebook'), result.get('tiktok'),
             result.get('email'), result.get('no_hp'),
             result.get('tempat_bekerja'), result.get('alamat_bekerja'),
             result.get('posisi'), result.get('jenis_pekerjaan'),
             result.get('sosmed_tempat_bekerja'), status))
    return jsonify({'status': status, 'alumni': alumni['nama'], 'data': result})

@app.route('/api/trace-batch', methods=['POST'])
@login_required
def trace_batch():
    ids = request.json.get('ids', [])
    results = []
    with get_db() as conn:
        for aid in ids[:50]:  # max 50 per batch
            alumni = conn.execute("SELECT * FROM alumni WHERE id=?", (aid,)).fetchone()
            if not alumni: continue
            result, found = simulasi_cari(dict(alumni))
            status = 'Ditemukan' if found else 'Tidak Ditemukan'
            conn.execute("DELETE FROM tracer WHERE alumni_id=?", (aid,))
            conn.execute("""INSERT INTO tracer
                (alumni_id,linkedin,instagram,facebook,tiktok,email,no_hp,
                 tempat_bekerja,alamat_bekerja,posisi,jenis_pekerjaan,sosmed_tempat_bekerja,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (aid, result.get('linkedin'), result.get('instagram'),
                 result.get('facebook'), result.get('tiktok'),
                 result.get('email'), result.get('no_hp'),
                 result.get('tempat_bekerja'), result.get('alamat_bekerja'),
                 result.get('posisi'), result.get('jenis_pekerjaan'),
                 result.get('sosmed_tempat_bekerja'), status))
            results.append({'id': aid, 'nama': alumni['nama'], 'status': status})
    return jsonify({'results': results, 'count': len(results)})

# ═══════ LAPORAN ═══════════════════════════════════════

@app.route('/laporan')
@login_required
def laporan():
    with get_db() as conn:
        ta  = conn.execute("SELECT COUNT(*) FROM alumni").fetchone()[0]
        td  = conn.execute("SELECT COUNT(DISTINCT alumni_id) FROM tracer WHERE status='Ditemukan'").fetchone()[0]
        fak = conn.execute("SELECT fakultas, COUNT(*) c FROM alumni WHERE fakultas IS NOT NULL GROUP BY fakultas ORDER BY c DESC").fetchall()
        jp  = conn.execute("SELECT jenis_pekerjaan, COUNT(*) c FROM tracer WHERE status='Ditemukan' AND jenis_pekerjaan IS NOT NULL GROUP BY jenis_pekerjaan").fetchall()
        pos = conn.execute("SELECT posisi, COUNT(*) c FROM tracer WHERE status='Ditemukan' AND posisi IS NOT NULL GROUP BY posisi ORDER BY c DESC LIMIT 10").fetchall()
        lok = conn.execute("SELECT alamat_bekerja, COUNT(*) c FROM tracer WHERE status='Ditemukan' AND alamat_bekerja IS NOT NULL GROUP BY alamat_bekerja ORDER BY c DESC LIMIT 8").fetchall()
        prodi_stat = conn.execute("SELECT prodi, COUNT(*) c FROM alumni WHERE prodi IS NOT NULL GROUP BY prodi ORDER BY c DESC LIMIT 10").fetchall()
    return render_template('laporan.html', total_alumni=ta, total_ditemukan=td,
                           fak_stats=fak, jp_stats=jp, pos_stats=pos, lok_stats=lok, prodi_stats=prodi_stat)

# ═══════ USER MANAGEMENT ═══════════════════════════════

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    msg = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_password':
            old = request.form.get('old_password','')
            new = request.form.get('new_password','')
            with get_db() as conn:
                u = conn.execute("SELECT * FROM users WHERE id=? AND password_hash=?",
                                 (session['user_id'], hash_pw(old))).fetchone()
                if u:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (hash_pw(new), session['user_id']))
                    msg = ('success', 'Password berhasil diubah.')
                else:
                    msg = ('error', 'Password lama salah.')
        elif action == 'add_user' and session.get('role') == 'admin':
            uname = request.form.get('new_username','').strip()
            pw    = request.form.get('new_password','')
            role  = request.form.get('new_role','admin')
            try:
                with get_db() as conn:
                    conn.execute("INSERT INTO users (username,password_hash,role) VALUES (?,?,?)",
                                 (uname, hash_pw(pw), role))
                msg = ('success', f'User {uname} berhasil ditambahkan.')
            except:
                msg = ('error', 'Username sudah ada.')
    with get_db() as conn:
        users = conn.execute("SELECT id, username, role, created_at FROM users").fetchall()
    return render_template('settings.html', users=users, msg=msg)

@app.route('/users/delete/<int:uid>', methods=['POST'])
@login_required
def delete_user(uid):
    if session.get('role') != 'admin' or uid == session['user_id']:
        return jsonify({'success': False})
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8000)
