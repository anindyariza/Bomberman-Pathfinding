# Algoritma Pathfinding

Dokumen ini menjelaskan model biaya, cara kerja tiap algoritma, mekanisme anti-loop, metrik, serta perbedaan implementasi server dan notebook.

## 1. Representasi masalah

Aplikasi memakai grid **13 baris × 15 kolom** (kanvas 15×13 ubin). Dokumen dan notebook kadang menyebutnya "15×13" dengan konvensi lebar × tinggi.

- **State**: satu ubin `(baris, kolom)` pada grid tersebut.
- **Aksi**: bergerak satu ubin ke atas, bawah, kiri, atau kanan.
- **Biaya langkah** (`g`): bergantung pada isi ubin tujuan dan penalti tambahan.
- **Tujuan**: mencapai `target` dengan biaya serendah mungkin (untuk algoritma berbobot), atau jumlah langkah sedikit mungkin (BFS).
- **Heuristik** (`h`): jarak Manhattan ke target.

Grid hanya menyediakan dua jenis ubin yang dapat dilalui oleh engine:

| Nilai | Arti | Biaya dasar |
| --- | --- | --- |
| `0` | Lantai | `1.0` |
| `2` | Dinding kayu | `5.5` |
| `1`, `3`, `4` | Dinding permanen, bom, runtuh | Tidak dapat dilalui |

Dinding kayu dianggap dapat dilalui karena bot memang dirancang untuk menembusnya dengan bom. Biaya tinggi membuat algoritma berbobot memilih memutar jalan bila rutenya tidak terlalu jauh, tetapi tetap memilih menembus kayu bila itu jauh lebih efisien.

## 2. Model biaya

Konstanta di `main.py`:

```python
WOOD_COST = 5.5
DANGER_COST = 35.0
HISTORY_MAX_PENALTY = 16.0
```

Biaya memasuki ubin `(nr, nc)` dari `curr`:

```text
cost = base(nr, nc) + history_weight(nr, nc) + danger_penalty(nr, nc)

base(nr, nc)        = 1.0  jika grid[nr][nc] == 0
                    = 5.5  jika grid[nr][nc] == 2
history_weight      = akumulasi bobot recency kunjungan sebelumnya
danger_penalty      = 35.0 jika ubin ada di daftar danger, selain itu 0
```

### 2.1 History penalty (anti-loop)

Frontend mengirim maksimal 22 posisi terakhir bot. Server mengubahnya menjadi bobot:

```python
total_h = len(history)                    # 0 jika kosong
for idx, h in enumerate(history):
    recency = (idx + 1) / total_h         # posisi terbaru ≈ 1.0, terlama ≈ 1/total_h
    history_weights[h] += recency * 16.0
```

Konsekuensi:

- Ubin yang baru saja dilewati mendapat penalti hingga **16** per kunjungan.
- Kunjungan berulang menumpuk, sehingga ubin yang berulang kali dilewati menjadi sangat mahal.
- Penalti maksimum per kunjungan (16) lebih besar dari biaya kayu (5.5). Bot didorong membuka jalur baru atau menembus kayu daripada berputar-putar di jalur yang sama.
- Ubin lama tetap mendapat penalti kecil, sehingga rute tidak langsung kembali ke sana.

History penalty hanya memengaruhi algoritma yang memakai biaya langkah (UCS, Dijkstra, A\*). BFS dan GBFS mengabaikan biaya, sehingga efeknya tidak langsung terasa pada pemilihan rute mereka.

### 2.2 Danger penalty

Frontend menghitung `danger` dari seluruh bom aktif, termasuk propagasi ledakan berantai, lalu mengirim daftar ubinnya. Server menambahkan **+35** datar ke setiap ubin bahaya.

Penalti ini bersifat *soft*: ubin tetap dapat dilalui jika satu-satunya jalan menuju target melewati area bahaya. Keputusan menghindar secara mutlak ditangani terpisah di frontend oleh `getEscapeMove()`, yang berjalan sebelum pathfinding diikuti.

### 2.3 Admissibility heuristik

Heuristik Manhattan menghitung jumlah langkah minimum tanpa memedulikan rintangan. Karena setiap langkah berbiaya minimal 1.0, berlaku:

```text
h(n) = |r - r_goal| + |c - c_goal| <= biaya sebenarnya dari n ke goal
```

Maka heuristik **admissible** dan **konsisten** terhadap model biaya ini (termasuk biaya kayu, history, dan danger). A\* karena itu optimal terhadap model biaya, meskipun tetap bisa mengekspansi lebih banyak node karena heuristik tidak mengetahui mahalnya kayu atau bahaya.

## 3. Ekspansi tetangga

```python
def get_neighbors(cell, grid, history_weights, danger_cells, order):
    for dr, dc in order:                  # urutan 4 arah yang sudah diacak
        if dalam batas:
            if grid == 0: cost = 1.0 + history + danger
            elif grid == 2: cost = 5.5 + history + danger
```

- Urutan arah diacak **sekali per pencarian** (`random_dir_order()`), bukan per node.
- Pengacakan ini adalah mekanisme *tie-breaking* agar dua bot dengan algoritma sama tidak selalu memilih rute identik dan agar bias arah (atas selalu dicek lebih dulu) hilang.
- Karena itu, dua pemanggilan dengan input identik dapat menghasilkan path berbeda dengan biaya sama.

## 4. Algoritma

### 4.1 Breadth-First Search (BFS)

**Kode API:** `BFS`

BFS menjelajah berdasarkan jumlah langkah, menggunakan antrean FIFO.

```text
queue = [start]; visited = {start}
while queue:
    curr = queue.pop_front()
    if curr == target: return path
    for nxt in neighbors(curr):
        if nxt not in visited:
            visited.add(nxt); came_from[nxt] = curr; queue.push_back(nxt)
```

Karakteristik:

- Mengabaikan `WOOD_COST`, `DANGER_COST`, dan history dalam memilih urutan ekspansi.
- Menjamin jumlah langkah minimum (bukan biaya minimum), karena setiap edge dihitung sama.
- Cocok sebagai *baseline* untuk membandingkan jumlah node yang dieksplorasi.
- Berhenti begitu target ditemukan (early exit).

### 4.2 Uniform Cost Search (UCS)

**Kode API:** `UCS`

UCS adalah Dijkstra dengan **early exit**: berhenti saat target dikeluarkan dari priority queue.

```text
pq = [(0, start)]; g[start] = 0
while pq:
    g_curr, curr = pq.pop_min()
    if g_curr > g[curr]: continue
    if curr == target: return path
    for nxt, cost in neighbors(curr):
        if g_curr + cost < g[nxt]:
            g[nxt] = g_curr + cost; came_from[nxt] = curr
            pq.push(g_curr + cost, nxt)
```

Karakteristik:

- Menghormati seluruh komponen biaya (kayu, history, danger).
- Optimal terhadap biaya.
- Biasanya mengeksplorasi lebih sedikit node daripada Dijkstra karena berhenti di target.

### 4.3 Dijkstra

**Kode API:** `DIJKSTRA`

Implementasi Dijkstra di server **tidak** berhenti saat target ditemukan. Algoritma membangun pohon shortest-path untuk seluruh area terjangkau, lalu merekonstruksi path ke target.

```text
pq = [(0, start)]; g[start] = 0
while pq:
    g_curr, curr = pq.pop_min()
    if g_curr > g[curr]: continue
    for nxt, cost in neighbors(curr):
        relax(g, curr, nxt, cost, pq)
if target in came_from:
    return reconstruct(target)
```

Karakteristik:

- Menghasilkan path optimal yang sama kualitasnya dengan UCS.
- Mengeksplorasi seluruh komponen terhubung, sehingga `nodes_explored` biasanya paling besar.
- Berguna sebagai pembanding biaya komputasi "exhaustive search".
- Jika target tidak dapat dijangkau, Dijkstra tetap menyelesaikan seluruh grid sebelum masuk ke mekanisme fallback.

### 4.4 Greedy Best-First Search (GBFS)

**Kode API:** `GBFS`

GBFS hanya memprioritaskan jarak perkiraan ke target.

```text
pq = [(h(start), start)]; visited = {start}
while pq:
    _, curr = pq.pop_min()
    if curr == target: return path
    for nxt in neighbors(curr):
        if nxt not in visited:
            visited.add(nxt); came_from[nxt] = curr
            pq.push(h(nxt), nxt)
```

Karakteristik:

- Sangat agresif menuju target, sering mengeksplorasi node paling sedikit.
- Tidak optimal: dapat masuk kantong buntu, menembus kayu meski ada jalan memutar murah, atau melewati zona bahaya tanpa perhitungan biaya.
- Tetap *complete* pada graf berhingga karena memakai `visited`.
- Biaya langkah diabaikan sepenuhnya saat menentukan prioritas.

### 4.5 A\* Search

**Kode API:** `A_STAR` atau `A*`

A\* menggabungkan biaya aktual dan estimasi sisa:

```text
pq = [(h(start), 0, start)]; g[start] = 0
while pq:
    f, g_curr, curr = pq.pop_min()
    if g_curr > g[curr]: continue          # entri basi
    if curr == target: return path
    for nxt, cost in neighbors(curr):
        if g_curr + cost < g[nxt]:
            g[nxt] = g_curr + cost; came_from[nxt] = curr
            pq.push(g[nxt] + h(nxt), g[nxt], nxt)
```

Karakteristik:

- Menghormati seluruh komponen biaya.
- Dengan heuristik admissible dan konsisten, path yang dihasilkan optimal terhadap model biaya.
- Umumnya menjadi kompromi terbaik antara jumlah node dan kualitas path.
- Pemeriksaan `g_curr > g[curr]` membuang entri lama yang sudah diperbaiki.

## 5. Fallback

Semua algoritma melacak node dengan jarak Manhattan terkecil ke target:

```python
best_fallback = start
best_fallback_dist = manhattan(start, target)
# setiap node yang diekspansi:
if manhattan(curr, target) < best_fallback_dist:
    best_fallback = curr
```

Jika pencarian selesai tanpa mencapai target (misalnya target tertutup dinding permanen atau bom), server mengembalikan path menuju node terdekat tersebut:

- `full_path` berisi path parsial.
- `solution_depth` diisi `0` untuk menandai bahwa target tidak tercapai.
- Jika tidak ada node yang lebih dekat dari start, path kosong dikembalikan.

Fallback membuat bot tidak diam total saat target mustahil dijangkau, tetapi juga berarti `next_move` dapat mengarah ke ubin yang bukan target sebenarnya.

## 6. Kompleksitas

Untuk grid 15×13, `V = 195` dan `E ≤ 4V` (maksimal sekitar 780 edge).

| Algoritma | Waktu | Memori | Optimal | Complete |
| --- | --- | --- | --- | --- |
| BFS | `O(V + E)` | `O(V)` | Jumlah langkah | Ya |
| UCS | `O(E log V)` | `O(V)` | Biaya | Ya |
| Dijkstra | `O((V + E) log V)` | `O(V)` | Biaya | Ya |
| GBFS | `O(V log V)` (praktiknya jauh lebih kecil) | `O(V)` | Tidak | Ya |
| A\* | `O(E log V)` hingga `O(V log V)`, bergantung heuristik | `O(V)` | Biaya (heuristik admissible) | Ya |

Catatan: `search_depth()` menelusuri parent untuk setiap node yang diekspansi. Instrumentasi ini menambah biaya `O(depth)` per node, sehingga waktu eksekusi yang dilaporkan bukan waktu pencarian murni.

## 7. Metrik

| Field | Definisi | Catatan |
| --- | --- | --- |
| `nodes_explored` | Jumlah node yang dikeluarkan/diekspansi dari frontier | Termasuk node basi? Tidak: UCS/Dijkstra/A\* melewati entri basi sebelum menghitung |
| `max_depth` | Jumlah edge maksimum dari start ke node yang pernah diekspansi | Bukan biaya; node dengan kayu bisa punya depth kecil |
| `solution_depth` | `len(full_path) - 1` bila target tercapai, selain itu `0` | Untuk path satu titik, nilainya `0` |
| `exec_time_ms` | Durasi `run_search` diukur dengan `time.perf_counter()` | Tidak termasuk HTTP/JSON |

Pada panel frontend, nilai "Dikunjungi", "Depth maks.", "Depth solusi", dan "Waktu" menampilkan nilai pemanggilan terakhir, sedangkan angka dalam tanda kurung adalah rata-rata seri.

## 8. Perilaku tie-breaking dan nondeterminisme

Ada tiga lapis pengacakan yang memengaruhi hasil:

1. **Urutan arah** diacak setiap `run_search` (`random.shuffle`), memengaruhi urutan neighbor dan isi heap.
2. **Counter heap** (`itertools.count`) menjamin tidak ada perbandingan tuple yang gagal; entri dengan prioritas sama diproses sesuai urutan masuk.
3. **Urutan hasil bot** diacak 50:50 di frontend sebelum aksi diterapkan, sehingga giliran bergerak tidak selalu sama.

Dampaknya:

- Path dengan biaya sama dapat berbeda antar pemanggilan.
- Benchmark sebaiknya menjalankan banyak trial (notebook memakai 50) dan melaporkan rata-rata serta standar deviasi.
- Jangan membandingkan dua algoritma hanya dari satu ronde; gunakan statistik seri.

## 9. Perbedaan notebook dan server

Notebook adalah implementasi terpisah yang disederhanakan untuk eksperimen batch. Keduanya tidak identik, sehingga angka benchmark notebook tidak boleh dianggap sebagai reproduksi persis metrik di UI.

| Aspek | Server (`main.py`) | Notebook |
| --- | --- | --- |
| Biaya kayu | `5.5` | `6` |
| History penalty | Recency-weighted, maks. `16` per kunjungan | `jumlah_kunjungan × 5`, tanpa recency |
| Danger penalty | `+35` per ubin | Tidak ada parameter danger |
| BFS | Urutan neighbor acak | Neighbor diurutkan berdasarkan biaya |
| GBFS | Prioritas `h(n)` murni | Prioritas `h(n) + (cost - 1)` |
| UCS | Implementasi terpisah dengan early exit | Alias ke fungsi Dijkstra |
| Dijkstra | Priority queue dengan tuple counter | Priority queue `(g, node)` |
| Early exit | BFS/UCS/GBFS/A\* ya, Dijkstra tidak | Semua berhenti di target |
| Fallback | Ya, path parsial ke node terdekat | Tidak ada; path kosong bila gagal |
| Metrik | Nodes, max depth, solution depth, waktu | Nodes, waktu, panjang path |
| Pengukuran waktu | Di endpoint, di sekitar `run_search` | Di dalam tiap fungsi algoritma |
| Pengacakan | Ya | Tidak (deterministik kecuali data berubah) |

Implikasi untuk penelitian:

- Gunakan notebook untuk perbandingan relatif antar algoritma pada kondisi yang sama.
- Gunakan UI untuk demonstrasi interaktif dan validasi perilaku.
- Jika membutuhkan angka yang benar-benar identik, samakan konstanta dan hilangkan pengacakan pada kedua implementasi, lalu dokumentasikan perubahannya.

## 10. Referensi konsep

- Russell, S., & Norvig, P. *Artificial Intelligence: A Modern Approach* — BFS, UCS, GBFS, A\*.
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). *A Formal Basis for the Heuristic Determination of Minimum Cost Paths*.
- Dijkstra, E. W. (1959). *A Note on Two Problems in Connexion with Graphs*.
