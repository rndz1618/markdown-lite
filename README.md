# Markdown Lite

**Aplikasi Markdown Viewer & Editor yang ringan, modern, dan aman** untuk dijalankan di server Linux.

- ✅ Ringan (hanya Flask + beberapa library Python)
- ✅ Tampilan modern (Tailwind + EasyMDE)
- ✅ Penyimpanan file bisa diatur (default folder `./data`)
- ✅ Bisa diakses dari mana saja
- ✅ Proteksi path traversal + Basic Auth + sanitasi HTML
- ✅ Support folder, create/rename/delete file
- ✅ Dark / Light mode
- ✅ Live preview (side-by-side)

---

## Fitur

| Fitur | Keterangan |
|-------|------------|
| File browser | Sidebar dengan navigasi folder |
| Editor | EasyMDE (toolbar lengkap, preview, fullscreen) |
| Live Preview | Side-by-side & preview mode |
| Keamanan | Basic Auth, path sanitization, HTML bleach, CSRF check, security headers |
| Konfigurasi | Via environment variable |
| Responsive | Bisa dipakai di mobile |

---

## Instalasi Cepat (Linux)

### 1. Persiapan

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
sudo mkdir -p /opt/markdown-lite
sudo chown $USER:$USER /opt/markdown-lite
cd /opt/markdown-lite
```

### 2. Download dari GitHub

```bash
git clone https://github.com/rndz1618/markdown-lite.git .
```

### 3. Virtual environment & dependency

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Konfigurasi

```bash
cp .env.example .env
nano .env
```

Isi minimal:

```env
MD_ROOT=/var/markdown
MD_USER=admin
MD_PASS=password_kuat_anda
PORT=8080
HOST=0.0.0.0
ENABLE_AUTH=true
```

```bash
sudo mkdir -p /var/markdown
sudo chown $USER:$USER /var/markdown
```

### 5. Jalankan manual (testing)

```bash
source venv/bin/activate
python app.py
```

Buka browser: `http://IP-SERVER:8080`

---

## Menjalankan sebagai Service (systemd)

Lihat contoh unit file di dokumentasi lengkap. Gunakan gunicorn + EnvironmentFile.

---

## Keamanan yang Diterapkan

1. **Basic Authentication** — password dibandingkan dengan `secrets.compare_digest`
2. **Path Traversal Protection** — `../` diblokir, symlink dicek
3. **HTML Sanitization** — bleach di server + DOMPurify di klien
4. **XSS protection di sidebar** — nama file di-escape sebelum masuk ke DOM
5. **CSRF check ringan** — Origin/Referer divalidasi pada endpoint POST
6. **Security headers** — X-Frame-Options, CSP, X-Content-Type-Options, dll.
7. **Atomic write** — file disimpan via temp file + `os.replace`
8. **Batas ukuran request** — MAX_CONTENT_LENGTH default 1 MB
9. **Health endpoint** tidak membocorkan path storage
10. **Warning** jika masih memakai password default (`changeme`)
11. **Hanya file Markdown** — ekstensi dibatasi
12. **Rekomendasi**: Nginx + HTTPS + firewall

---

## Penggunaan

1. Login dengan kredensial di `.env`
2. Sidebar kiri = daftar file & folder
3. Klik file → buka editor
4. Toolbar EasyMDE + `Ctrl+S` untuk simpan
5. Tombol **+ File** / **+ Folder** untuk membuat baru

---

## Lisensi

MIT

Repo: https://github.com/rndz1618/markdown-lite
