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
| Keamanan | Basic Auth, path sanitization, HTML bleach |
| Konfigurasi | Via environment variable |
| Responsive | Bisa dipakai di mobile |

---

## Instalasi Cepat (Linux)

### 1. Persiapan

```bash
# Install Python 3 & venv (jika belum)
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# Buat folder aplikasi
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
cd /opt/markdown-lite
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Konfigurasi

Buat file `.env`:

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

Buat folder penyimpanan:

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

## Menjalankan sebagai Service (systemd) — Recommended

```bash
sudo tee /etc/systemd/system/markdown-lite.service > /dev/null << 'EOF'
[Unit]
Description=Markdown Lite - Lightweight Markdown Editor
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/markdown-lite
EnvironmentFile=/opt/markdown-lite/.env
ExecStart=/opt/markdown-lite/venv/bin/gunicorn \
    --bind 0.0.0.0:8080 \
    --workers 2 \
    --threads 4 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo chown -R www-data:www-data /opt/markdown-lite
sudo chown -R www-data:www-data /var/markdown
sudo systemctl daemon-reload
sudo systemctl enable --now markdown-lite
sudo systemctl status markdown-lite
```

---

## Reverse Proxy dengan Nginx (HTTPS + Domain)

```nginx
server {
    listen 80;
    server_name markdown.domainanda.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name markdown.domainanda.com;

    ssl_certificate     /etc/letsencrypt/live/markdown.domainanda.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/markdown.domainanda.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Konfigurasi Environment Variables

| Variable | Default | Keterangan |
|----------|---------|------------|
| `MD_ROOT` | `./data` | Folder root penyimpanan file `.md` |
| `MD_USER` | `admin` | Username Basic Auth |
| `MD_PASS` | `changeme` | Password Basic Auth |
| `PORT` | `8080` | Port aplikasi |
| `HOST` | `0.0.0.0` | Bind address |
| `ENABLE_AUTH` | `true` | Aktifkan/nonaktifkan login |
| `SECRET_KEY` | (random) | Kunci session Flask |

---

## Keamanan yang Diterapkan

1. **Basic Authentication** — wajib login sebelum akses
2. **Path Traversal Protection** — tidak bisa keluar dari `MD_ROOT` (`../` diblokir)
3. **HTML Sanitization** — output Markdown dibersihkan dengan `bleach` (mencegah XSS)
4. **Hanya file Markdown** — ekstensi dibatasi
5. **Tidak ada upload binary** — hanya text `.md`
6. **Rekomendasi**: Jalankan di belakang Nginx + HTTPS + firewall

---

## Penggunaan

1. Login dengan username & password yang diatur di `.env`
2. Sidebar kiri = daftar file & folder
3. Klik file → buka editor
4. Toolbar EasyMDE: bold, heading, list, table, code, preview, side-by-side, fullscreen
5. `Ctrl + S` untuk menyimpan
6. Tombol **+ File** / **+ Folder** untuk membuat baru
7. Hover file → tombol hapus muncul

---

## Lisensi

MIT — silakan modifikasi sesuai kebutuhan.

Repo: https://github.com/rndz1618/markdown-lite
