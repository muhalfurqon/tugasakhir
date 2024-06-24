import os
from flask import Flask, redirect, url_for, render_template, request, jsonify, flash, session, send_file
from pymongo import MongoClient
from functools import wraps
from flask_bcrypt import Bcrypt
from flask_bcrypt import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import make_response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from os.path import join, dirname
from dotenv import load_dotenv

dotenv_path = join(dirname(_file_), '.env')
load_dotenv(dotenv_path)

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME =  os.environ.get("DB_NAME")

client = MongoClient(MONGODB_URI)
db = client[DB_NAME]

app = Flask(__name__)
app.secret_key='BIOSTAR'

SECRET_KEY='BIOSTAR'

bcrypt = Bcrypt(app)

UPLOAD_FOLDER = 'static/admin-assets/imgBukti'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/generate-pdf/<transaction_id>', methods=['GET'])
def generate_pdf(transaction_id):
    # Mencari transaksi berdasarkan ID
    transaction = db.transaksi.find_one({'_id': ObjectId(transaction_id)})
    if not transaction:
        return "Transaksi tidak ditemukan", 404

    filename = f"transaction_{transaction_id}.pdf"
    filepath = os.path.join("static", "admin-assets", "pdf", filename)

    # Membuat dokumen PDF menggunakan reportlab
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter

    # Warna latar belakang dan tepi kartu
    c.setStrokeColorRGB(0, 0, 0)
    c.setFillColorRGB(0.2, 0.2, 0.2)

    # Buat kartu dengan sudut bulat dan tinggi yang lebih besar
    c.roundRect(50, height - 400, 500, 300, 10, fill=1)

    # Tulisan di dalam kartu
    c.setFillColorRGB(1, 1, 1)  # Warna tulisan putih
    c.setFont("Helvetica-Bold", 16)
    c.drawString(70, height - 430, "Informasi Transaksi")

    # Header
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(70, height - 200, "Detail Transaksi")

    # Informasi Transaksi
    c.setFont("Helvetica", 12)
    c.drawString(70, height - 240, f"Nama Pengguna: {transaction['nama_pengguna']}")
    c.drawString(70, height - 260, f"Nama Diamond: {transaction['nama_diamond']}")
    c.drawString(70, height - 280, f"Total Harga: Rp{transaction['total_harga']},00")
    c.drawString(70, height - 300, f"Tanggal Pembelian: {transaction['tanggal_pembelian']}")
    c.drawString(70, height - 320, f"Status: {transaction['status']}")

    # Jika ada bukti transfer, tampilkan gambar
    if transaction.get('bukti_transfer'):
        bukti_transfer_filename = transaction['bukti_transfer']  # Nama file gambar bukti transfer
        bukti_transfer_path = os.path.join(UPLOAD_FOLDER, bukti_transfer_filename)
        if os.path.exists(bukti_transfer_path):
            c.drawString(70, height - 510, "Bukti Transfer:")
            c.drawImage(bukti_transfer_path, 70, height - 760, width=300, height=350, mask='auto')
        else:
            c.drawString(70, height - 510, "Bukti Transfer: (Gambar tidak ditemukan)")

    c.showPage()
    c.save()

    return send_file(filepath, as_attachment=True)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] == '':
            flash('Harap login terlebih dahulu.', 'error')
            return redirect(url_for('index'))
        if 'status' not in session or session['status'] != 'login':
            flash('Anda harus login terlebih dahulu untuk mengakses halaman ini.', 'error')
            return redirect(url_for('index'))
        if session['username'] != 'admin':
            flash('Akses ditolak. Hanya admin yang dapat mengakses halaman ini.', 'error')
            return redirect(url_for('dashboardadmin'))
        return f(*args, **kwargs)
    return decorated_function

def user_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] == '':
            flash('Harap login terlebih dahulu.', 'error')
            return redirect(url_for('index'))
        if 'status' not in session or session['status'] != 'login':
            flash('Anda harus login terlebih dahulu untuk mengakses halaman ini.', 'error')
            return redirect(url_for('index'))
        if session['username'] == 'admin':
            flash('Akses ditolak, harus login sebagai user.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    session.clear()
    
    diamonds = list(db.diamond.find({}))
    
    bestselling_diamonds = db.transaksi.aggregate([
        {"$group": {"_id": "$nama_diamond", "jumlah_pembelian": {"$sum": 1}}},
        {"$sort": {"jumlah_pembelian": -1}},
        {"$limit": 6}
    ])

    bestselling_data = []
    
    for diamond in bestselling_diamonds:
        # Ambil informasi detail diamond berdasarkan nama dari transaksi
        diamond_detail = db.diamond.find_one({"nama": diamond["_id"]})
        
        if diamond_detail:
            bestselling_data.append({
                "nama": diamond["_id"],
                "harga": diamond_detail["harga"],
                "gambar": diamond_detail["gambar"],  # Asumsi ada field gambar di collection diamond
                "jumlah_pembelian": diamond["jumlah_pembelian"]
            })

    return render_template('index.html', diamonds=diamonds, bestselling_data=bestselling_data)

@app.route('/dashboard-admin')
@admin_required
def dashboardadmin():
    return render_template('dashboard_admin.html')

@app.route('/diamond',methods=['GET'])
@admin_required
def diamond():
    diamond = list(db.diamond.find({}))
    return render_template('diamond.html', diamond = diamond)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    user_id = session.get('_id')

    if not user_id:
        return jsonify({'success': False, 'message': 'User not logged in'})

    transaction = {
        'user_id': user_id,
        'nama_pengguna': session.get('nama', 'Anonymous'),
        'nama_diamond': data['nama'],
        'total_harga': data['harga'],
        'tanggal_pembelian': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'pending'
    }
    
    db.transaksi.insert_one(transaction)
    return jsonify({'success': True})

@app.route('/transaksi')
def transakasi():
    user_id = session.get('_id')

    if not user_id:
        return render_template('transaksi.html', transaksi=[])

    transaksi = list(db.transaksi.find({'user_id': user_id}))
    return render_template('transaksi.html', transaksi=transaksi)

@app.route('/hapus-transaksi/<transaction_id>', methods=['POST'])
def hapus_transaksi(transaction_id):
    # Lakukan operasi penghapusan transaksi dari database
    db.transaksi.delete_one({'_id': ObjectId(transaction_id)})
    # Kirim respons JSON untuk menampilkan pesan ke frontend
    return jsonify({'message': 'Transaksi berhasil dihapus'})

@app.route('/transaksi-admin', methods=['GET'])
@admin_required  
def transaksiadmin():
    transaksi = list(db.transaksi.find({})) 
    return render_template('transaksi_admin.html', transaksi=transaksi)

@app.route('/detail-transaksi-admin/<transaction_id>', methods=['GET'])
def detail_transaksi_admin(transaction_id):
    transaction = db.transaksi.find_one({'_id': ObjectId(transaction_id)})

    if not transaction:
        return "Transaksi tidak ditemukan", 404

    return render_template('detail_transaksi_admin.html', transaction=transaction)

@app.route('/ubah-status-transaksi/<transaction_id>', methods=['POST'])
def ubah_status_transaksi(transaction_id):
    transaction = db.transaksi.find_one({'_id': ObjectId(transaction_id)})
    if not transaction:
        return jsonify({'message': 'Transaksi tidak ditemukan'}), 404

    # Lakukan perubahan status (misalnya dari 'pending' menjadi 'confirmed')
    db.transaksi.update_one(
        {'_id': ObjectId(transaction_id)},
        {'$set': {'status': 'confirmed'}}
    )

    return jsonify({'message': 'Status transaksi berhasil diubah'})

@app.route('/upload_bukti_transfer/<transaction_id>', methods=['POST'])
def upload_bukti_transfer(transaction_id):
    transaksi = db.transaksi.find_one({'_id': ObjectId(transaction_id)})

    if 'buktiTransfer' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'})

    file = request.files['buktiTransfer']

    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'})

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        db.transaksi.update_one({'_id': ObjectId(transaction_id)}, {'$set': {'bukti_transfer': filename, 'status': 'waiting'}})
        return redirect(url_for('dashboard'))

    return redirect(url_for('dashboard'))

@app.route('/detail-transaksi/<transaction_id>', methods=['GET'])
def detail_transaksi(transaction_id):
    transaction = db.transaksi.find_one({'_id': ObjectId(transaction_id)})
    return render_template('detail_transaksi.html', transaction=transaction)

@app.route('/addDiamond',methods=['GET', 'POST'])
@admin_required
def addDiamond():
    if request.method=='POST':
        nama = request.form['nama']
        harga = request.form['harga']
        gambar = request.files['gambar']

        if gambar:
            namaGambarAsli = gambar.filename
            namafileGambar = namaGambarAsli.split('/')[-1]
            file_path = f'static/admin-assets/imgGambar/{namafileGambar}'
            gambar.save(file_path)
        else:
           gambar = None 
        
        doc = {
            'nama': nama,
            'harga': int(harga),
            'gambar': namafileGambar
        }
        db.diamond.insert_one(doc)
        return redirect(url_for("diamond"))

    return render_template('addDiamond.html')

@app.route('/editDiamond/<_id>',methods=['GET','POST'])
@admin_required
def editDiamond(_id):
    if request.method=='POST':
        id = request.form['_id']
        nama = request.form['nama']
        harga = request.form['harga']
        nama_gambar = request.files['gambar']

        doc = {
            'nama': nama,
            'harga': harga
        }

        if nama_gambar:
            namaGambarAsli = nama_gambar.filename
            namafileGambar = namaGambarAsli.split('/')[-1]
            file_path = f'static/admin-assets/imgGambar/{namafileGambar}'
            nama_gambar.save(file_path)
            doc['gambar']= namafileGambar 
        
        db.diamond.update_one({"_id":ObjectId(_id)},{"$set":doc})
        return redirect(url_for("diamond"))

    id = ObjectId(_id)
    data = list(db.diamond.find({"_id":id}))
    return render_template('editDiamond.html', data = data)

@app.route('/deleteDiamond/<_id>',methods=['GET'])
def deleteDiamond(_id):
    db.diamond.delete_one({"_id": ObjectId(_id)})
    return redirect(url_for("diamond"))

@app.route('/login')
def login():
    session.clear()
    return render_template('login.html')

@app.route('/proses_login', methods=['POST'])
def proses_login():
    if request.method == 'POST':
        login_user = db.user.find_one({'username': request.form['username']})

        if login_user and bcrypt.check_password_hash(login_user['password'], request.form['password']):
            session['username'] = request.form['username']
            session['nama'] = login_user['nama']
            session['password'] = login_user['password']
            session['_id'] = str(login_user['_id'])
            session['status'] = 'login'
            if request.form['username'] == 'admin':
                return redirect(url_for('dashboardadmin'))
            else:
                return redirect(url_for('dashboard'))

    return render_template('index.html')

@app.route('/proses_register', methods=['GET', 'POST'])
def proses_register():
    if request.method == 'POST':
        username = request.form['username']
        nama = request.form['nama']
        alamat = request.form['alamat']
        password = request.form['password']

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        user_exists = db.user.find_one({'username': username})

        if user_exists:
            return jsonify({"status": "error", "message": "Username sudah ada, gunakan yang lain"}), 404

        db.user.insert_one({'username': username, 'nama': nama, 'alamat': alamat, 'password': hashed_password})

        return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/dashboard')
@user_required
def dashboard():
    if 'username' in session:
        diamonds = list(db.diamond.find({}))
        bestselling_diamonds = db.transaksi.aggregate([
            {"$group": {"_id": "$nama_diamond", "jumlah_pembelian": {"$sum": 1}}},
            {"$sort": {"jumlah_pembelian": -1}},
            {"$limit": 6}
        ])

        bestselling_data = []
        
        for diamond in bestselling_diamonds:
            diamond_detail = db.diamond.find_one({"nama": diamond["_id"]})
            
            if diamond_detail:
                bestselling_data.append({
                    "nama": diamond["_id"],
                    "harga": diamond_detail["harga"],
                    "gambar": diamond_detail["gambar"],  # Asumsi ada field gambar di collection diamond
                    "jumlah_pembelian": diamond["jumlah_pembelian"]
                })
        return render_template('dashboard_user.html', diamonds=diamonds, bestselling_data=bestselling_data)
    else:
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Anda telah berhasil logout.')
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)
