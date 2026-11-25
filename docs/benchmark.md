# Benchmark dan Notebook

Notebook `benchmarking.ipynb` menyediakan lima suite eksperimen untuk membandingkan algoritma pathfinding dan mengevaluasi mekanisme anti-deadlock. Dokumen ini menjelaskan isi notebook, parameter yang dapat diubah, output yang dihasilkan, serta cara membaca hasilnya.

## 1. Menjalankan notebook

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
jupyter lab
```

Buka `benchmarking.ipynb`, lalu **Run All**. Notebook tidak membutuhkan server FastAPI; seluruh algoritma didefinisikan ulang di dalam notebook agar eksperimen dapat dijalankan mandiri.

Dependensi notebook:

| Paket | Kegunaan |
| --- | --- |
| `numpy` | Statistik rata-rata, standar deviasi, array heatmap |
| `pandas` | Tabel hasil dan ekspor CSV |
| `matplotlib` | Grafik dan visualisasi grid |
| `seaborn` | Tema dan styling |
| `jupyterlab` | Lingkungan notebook |

Semua paket tersebut tercantum di `requirements.txt`.

## 2. Struktur notebook

| Sel | Tipe | Isi |
| --- | --- | --- |
| 1 | Markdown | Judul dan fokus eksperimen |
| 2 | Markdown | Label library dan visual |
| 3 | Code | Import pustaka, warna algoritma, tema seaborn |
| 4 | Markdown | Skema nilai grid dan biaya |
| 5 | Markdown | Definisi peta benchmark |
| 6 | Code | `MAP_OPEN`, `MAP_COMPLEX`, `MAP_CORRIDOR`, statistik grid |
| 7 | Markdown | Pengantar implementasi pathfinding |
| 8 | Code | Konstanta biaya dan lima algoritma |
| 9 | Markdown | Verifikasi sebelum benchmark |
| 10 | Code | Uji cepat setiap algoritma pada `MAP_COMPLEX` |
| 11 | Markdown | Visualisasi grid dan path |
| 12 | Code | Gambar tiga peta + path A\*, simpan `grid_visualization.png` |
| 13 | Markdown | Suite 1 — efisiensi |
| 14 | Code | Benchmark efisiensi, `df_benchmark` |
| 15 | Markdown | Visualisasi Suite 1 |
| 16 | Code | Grafik nodes/time/path, simpan `suite1_efficiency.png` |
| 17 | Markdown | Suite 2 — anti-deadlock |
| 18 | Code | Simulasi BvB, `df_deadlock` |
| 19 | Markdown | Visualisasi Suite 2 |
| 20 | Code | Grafik deadlock dan langkah, simpan `suite2_deadlock.png` |
| 21 | Markdown | Suite 3 — skalabilitas kepadatan kayu |
| 22 | Code | Benchmark kepadatan, `df_density`, simpan `suite3_density.png` |
| 23 | Markdown | Suite 4 — profiling jarak |
| 24 | Code | Benchmark jarak, `df_distance`, simpan `suite4_distance.png` |
| 25 | Markdown | Suite 5 — heatmap per sel target |
| 26 | Code | Heatmap lima algoritma, simpan `suite5_heatmap.png` |
| 27 | Markdown | Ringkasan dan ekspor CSV |
| 28 | Code | Ekspor 4 CSV dan ringkasan teks |

## 3. Peta benchmark

Notebook memakai tiga peta statis berukuran 13×15:

| Peta | Karakteristik |
| --- | --- |
| `MAP_OPEN` | Hanya dinding permanen berpola; seluruh sel lain lantai. Tidak ada kayu. |
| `MAP_COMPLEX` | Banyak dinding kayu di antara dinding permanen, menyerupai peta Klasik aplikasi. |
| `MAP_CORRIDOR` | Dinding kayu membentuk lorong vertikal dan horizontal. |

Keduanya memakai:

- Start: `(1, 1)`
- Target: `(11, 13)`

`MAP_OPEN` tetap memiliki dinding permanen, sehingga bukan medan tanpa rintangan; ia menjadi pembanding "tanpa kayu" terhadap dua peta lainnya.

## 4. Implementasi algoritma di notebook

Konstanta dan perilaku:

| Aspek | Nilai di notebook |
| --- | --- |
| Biaya lantai | `1.0` |
| Biaya kayu | `6.0` |
| History penalty | `5.0` per kemunculan |
| Danger penalty | Tidak ada |
| Depth limit | Tidak ada |
| Ubin yang dapat dilalui | `{0, 2}` |
| Dijkstra/UCS | Sama-sama berhenti saat target ditemukan; UCS adalah alias Dijkstra |
| BFS/GBFS | Mengabaikan biaya saat memilih urutan ekspansi |
| A\* | `f = g + h`, heuristik Manhattan |
| Fallback | Tidak ada; path kosong bila target gagal dicapai |

Perbedaan ini penting: angka notebook adalah perbandingan **relatif antar algoritma**, bukan reproduksi persis metrik UI. Rincian lengkap ada di [algoritma.md](algoritma.md#9-perbedaan-notebook-dan-server).

## 5. Suite 1 — Efisiensi pathfinding

### Metodologi

```python
NUM_TRIALS = 50
for setiap peta (3):
    for setiap algoritma (5):
        jalankan 50 kali dari START ke TARGET
        catat nodes, waktu, dan panjang path
```

Total: **5 algoritma × 3 peta × 50 trial = 750 eksekusi**.

### Kolom hasil

| Kolom | Satuan | Arti |
| --- | --- | --- |
| `Map Type` | — | Nama peta |
| `Algorithm` | — | Nama algoritma |
| `Nodes Explored (Avg)` | node | Rata-rata node yang dieksplorasi |
| `Nodes Explored (Std)` | node | Standar deviasi node |
| `Execution Time (ms)` | milidetik | Rata-rata waktu eksekusi internal algoritma |
| `Exec Time Std (ms)` | milidetik | Standar deviasi waktu |
| `Path Length` | ubin | Rata-rata `len(path)`, sudah termasuk ubin start |
| `Path Length Std` | ubin | Standar deviasi panjang path |
| `Success Rate (%)` | persen | `100.0` jika rata-rata path length > 0, selain itu `0.0` |

Untuk mendapatkan jumlah langkah, kurangi `Path Length` dengan 1.

### Catatan

- Waktu diukur **di dalam fungsi algoritma**, bukan di endpoint.
- `UCS` adalah alias `run_dijkstra`, sehingga barisnya akan identik dengan `Dijkstra`.
- BFS/GBFS mengabaikan biaya, sehingga `Path Length` kecil belum tentu berarti biaya berbobot kecil.
- `Success Rate` dihitung dari rata-rata, bukan per trial.

## 6. Suite 2 — Anti-deadlock

### Metodologi

`simulate_bvb()` menjalankan dua bot bergantian selama maksimal 100 langkah:

1. Bot 1 menghitung path ke posisi Bot 2, lalu mengambil langkah pertama.
2. Bot 2 menghitung path ke posisi Bot 1, lalu mengambil langkah pertama.
3. History 6 posisi terakhir dikirim bila `use_history=True`.
4. Simulasi berhenti jika jarak Manhattan kedua bot ≤ 1 (dianggap bertemu).
5. State `(pos1, pos2)` yang berulang dihitung.
6. Setelah 100 langkah, simulasi dianggap deadlock jika jumlah state berulang > 30.

Pasangan yang diuji:

```python
pairs = [("A*","A*"), ("A*","BFS"), ("GBFS","BFS"), ("Dijkstra","A*")]
```

Setiap pasangan dijalankan **20 kali tanpa history penalty** dan **20 kali dengan history penalty** pada `MAP_OPEN`, menggunakan seed `0..19` untuk kedua kondisi. Total 160 simulasi.

### Kolom hasil

| Kolom | Arti |
| --- | --- |
| `Matchup` | Pasangan algoritma, mis. `A* vs BFS` |
| `Deadlock Rate Without History (%)` | Persentase run yang terdeteksi deadlock tanpa penalti |
| `Deadlock Rate With History (%)` | Persentase run yang terdeteksi deadlock dengan penalti |
| `Avg Steps Without History` | Rata-rata langkah sampai bertemu/berhenti tanpa penalti |
| `Avg Steps With History` | Rata-rata langkah sampai bertemu/berhenti dengan penalti |

Semakin rendah deadlock rate, semakin baik. Tujuan history penalty adalah menurunkan angka pada kolom "With History" dibanding "Without History".

### Keterbatasan definisi deadlock

- Deteksi berbasis **state berulang** `(pos1, pos2)`, bukan analisis siklus formal.
- Bot dapat dianggap deadlock meski sebenarnya hanya berputar lambat menuju lawan.
- `oscillating` menghitung kemunculan state yang sudah pernah dilihat; ambang `> 30` bersifat heuristik.
- Simulasi berhenti lebih awal saat jarak ≤ 1, sehingga tingkat "penyelesaian" ikut memengaruhi hasil.
- Penalti history notebook (5.0 datar) berbeda dari server (recency), sehingga angka absolutnya tidak dapat dibandingkan langsung dengan UI.

## 7. Suite 3 — Skalabilitas kepadatan kayu

### Metodologi

```python
DENSITY_TRIALS = 30
DENSITIES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
```

- Grid dibuat dari `MAP_OPEN`, lalu sebagian sel lantai diubah menjadi kayu.
- Sel spawn, target, dan tetangga langsungnya dilindungi agar tidak tertutup.
- `seed=trial` dipakai agar peta untuk trial tertentu dapat direproduksi.
- Setiap kombinasi dijalankan 30 kali.

Total: **7 tingkat kepadatan × 5 algoritma × 30 trial = 1050 eksekusi**.

Kolom hasil:

| Kolom | Arti |
| --- | --- |
| `Wood Density (%)` | Persentase kayu yang disisipkan pada sel kandidat |
| `Algorithm` | Nama algoritma |
| `Nodes (Avg)` | Rata-rata node dieksplorasi |
| `Nodes (Std)` | Standar deviasi node |

Catatan:

- Persentase dihitung dari jumlah sel kandidat, bukan seluruh grid.
- Tidak ada jaminan target tetap terjangkau pada kepadatan tinggi; karena notebook tidak punya fallback, path dapat kosong dan tetap mencatat node yang dieksplorasi.
- Suite ini tidak mencatat success rate atau waktu.

## 8. Suite 4 — Profiling jarak

### Metodologi

- Peta: `MAP_OPEN`.
- Target: semua sel lantai dengan jarak Manhattan 2–22 dari `START`.
- Untuk setiap jarak, diambil sampel maksimal `DISTANCE_TRIALS = 20` sel.
- Setiap algoritma dijalankan pada target sampel tersebut.

Kolom hasil:

| Kolom | Arti |
| --- | --- |
| `Manhattan Distance` | Jarak Manhattan start ke target |
| `Algorithm` | Nama algoritma |
| `Nodes (Avg)` | Rata-rata node dieksplorasi untuk jarak tersebut |

Grafik menunjukkan bagaimana beban pencarian tumbuh seiring jarak target.

## 9. Suite 5 — Heatmap nodes per sel target

- Peta: `MAP_COMPLEX`.
- Target: setiap sel yang dapat dilalui (`0` atau `2`), kecuali `START`.
- Setiap algoritma dijalankan dari `START` ke setiap target tersebut.
- Hasilnya berupa heatmap 13×15 per algoritma; sel dinding dibiarkan kosong (NaN) dan ditimpa warna dinding.

Suite ini tidak mengekspor CSV; hanya menghasilkan gambar `suite5_heatmap.png`.

## 10. Output file

Setelah **Run All**, notebook menulis ke direktori kerja notebook:

### CSV

| File | Isi |
| --- | --- |
| `benchmark_efficiency_results.csv` | Hasil Suite 1 |
| `benchmark_deadlock_results.csv` | Hasil Suite 2 |
| `benchmark_density_results.csv` | Hasil Suite 3 |
| `benchmark_distance_results.csv` | Hasil Suite 4 |

### Gambar

| File | Isi |
| --- | --- |
| `grid_visualization.png` | Tiga peta dengan path A\* |
| `suite1_efficiency.png` | Nodes, waktu, dan path length per peta |
| `suite2_deadlock.png` | Deadlock rate dan rata-rata langkah |
| `suite3_density.png` | Nodes vs kepadatan kayu |
| `suite4_distance.png` | Nodes vs jarak Manhattan |
| `suite5_heatmap.png` | Heatmap nodes per sel target |

Jika notebook dijalankan dari lokasi lain, file akan muncul di sana. Cari dengan `Get-ChildItem -Recurse benchmark_*.csv` atau `Get-ChildItem -Recurse suite*.png`.

## 11. Mengubah eksperimen

### Menambah trial

```python
NUM_TRIALS = 200
DENSITY_TRIALS = 100
DISTANCE_TRIALS = 50
```

Trial lebih banyak mengurangi noise waktu, tetapi memperpanjang runtime secara linear.

### Mengganti start/target

```python
START  = (1, 1)
TARGET = (11, 13)
```

Pastikan kedua koordinat berada di dalam grid dan target dapat dijangkau.

### Menambah algoritma

Tambahkan fungsi dengan signature:

```python
def run_algo(grid, start, target, history=None):
    return path, nodes_explored, exec_time_ms, path_length
```

Lalu daftarkan pada `ALGORITHMS` dan tambahkan warna di `ALGO_COLORS` serta urutan di `ALGO_ORDER` agar grafik tetap konsisten.

### Mengubah pasangan deadlock

```python
pairs = [("A*","A*"), ("GBFS","GBFS"), ("BFS","Dijkstra")]
```

### Memakai peta aplikasi

Salin `MAP_TEMPLATE` dari `main.py` ke notebook, lalu tambahkan ke `MAPS`. Ingat bahwa implementasi notebook dan server berbeda; samakan konstanta biaya, history, danger, dan depth limit bila ingin hasil sebanding.

### Mengatur seed

- Suite 2 memakai `random.seed(run)` untuk setiap simulasi.
- Suite 3 memakai `random.Random(trial)` untuk membuat grid.
- Suite 4 memakai `random.sample` tanpa seed, sehingga sampel target dapat berbeda antar run.

Untuk reproduksi penuh, set seed global di awal:

```python
import random
random.seed(42)
```

## 12. Tips pelaporan

- Laporkan **rata-rata ± standar deviasi**, bukan hanya satu angka.
- Sebutkan jumlah trial, peta, dan perangkat; waktu absolut bergantung pada CPU dan beban sistem.
- Bedakan **langkah** (path length) dari **biaya** (kayu/history/danger).
- Jelaskan bahwa UCS dan Dijkstra di notebook identik, sehingga bukan perbandingan dua algoritma berbeda.
- Untuk klaim anti-deadlock, tampilkan persentase dan jumlah run, mis. "6 dari 20 run".
- Untuk Suite 3 dan 4, jelaskan bahwa nodes dapat turun karena target tidak terjangkau, bukan karena algoritma lebih efisien.
- Simpan CSV, gambar, dan versi notebook/commit hash agar eksperimen dapat direproduksi.
- Jika membandingkan dengan UI, cantumkan perbedaan konstanta dan tidak adanya depth limit di notebook.

## 13. Reproduksibilitas

Checklist singkat:

1. Gunakan versi Python dan paket dari `requirements.txt`.
2. Jalankan **Restart Kernel and Run All** agar state lama tidak mencemari hasil.
3. Tutup aplikasi berat lain untuk mengurangi noise waktu.
4. Simpan CSV dan grafik bersama laporan.
5. Catat perubahan parameter (`NUM_TRIALS`, peta, pasangan algoritma, seed).
6. Jalankan ulang minimal dua kali untuk memastikan tren utama konsisten.
