# Bomberman AI Pathfinding

Arena simulasi Bomberman 2D berbasis web untuk membandingkan lima algoritma pathfinding secara *head-to-head*: **BFS, Dijkstra, UCS, GBFS, dan A\***. Backend **FastAPI** menghitung rute musuh, frontend kanvas HTML5 menjalankan simulasi **Bot vs Bot (BvB)** atau **Player vs Bot (PvB)**, dan notebook Jupyter menyediakan benchmark kuantitatif untuk kebutuhan penelitian.

Seluruh aplikasi web berada dalam satu file, `main.py`: model data, engine pathfinding, REST API, dan antarmuka simulasi.

## Daftar isi

- [Fitur](#fitur)
- [Prasyarat](#prasyarat)
- [Instalasi dan menjalankan](#instalasi-dan-menjalankan)
- [Cara menggunakan](#cara-menggunakan)
- [Struktur proyek](#struktur-proyek)
- [Algoritma yang didukung](#algoritma-yang-didukung)
- [Model biaya dan metrik](#model-biaya-dan-metrik)
- [Aturan arena](#aturan-arena)
- [API singkat](#api-singkat)
- [Notebook benchmark](#notebook-benchmark)
- [Dokumentasi lanjutan](#dokumentasi-lanjutan)
- [Troubleshooting](#troubleshooting)
- [Batasan](#batasan)

## Fitur

- **Lima algoritma pathfinding** yang dapat dipilih terpisah untuk Bot 1 dan Bot 2.
- **Mode BvB simultan**: dua bot berburu, mengebom, dan menghancurkan dinding kayu secara bergantian dengan urutan yang diacak agar adil.
- **Mode PvB**: pemain mengendalikan karakter dengan WASD/panah dan mengebom dengan Spasi.
- **Tiga peta simetris**: Klasik, Koridor, dan Terbuka, dengan validasi simetri, konektivitas, dan keamanan area spawn.
- **Fase permainan**: NORMAL → OVERDRIVE → SUDDEN DEATH, dengan eskalasi kecepatan, jumlah bom, dan penyusutan arena simetris 180°.
- **Anti-loop**: *history penalty* berbasis recency pada engine dan state `BREAK_LOOP` pada bot.
- **Escape planner**: bot memprioritaskan keluar dari zona ledakan sebelum mengejar target.
- **Panel analisis**: win counter, rata-rata node dieksplorasi, depth ekspansi, depth solusi, dan waktu eksekusi per algoritma.
- **Benchmark notebook**: uji efisiensi 5 algoritma pada 2 peta, uji deadlock sebelum/sesudah history penalty, grafik, dan ekspor CSV.

## Prasyarat

- Python **3.10+** (proyek diuji dengan Python 3.13–3.15)
- Browser modern dengan dukungan Canvas dan `fetch`
- Tidak membutuhkan database atau layanan eksternal

## Instalasi dan menjalankan

```powershell
# dari root proyek
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
python main.py
```

Buka <http://127.0.0.1:8000>.

Catatan:

- `python main.py` menjalankan Uvicorn dengan `reload=True` pada `127.0.0.1:8000`. Jalankan dari root proyek agar `main:app` dapat ditemukan.
- Untuk mengakses dari perangkat lain di jaringan lokal, ubah `uvicorn.run(...)` menjadi `host="0.0.0.0"` atau jalankan `uvicorn main:app --host 0.0.0.0 --port 8000`.
- Jika PowerShell memblokir aktivasi venv, jalankan `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` pada sesi tersebut, atau panggil `.\venv\Scripts\python.exe main.py` tanpa aktivasi.
- Port bentrok? Gunakan `uvicorn main:app --port 8001`, lalu sesuaikan URL yang dibuka.

## Cara menggunakan

1. Pada menu awal, pilih **mode permainan**, **algoritma Bot 1/Bot 2**, **kecepatan**, dan **peta**.
2. Opsional: aktifkan **Eskalasi otomatis fase** agar kecepatan mengikuti fase permainan.
3. Klik **Mulai**.
4. Selama simulasi tersedia kontrol:
   - **Ulang ronde** — mulai ronde baru dan reset statistik seri.
   - **Jeda / Lanjut** — hentikan atau lanjutkan tick.
   - **Step satu tick** — majukan satu tick saat jeda.
   - **Kembali ke menu** — buka kembali layar konfigurasi.
   - **Kecepatan saat ini** — ubah kecepatan tanpa kembali ke menu.

Pada mode **PvB**:

| Aksi | Tombol |
| --- | --- |
| Gerak | `W` `A` `S` `D` atau panah |
| Pasang bom | `Spasi` |

Pemain memiliki 3 nyawa, 1 bom per magazin, waktu isi ulang 150 tick, dan 60 tick *invincibility frames* setelah terkena ledakan.

## Struktur proyek

```text
Bomberman-Pathfinding/
├─ main.py                       # Model, engine pathfinding, REST API, frontend, server
├─ bomberman_ai_benchmark.ipynb  # Benchmark & visualisasi untuk laporan penelitian
├─ requirements.txt              # Dependensi web dan notebook
├─ docs/
│  ├─ arsitektur.md              # Arsitektur, alur request, game loop, aturan arena
│  ├─ algoritma.md               # Detail tiap algoritma, biaya, heuristik, metrik
│  ├─ api.md                     # Referensi endpoint dan skema data
│  └─ benchmark.md               # Metodologi dan penggunaan notebook benchmark
├─ venv/                         # Virtual environment lokal (tidak perlu di-commit)
└─ __pycache__/                  # Cache Python (tidak perlu di-commit)
```

Pembagian bagian di `main.py`:

| Bagian | Isi |
| --- | --- |
| 1. Data models | `EnemyInfo`, `MultiPathRequest` (Pydantic) |
| 2. Pathfinding engine | Konstanta biaya, `run_search`, ekspansi tetangga, rekonstruksi path |
| 3. REST endpoint | `POST /api/find-paths-multi` |
| 4. Frontend | `GET /` — HTML, CSS, dan JavaScript simulasi |

## Algoritma yang didukung

| Kode API | Algoritma | Strategi | Early exit | Bobot biaya |
| --- | --- | --- | --- | --- |
| `BFS` | Breadth-First Search | FIFO, level per level | Ya | Diabaikan |
| `UCS` | Uniform Cost Search | Priority queue `g(n)` | Ya | Dipakai |
| `DIJKSTRA` | Dijkstra | Priority queue `g(n)` | Tidak (seluruh grid) | Dipakai |
| `GBFS` | Greedy Best-First Search | Priority queue `h(n)` | Ya | Diabaikan saat memilih prioritas |
| `A_STAR` / `A*` | A\* Search | Priority queue `g(n) + h(n)` | Ya | Dipakai |

Semua pencarian memakai jarak Manhattan untuk heuristik (GBFS/A\*) dan pemilihan node *fallback*: bila target tidak tercapai, bot tetap diarahkan ke node terdekat yang sempat ditemukan.

Detail implementasi, kompleksitas, dan perbedaan dengan notebook ada di [docs/algoritma.md](docs/algoritma.md).

## Model biaya dan metrik

Biaya langkah pada engine server:

| Kondisi | Biaya |
| --- | --- |
| Ubin kosong (`0`) | `1.0` |
| Dinding kayu (`2`) | `5.5` |
| Ubin dalam zona bahaya | `+35.0` |
| Ubin yang sering dikunjungi | `+` hingga `16.0` per kunjungan, tergantung recency |

Dinding permanen (`1`), bom aktif (`3`), dan ubin runtuh (`4`) tidak dapat dilalui oleh pathfinding.

Metrik yang dikembalikan dan ditampilkan:

| Metrik | Arti |
| --- | --- |
| `nodes_explored` | Jumlah node yang diekspansi selama pencarian |
| `max_depth` | Kedalaman ekspansi terdalam, dihitung dari jumlah edge terhadap posisi awal |
| `solution_depth` | Jumlah langkah pada path solusi (`len(path) - 1`); `0` untuk path fallback |
| `exec_time_ms` | Waktu eksekusi `run_search` dalam milidetik |

Nilai depth adalah **kedalaman graph**, bukan biaya. Path yang melewati kayu bisa memiliki depth lebih kecil tetapi biaya lebih besar.

## Aturan arena

- Grid berukuran **13 baris × 15 kolom** (15×13 ubin) dengan koordinat `(baris, kolom)` 0-indexed.
- Spawn BvB: Bot 1 di `(1,1)`, Bot 2 di `(11,13)`.
- Setiap peta divalidasi: simetris 180°, area spawn terhubung, dan tiga ubin area spawn harus kosong.
- Jangkauan ledakan tetap **3 ubin** (pusat + 1 ubin tiap arah).
- Fase permainan:

| Fase | Tick mulai | Kecepatan otomatis | Maks. bom/bot | Fuse bom bot |
| --- | --- | --- | --- | --- |
| NORMAL | 0 | 1× | 1 | 60 |
| OVERDRIVE | 1200 | 2× | 2 | 48 |
| SUDDEN DEATH | 2100 | 3× | 3 | 36 |

- Kecepatan fase hanya berlaku jika **Eskalasi otomatis fase** dicentang; tanpa itu, kecepatan mengikuti pilihan pengguna. Maksimum bom dan fuse selalu mengikuti fase.

- Saat SUDDEN DEATH, arena menyusut berpasangan secara simetris setiap 75 tick, menyisakan area tengah 3×5. Ubin yang runtuh langsung mengeliminasi apa pun yang berdiri di atasnya.
- Bot bergerak setiap 12 tick; ledakan dan bom diperbarui setiap tick.
- Pemenang ditentukan oleh KO (ledakan atau arena runtuh), dengan *double KO* dicatat sebagai seri.

Penjelasan lengkap alur tick dan keputusan bot ada di [docs/arsitektur.md](docs/arsitektur.md).

## API singkat

Server menyediakan:

| Method | Path | Fungsi |
| --- | --- | --- |
| `GET` | `/` | Antarmuka simulasi |
| `POST` | `/api/find-paths-multi` | Hitung path untuk banyak musuh sekaligus |
| `GET` | `/docs` | Swagger UI (otomatis dari FastAPI) |
| `GET` | `/redoc` | ReDoc |
| `GET` | `/openapi.json` | Skema OpenAPI |

Contoh request:

```bash
curl -X POST http://127.0.0.1:8000/api/find-paths-multi \
  -H "Content-Type: application/json" \
  -d '{
    "grid": [
      [1,1,1,1,1],
      [1,0,0,0,1],
      [1,0,2,0,1],
      [1,0,0,0,1],
      [1,1,1,1,1]
    ],
    "enemies": [{
      "id": 1,
      "pos": [1,1],
      "target": [3,3],
      "algorithm": "A_STAR",
      "history": [],
      "danger": []
    }]
  }'
```

Contoh respons:

```json
{
  "status": "success",
  "results": [
    {
      "id": 1,
      "enemy_pos": [1, 1],
      "next_move": [1, 2],
      "full_path": [[1, 1], [1, 2], [1, 3], [2, 3], [3, 3]],
      "algorithm": "A_STAR",
      "nodes_explored": 8,
      "max_depth": 4,
      "solution_depth": 4,
      "exec_time_ms": 0.067
    }
  ]
}
```

Skema lengkap, contoh Python, dan catatan perilaku ada di [docs/api.md](docs/api.md).

## Notebook benchmark

Notebook `bomberman_ai_benchmark.ipynb` menjalankan dua suite:

1. **Efisiensi pathfinding** — 5 algoritma × 2 peta × 50 trial, mengukur rata-rata node, waktu eksekusi, panjang path, dan success rate.
2. **Anti-deadlock** — 4 pasangan algoritma × 20 run per kondisi, membandingkan tingkat kebuntuan tanpa dan dengan *history penalty*.

Jalankan dengan:

```powershell
jupyter lab
```

Lalu buka notebook dan jalankan semua sel. Output yang dihasilkan:

- `benchmark_efficiency_results.csv`
- `benchmark_deadlock_results.csv`
- Tiga grafik: nodes explored, execution time, dan deadlock rate.

Metodologi, skema CSV, dan tips interpretasi ada di [docs/benchmark.md](docs/benchmark.md).

## Dokumentasi lanjutan

- [docs/arsitektur.md](docs/arsitektur.md) — arsitektur sistem, alur request, pipeline tick, keputusan bot, peta, fase.
- [docs/algoritma.md](docs/algoritma.md) — model biaya, pseudocode, kompleksitas, perbandingan dengan notebook.
- [docs/api.md](docs/api.md) — referensi REST API dan skema data.
- [docs/benchmark.md](docs/benchmark.md) — metodologi benchmark dan ekspor data penelitian.

## Troubleshooting

| Gejala | Penyebab umum | Solusi |
| --- | --- | --- |
| `ModuleNotFoundError: fastapi` | Dependensi belum terpasang di venv aktif | Aktifkan venv lalu `pip install -r requirements.txt` |
| Halaman terbuka tetapi bot tidak bergerak | Request API gagal | Buka DevTools → Network/Console, pastikan `/api/find-paths-multi` merespons 200 |
| `[Errno 10048] address already in use` | Port 8000 dipakai proses lain | Hentikan proses lama atau jalankan di port lain |
| Notebook gagal `import seaborn` | Dependensi notebook belum lengkap | `pip install -r requirements.txt` (sudah mencakup `numpy` dan `seaborn`) |
| Aktivasi venv ditolak PowerShell | Execution policy | Gunakan `.\venv\Scripts\python.exe main.py` atau ubah policy sesi |
| Perubahan `main.py` tidak terlihat | Mode reload gagal/berjalan dari folder salah | Jalankan `python main.py` dari root proyek, cek log Uvicorn |

## Batasan

- Tidak ada penyimpanan data: statistik seri hanya hidup di memori halaman dan hilang saat halaman dimuat ulang.
- API tidak memiliki autentikasi, rate limit, atau validasi bentuk grid yang ketat; anggap sebagai alat lokal/penelitian.
- Pemanggilan AI bersifat *best effort* tiap 12 tick. Jika respons API lambat, ada guard `isFetching` yang mencegah request bertumpuk, sehingga bot dapat melewatkan giliran.
- A\* memakai heuristik Manhattan yang admissible terhadap model biaya, tetapi heuristik tidak mengetahui mahalnya kayu atau bahaya, sehingga jumlah node yang diekspansi tetap bisa lebih besar dari perkiraan.
- Pengukuran `max_depth` melakukan penelusuran parent per node, sehingga menambah overhead pada waktu eksekusi.
- Implementasi notebook dan server tidak identik (biaya kayu, bobot history, penanganan danger). Rincian perbedaannya ada di [docs/algoritma.md](docs/algoritma.md#9-perbedaan-notebook-dan-server).
- Tidak ada file lisensi dalam repositori ini.
