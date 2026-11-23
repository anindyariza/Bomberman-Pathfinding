# Benchmark dan Notebook

Notebook `bomberman_ai_benchmark.ipynb` menyediakan eksperimen kuantitatif untuk membandingkan algoritma pathfinding dan mengevaluasi mekanisme anti-deadlock. Dokumen ini menjelaskan isi notebook, parameter yang dapat diubah, output yang dihasilkan, serta cara membaca hasilnya.

## 1. Menjalankan notebook

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
jupyter lab
```

Buka `bomberman_ai_benchmark.ipynb`, lalu **Run All**. Notebook tidak membutuhkan server FastAPI; seluruh algoritma didefinisikan ulang di dalam notebook agar eksperimen dapat dijalankan mandiri.

Dependensi notebook:

| Paket | Kegunaan |
| --- | --- |
| `numpy` | Statistik rata-rata dan standar deviasi |
| `pandas` | Tabel hasil dan ekspor CSV |
| `matplotlib` | Grafik |
| `seaborn` | Bar plot dan styling |
| `jupyterlab` | Lingkungan notebook |

Semua paket tersebut sudah dicantumkan di `requirements.txt`.

## 2. Struktur notebook

| Sel | Isi |
| --- | --- |
| 1 | Judul, tujuan penelitian, dan empat fokus eksperimen |
| 2 | Sel markdown kosong |
| 3 | Import pustaka dan pengaturan visualisasi |
| 4 | Penjelasan skema grid |
| 5 | Definisi `MAP_OPEN` dan `MAP_COMPLEX` (15×13) |
| 6 | Judul bagian implementasi |
| 7 | Implementasi BFS, Dijkstra, UCS, GBFS, A\*, heuristik, dan history penalty |
| 8 | Judul Suite 1 |
| 9 | Eksekusi benchmark efisiensi dan tabel `df_benchmark` |
| 10 | Judul Suite 2 |
| 11 | Simulasi BvB untuk mengukur deadlock dan tabel `df_deadlock` |
| 12 | Judul bagian visualisasi |
| 13 | Tiga grafik: nodes explored, execution time, deadlock rate |
| 14 | Judul bagian ekspor |
| 15 | Ekspor kedua DataFrame ke CSV dan ringkasan |

## 3. Peta benchmark

Notebook memakai dua peta tetap berukuran 15×13:

| Peta | Karakteristik |
| --- | --- |
| `MAP_OPEN` | Dinding permanen membentuk pola lorong; seluruh sel lain adalah lantai. Tidak ada dinding kayu. |
| `MAP_COMPLEX` | Banyak dinding kayu (`2`) di antara dinding permanen, menyerupai peta Klasik di aplikasi. |

Keduanya memakai:

- Start: `(1, 1)`
- Target: `(11, 13)`

Karena `MAP_OPEN` tetap memiliki dinding permanen, peta ini bukan medan tanpa rintangan; ia menjadi pembanding "tanpa kayu" terhadap peta kompleks.

## 4. Suite 1 — Efisiensi pathfinding

### Metodologi

```python
NUM_TRIALS = 50
for setiap peta:
    for setiap algoritma:
        jalankan 50 kali dari start ke target
        catat nodes_explored, execution_time_ms, path_length
```

Kombinasi: **5 algoritma × 2 peta × 50 trial = 500 eksekusi**.

Algoritma yang diuji:

| Nama di notebook | Fungsi |
| --- | --- |
| `BFS` | `run_bfs` |
| `Dijkstra` | `run_dijkstra` |
| `UCS` | `run_ucs` (alias Dijkstra) |
| `GBFS` | `run_gbfs` |
| `A*` | `run_a_star` |

### Kolom hasil

| Kolom | Satuan | Arti |
| --- | --- | --- |
| `Map Type` | — | Nama peta |
| `Algorithm` | — | Nama algoritma |
| `Nodes Explored (Avg)` | node | Rata-rata node yang dieksplorasi |
| `Nodes Explored (Std)` | node | Standar deviasi node |
| `Execution Time (ms)` | milidetik | Rata-rata waktu eksekusi internal algoritma |
| `Path Length` | ubin | Rata-rata `len(path)`, sudah termasuk ubin start |
| `Success Rate (%)` | persen | `100.0` jika rata-rata path length > 0, selain itu `0.0` |

Untuk mendapatkan jumlah langkah, kurangi `Path Length` dengan 1.

### Catatan penting

- Notebook mengukur waktu **di dalam fungsi algoritma**, berbeda dari server yang mengukur di endpoint.
- Pada notebook, `UCS` adalah alias `run_dijkstra`, sehingga kedua baris akan identik.
- BFS dan GBFS mengabaikan biaya, sehingga `Path Length` yang kecil belum tentu berarti biaya berbobot yang kecil.
- `Success Rate` dihitung dari rata-rata, bukan per trial; nilainya biner pada dataset ini.

## 5. Suite 2 — Anti-deadlock

### Metodologi

`simulate_bvb_loop()` menjalankan dua bot bergantian selama maksimal 100 langkah:

1. Setiap bot menghitung path ke posisi lawan.
2. Bot mengambil langkah pertama dari path.
3. History 6 posisi terakhir dikirim bila `use_history_penalty=True`.
4. Simulasi berhenti jika jarak Manhattan kedua bot ≤ 1 (dianggap "bertemu").
5. Setelah 100 langkah, simulasi dianggap deadlock jika jumlah state berulang melebihi 30.

Pasangan yang diuji:

```python
pairs = [('A*', 'A*'), ('A*', 'BFS'), ('GBFS', 'BFS'), ('Dijkstra', 'A*')]
```

Setiap pasangan dijalankan **20 kali** tanpa history penalty dan **20 kali** dengan history penalty, pada `MAP_OPEN`.

### Kolom hasil

| Kolom | Arti |
| --- | --- |
| `Matchup` | Pasangan algoritma, mis. `A* vs BFS` |
| `Deadlock Rate Without History Penalty (%)` | Persentase run yang terdeteksi deadlock tanpa penalti |
| `Deadlock Rate With History Penalty (%)` | Persentase run yang terdeteksi deadlock dengan penalti |

Semakin rendah nilainya semakin baik. Tujuan fitur history penalty adalah menurunkan angka pada kolom kedua dibanding kolom pertama.

### Keterbatasan definisi deadlock

- Deteksi berbasis **state berulang** `(pos1, pos2)`, bukan analisis siklus formal.
- Bot dapat dianggap deadlock meski sebenarnya hanya berputar lambat menuju lawan.
- `oscillating_steps` menghitung kemunculan state yang sudah pernah dilihat, dan ambang `> 30` bersifat heuristik.
- Simulasi berhenti lebih awal saat jarak ≤ 1, sehingga tingkat "penyelesaian" ikut memengaruhi hasil.
- Penalti history notebook berbeda dari server (lihat [algoritma.md](algoritma.md#9-perbedaan-notebook-dan-server)), jadi angka absolutnya tidak dapat dibandingkan langsung dengan UI.

## 6. Visualisasi

Notebook menghasilkan tiga gambar:

1. **Nodes Explored** — dua subplot (peta terbuka dan kompleks), batang per algoritma, label nilai di atas batang.
2. **Execution Time (ms)** — dua subplot serupa, dengan label tiga desimal.
3. **Deadlock Rate** — grafik batang berkelompok yang membandingkan kondisi tanpa dan dengan history penalty untuk setiap matchup.

Gunakan grafik ini untuk:

- Menunjukkan trade-off antara jumlah ekspansi dan kualitas path.
- Membandingkan sensitivitas algoritma terhadap kompleksitas peta.
- Menjustifikasi pemilihan A\* atau UCS sebagai algoritma utama.
- Mengevaluasi efektivitas history penalty secara visual.

## 7. Output file

Sel setelah eksekusi menulis dua CSV ke **direktori kerja notebook** (biasanya folder proyek):

```text
benchmark_efficiency_results.csv
benchmark_deadlock_results.csv
```

Jika notebook dijalankan dari lokasi lain, file akan muncul di sana. Cari dengan `Get-ChildItem -Recurse benchmark_*.csv` bila tidak menemukannya.

Skema CSV mengikuti kolom DataFrame pada bagian 4 dan 5, sehingga dapat langsung dibuka di Excel, LibreOffice, atau diolah dengan pandas untuk BAB 3/BAB 4.

## 8. Mengubah eksperimen

### Menambah trial

```python
NUM_TRIALS = 200
```

Trial lebih banyak mengurangi noise waktu, tetapi memperpanjang runtime secara linear.

### Mengganti start/target

```python
start_pos = (1, 1)
target_pos = (11, 13)
```

Pastikan kedua koordinat berada di dalam grid dan target dapat dijangkau agar `Success Rate` tidak nol.

### Menambah algoritma

Tambahkan fungsi dengan signature:

```python
def run_algo(grid, start, target, history=None):
    return path, nodes_explored, exec_time_ms, path_length
```

Lalu daftarkan pada `algorithms`:

```python
algorithms['Algo Baru'] = run_algo
```

### Mengubah pasangan deadlock

```python
pairs = [('A*', 'A*'), ('GBFS', 'GBFS'), ('BFS', 'Dijkstra')]
```

### Memakai peta aplikasi

Salin `MAP_TEMPLATE` dari `main.py` ke notebook, lalu tambahkan ke `maps` pada Suite 1. Ingat bahwa implementasi notebook dan server berbeda; samakan konstanta biaya bila ingin hasil sebanding.

### Mengatur seed

Notebook tidak memakai pengacakan internal, sehingga hasil node dan path deterministik. Waktu eksekusi tetap bervariasi. Jika menambahkan komponen acak, set seed di awal:

```python
import random
random.seed(42)
```

## 9. Tips pelaporan

- Laporkan **rata-rata ± standar deviasi**, bukan hanya satu angka.
- Sebutkan jumlah trial dan perangkat yang dipakai; waktu absolut bergantung pada CPU dan beban sistem.
- Bedakan **langkah** (path length) dari **biaya** (wood/history/danger). BFS/GBFS bisa unggul di langkah tetapi kalah di biaya.
- Jelaskan bahwa UCS dan Dijkstra di notebook identik, sehingga bukan perbandingan dua algoritma berbeda.
- Untuk klaim anti-deadlock, tampilkan persentase dan jumlah run, mis. "6 dari 20 run" agar pembaca dapat menilai signifikansi.
- Simpan CSV bersama versi notebook dan commit hash agar eksperimen dapat direproduksi.
- Jika membandingkan dengan UI, cantumkan perbedaan konstanta pada metodologi.

## 10. Reproduksibilitas

Checklist singkat:

1. Gunakan versi Python dan paket dari `requirements.txt`.
2. Jalankan **Restart Kernel and Run All** agar state lama tidak mencemari hasil.
3. Tutup aplikasi berat lain untuk mengurangi noise waktu.
4. Simpan CSV dan grafik bersama laporan.
5. Catat perubahan parameter (`NUM_TRIALS`, peta, pasangan algoritma, seed).
6. Jalankan ulang minimal dua kali untuk memastikan tren utama konsisten.
