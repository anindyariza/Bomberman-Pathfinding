# BOMBERMAN Pathfinding

Arena simulasi Bomberman 2D berbasis web untuk membandingkan lima algoritma pathfinding secara *head-to-head*: **BFS, Dijkstra, UCS, GBFS, dan A\***. Backend **FastAPI** menghitung rute bot, frontend kanvas HTML5 menjalankan simulasi **Player vs Bot (PvB)** atau **Bot vs Bot (BvB)**, dan notebook Jupyter menyediakan lima suite benchmark kuantitatif untuk kebutuhan penelitian.

Seluruh aplikasi web berada dalam satu file, `main.py`: model data, engine pathfinding, REST API, serta antarmuka menu dan arena.

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
- **Batas depth pencarian** yang dapat diatur: 2, 4, 6, 8, 12, 16, 20, atau tak terbatas.
- **UI tiga layar**: menu utama → pilih map dan pengaturan → konfirmasi pilihan.
- **Tiga karakter kosmetik** (IGNIS, VECTRA, KRONOS) tanpa perbedaan statistik.
- **Mode BvB simultan**: dua bot berburu, mengebom, dan menghancurkan dinding kayu dengan urutan giliran yang diacak agar adil.
- **Mode PvB**: pemain mengendalikan karakter dengan WASD/panah dan mengebom dengan Spasi.
- **Tiga peta simetris**: Klasik, Koridor, dan Terbuka, dengan validasi simetri, konektivitas, dan keamanan area spawn.
- **Fase permainan**: NORMAL → OVERDRIVE → SUDDEN DEATH, menambah jumlah bom, memperpendek fuse, dan menyusutkan arena secara simetris.
- **Ledakan kotak 3×3** (maksimal 9 ubin) yang menghancurkan kayu dan memicu reaksi berantai.
- **Anti-loop**: *history penalty* pada engine dan state `BREAK_LOOP` pada bot.
- **Escape planner**: bot memprioritaskan keluar dari zona ledakan sebelum mengejar target.
- **Panel analisis**: win counter, batas depth, rata-rata node, depth ekspansi, depth solusi, dan waktu eksekusi per bot.
- **Notebook benchmark** dengan lima suite: efisiensi, anti-deadlock, skalabilitas kepadatan kayu, profiling jarak, dan heatmap per sel target.

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

### Alur menu

1. **Layar 1 — Menu utama**: pilih **Player Vs Bot** atau **Bot Vs Bot**.
2. **Layar 2 — Pilih map dan pengaturan**:
   - pilih salah satu dari tiga peta;
   - pilih karakter untuk tiap entitas melalui tab **Player/Bot** (PvB) atau **Bot 1/Bot 2** (BvB);
   - pilih algoritma (satu untuk bot di mode PvB, dua untuk mode BvB);
   - pilih **Depth** pencarian;
   - klik **Mulai**.
3. **Layar 3 — Pilihan kamu**: periksa ringkasan mode, peta, karakter, algoritma, dan depth. Klik **BALIK** untuk mengubah atau **OMKE GAS** untuk memulai simulasi.

### Kontrol arena

| Kontrol | Fungsi |
| --- | --- |
| **Ulang ronde** | Mulai ronde baru dengan pengaturan yang sama dan reset statistik seri |
| **Jeda / Lanjut** | Hentikan atau lanjutkan simulasi |
| **Step satu tick** | Majukan satu tick saat simulasi dijeda |
| **Ubah di Settings** | Hentikan simulasi dan kembali ke layar pengaturan |
| **Menu Utama** | Hentikan simulasi dan kembali ke menu utama |

Pada mode **PvB**:

| Aksi | Tombol |
| --- | --- |
| Gerak | `W` `A` `S` `D` atau panah |
| Pasang bom | `Spasi` |

Pemain memiliki 3 nyawa, 1 bom per magazin, waktu isi ulang 150 tick, dan 60 tick *invincibility frames* setelah terkena ledakan. Karakter hanya mengubah tampilan, bukan statistik.

## Struktur proyek

```text
Bomberman-Pathfinding/
├─ main.py                  # Model, engine pathfinding, REST API, frontend, server
├─ benchmarking.ipynb       # Lima suite benchmark dan visualisasi
├─ requirements.txt         # Dependensi web dan notebook
├─ docs/
│  ├─ arsitektur.md         # Arsitektur, alur request, UI, game loop, aturan arena
│  ├─ algoritma.md          # Detail tiap algoritma, depth limit, biaya, metrik
│  ├─ api.md                # Referensi endpoint dan skema data
│  └─ benchmark.md          # Metodologi dan penggunaan notebook benchmark
├─ .gitignore               # Mengabaikan venv dan __pycache__
├─ venv/                    # Virtual environment lokal (diabaikan Git)
└─ __pycache__/             # Cache Python (diabaikan Git)
```

Pembagian bagian di `main.py`:

| Bagian | Isi |
| --- | --- |
| 1. Data models | `EnemyInfo`, `MultiPathRequest` (Pydantic) |
| 2. Pathfinding helpers & search | Biaya, `get_neighbors`, `run_search` untuk 5 algoritma |
| 3. REST endpoint | `POST /api/find-paths-multi` |
| 4. Frontend | `GET /` — CSS, tiga layar UI, kanvas arena, dan JavaScript simulasi |

## Algoritma yang didukung

| Kode API | Algoritma | Strategi | Early exit | Bobot biaya | Depth limit |
| --- | --- | --- | --- | --- | --- |
| `BFS` | Breadth-First Search | FIFO, level per level | Ya | Diabaikan | Ya |
| `UCS` | Uniform Cost Search | Priority queue `g(n)` | Ya | Dipakai | Ya |
| `DIJKSTRA` | Dijkstra | Priority queue `g(n)` | Ya | Dipakai | Ya |
| `GBFS` | Greedy Best-First Search | Priority queue `h(n)` | Ya | Diabaikan saat memilih prioritas | Ya |
| `A_STAR` / `A*` | A\* Search | Priority queue `g(n) + h(n)` | Ya | Dipakai | Ya |

Semua pencarian memakai jarak Manhattan untuk heuristik (GBFS/A\*) dan pemilihan node *fallback*. Bila target tidak ditemukan dalam batas depth atau tidak terjangkau, bot diarahkan ke node terdekat yang sempat diekspansi.

Detail implementasi, kompleksitas, dan perbedaan dengan notebook ada di [docs/algoritma.md](docs/algoritma.md).

## Model biaya dan metrik

Biaya langkah pada engine server:

| Kondisi | Biaya |
| --- | --- |
| Ubin kosong (`0`) | `1.0` |
| Dinding kayu (`2`) | `4.0` |
| Ubin dalam zona bahaya | `+14.0` |
| Riwayat kunjungan | `+0.65` hingga `+1.70` per kunjungan, terakumulasi bila berulang |

Riwayat terbaru mendapat penalti lebih besar: posisi ke-`i` pada daftar history menambah `0.65 + i × 0.05`. Dinding permanen (`1`), bom aktif (`3`), dan ubin runtuh (`4`) tidak dapat dilalui pathfinding.

Metrik yang dikembalikan dan ditampilkan:

| Metrik | Arti |
| --- | --- |
| `nodes_explored` | Jumlah node yang diekspansi selama pencarian |
| `max_depth` | Kedalaman ekspansi terdalam, dihitung dari jumlah edge terhadap posisi awal |
| `solution_depth` | `len(path) - 1`; untuk path fallback nilainya adalah panjang path parsial |
| `exec_time_ms` | Waktu eksekusi `run_search` dalam milidetik |
| `max_depth_limit` | Batas depth yang dipakai untuk pencarian tersebut; `0` berarti tak terbatas |

Nilai depth adalah **kedalaman graph**, bukan biaya. Path yang melewati kayu bisa memiliki depth lebih kecil tetapi biaya lebih besar.

## Aturan arena

- Grid berukuran **13 baris × 15 kolom** (15×13 ubin) dengan koordinat `(baris, kolom)` 0-indexed.
- Spawn: Player/Bot 1 di `(1,1)`, Bot/Bot 2 di `(11,13)`.
- Setiap peta divalidasi: simetris 180°, area spawn terhubung, dan area spawn harus kosong.
- Ledakan berbentuk **kotak 3×3** (maksimal 9 ubin), bukan salib. Dinding permanen dan ubin runtuh tidak ikut terkena; kayu di dalam area hancur.
- Fase permainan:

| Fase | Tick mulai | Maks. bom/bot | Fuse bom bot |
| --- | --- | --- | --- |
| NORMAL | 0 | 1 | 60 |
| OVERDRIVE | 1200 | 2 | 48 |
| SUDDEN DEATH | 2100 | 3 | 36 |

- Tidak ada kontrol kecepatan. Simulasi berjalan satu tick per frame animasi; fase hanya mengubah jumlah bom dan fuse.
- Saat SUDDEN DEATH, arena menyusut berpasangan secara simetris setiap 75 tick, menyisakan area tengah 3×5. Ubin yang runtuh langsung mengeliminasi apa pun yang berdiri di atasnya.
- Bot mengambil keputusan setiap 12 tick; bom dan ledakan diperbarui setiap tick.
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
      "max_depth": 12,
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
      "max_depth_limit": 12,
      "nodes_explored": 8,
      "max_depth": 4,
      "solution_depth": 4,
      "exec_time_ms": 0.077
    }
  ]
}
```

Skema lengkap, contoh Python, dan catatan perilaku ada di [docs/api.md](docs/api.md).

## Notebook benchmark

Notebook `benchmarking.ipynb` menjalankan lima suite:

1. **Efisiensi pathfinding** — 5 algoritma × 3 peta × 50 trial.
2. **Anti-deadlock** — 4 pasangan algoritma × 20 run per kondisi (tanpa/dengan history penalty).
3. **Skalabilitas kepadatan kayu** — 7 tingkat kepadatan (0–60%) × 5 algoritma × 30 trial.
4. **Profiling jarak** — nodes explored terhadap jarak Manhattan 2–22.
5. **Heatmap** — nodes explored untuk setiap sel target pada peta kompleks.

Jalankan dengan:

```powershell
jupyter lab
```

Lalu buka notebook dan jalankan semua sel. Output yang dihasilkan:

- `benchmark_efficiency_results.csv`
- `benchmark_deadlock_results.csv`
- `benchmark_density_results.csv`
- `benchmark_distance_results.csv`
- Enam gambar: `grid_visualization.png`, `suite1_efficiency.png`, `suite2_deadlock.png`, `suite3_density.png`, `suite4_distance.png`, `suite5_heatmap.png`

Metodologi, skema CSV, dan tips interpretasi ada di [docs/benchmark.md](docs/benchmark.md).

## Dokumentasi lanjutan

- [docs/arsitektur.md](docs/arsitektur.md) — arsitektur sistem, alur request, UI tiga layar, pipeline tick, keputusan bot, peta, fase.
- [docs/algoritma.md](docs/algoritma.md) — model biaya, depth limit, pseudocode, kompleksitas, perbandingan dengan notebook.
- [docs/api.md](docs/api.md) — referensi REST API dan skema data.
- [docs/benchmark.md](docs/benchmark.md) — metodologi lima suite, output, dan ekspor data penelitian.

## Troubleshooting

| Gejala | Penyebab umum | Solusi |
| --- | --- | --- |
| `ModuleNotFoundError: fastapi` | Dependensi belum terpasang di venv aktif | Aktifkan venv lalu `pip install -r requirements.txt` |
| Halaman terbuka tetapi bot tidak bergerak | Belum menekan **OMKE GAS** atau request API gagal | Mulai dari layar konfirmasi; cek DevTools → Network/Console |
| Bot hanya bergerak sedikit lalu berhenti | Batas depth terlalu kecil untuk jarak target | Naikkan **Depth** atau pilih **Tak Terbatas** |
| `[Errno 10048] address already in use` | Port 8000 dipakai proses lain | Hentikan proses lama atau jalankan di port lain |
| Notebook gagal `import seaborn` | Dependensi notebook belum lengkap | `pip install -r requirements.txt` |
| Aktivasi venv ditolak PowerShell | Execution policy | Gunakan `.\venv\Scripts\python.exe main.py` atau ubah policy sesi |
| Perubahan `main.py` tidak terlihat | Mode reload gagal/berjalan dari folder salah | Jalankan `python main.py` dari root proyek, cek log Uvicorn |

## Batasan

- Tidak ada penyimpanan data: statistik seri hanya hidup di memori halaman dan hilang saat halaman dimuat ulang.
- API tidak memiliki autentikasi, rate limit, atau validasi bentuk grid yang ketat; anggap sebagai alat lokal/penelitian.
- Middleware CORS tidak dipasang. UI bekerja karena satu origin dengan API, tetapi pemanggilan dari browser di origin lain akan diblokir.
- Tidak ada kontrol kecepatan simulasi; satu tick dijalankan per frame animasi.
- Pemanggilan AI bersifat *best effort* tiap 12 tick. Jika respons API lambat, guard `isFetching` mencegah request bertumpuk sehingga bot dapat melewatkan giliran.
- Batas depth membatasi ekspansi berdasarkan jumlah edge dari posisi awal. Target yang lebih jauh dari batas akan menghasilkan path parsial/fallback.
- A\* memakai heuristik Manhattan yang admissible, tetapi heuristik tidak mengetahui mahalnya kayu atau bahaya sehingga jumlah node yang diekspansi tetap bisa lebih besar dari perkiraan.
- Implementasi notebook dan server tidak identik (biaya kayu, bobot history, penanganan danger, depth limit). Rincian perbedaannya ada di [docs/algoritma.md](docs/algoritma.md#9-perbedaan-notebook-dan-server).
- Tidak ada file lisensi dalam repositori ini.
