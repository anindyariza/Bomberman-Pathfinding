# Algoritma Pathfinding

Dokumen ini menjelaskan model biaya, batas depth, cara kerja tiap algoritma, mekanisme anti-loop, metrik, serta perbedaan implementasi server dan notebook.

## 1. Representasi masalah

Aplikasi memakai grid **13 baris × 15 kolom** (kanvas 15×13 ubin). Dokumen dan notebook kadang menyebutnya "15×13" dengan konvensi lebar × tinggi.

- **State**: satu ubin `(baris, kolom)` pada grid tersebut.
- **Aksi**: bergerak satu ubin ke atas, bawah, kiri, atau kanan.
- **Biaya langkah** (`g`): bergantung pada isi ubin tujuan dan penalti tambahan.
- **Tujuan**: mencapai `target` dengan biaya serendah mungkin (untuk algoritma berbobot), atau jumlah langkah sedikit mungkin (BFS).
- **Heuristik** (`h`): jarak Manhattan ke target.
- **Batas depth** (`max_depth_limit`): jumlah edge maksimum yang boleh diekspansi; `0` berarti tak terbatas.

Grid hanya menyediakan dua jenis ubin yang dapat dilalui oleh engine:

| Nilai | Arti | Biaya dasar |
| --- | --- | --- |
| `0` | Lantai | `1.0` |
| `2` | Dinding kayu | `4.0` |
| `1`, `3`, `4` | Dinding permanen, bom, runtuh | Tidak dapat dilalui |

Dinding kayu dianggap dapat dilalui karena bot memang dirancang untuk menembusnya dengan bom. Biaya tinggi membuat algoritma berbobot memilih memutar jalan bila rutenya tidak terlalu jauh, tetapi tetap memilih menembus kayu bila itu jauh lebih efisien.

## 2. Model biaya

Konstanta di `main.py` saat ini ditulis langsung di `get_neighbors`:

```python
step_cost = 4.0 if tile == 2 else 1.0
if nxt in danger_cells:
    step_cost += 14.0
if nxt in history_weights:
    step_cost += history_weights[nxt]
```

Biaya memasuki ubin `(nr, nc)`:

```text
cost = base(nr, nc) + history_weight(nr, nc) + danger_penalty(nr, nc)

base(nr, nc)        = 1.0  jika grid[nr][nc] == 0
                    = 4.0  jika grid[nr][nc] == 2
danger_penalty      = 14.0 jika ubin ada di daftar danger, selain itu 0
```

### 2.1 History penalty (anti-loop)

Frontend mengirim maksimal 22 posisi terakhir bot, dari terlama ke terbaru. Server mengubahnya menjadi bobot:

```python
for idx, pos in enumerate(history):
    key = (pos[0], pos[1])
    history_weights[key] += 0.65 + (idx * 0.05)
```

Karakteristik:

- Posisi paling lama mendapat tambahan `0.65`; posisi terbaru (indeks ke-21) mendapat `0.65 + 21 × 0.05 = 1.70`.
- Bila ubin yang sama muncul beberapa kali, nilainya **terakumulasi**.
- Tidak ada batas maksimum per ubin; penalti tumbuh sesuai panjang dan pengulangan history.
- Karena nilainya lebih kecil dari biaya kayu (`4.0`), history penalty mendorong variasi rute tanpa langsung memaksa bot menembus kayu.
- Hanya algoritma berbobot (UCS, Dijkstra, A\*) yang terpengaruh. BFS dan GBFS mengabaikan biaya.

### 2.2 Danger penalty

Frontend menghitung `danger` dari seluruh bom aktif, termasuk propagasi ledakan berantai, lalu mengirim daftar ubinnya. Server menambahkan **+14** datar ke setiap ubin bahaya.

Penalti ini bersifat *soft*: ubin tetap dapat dilalui jika satu-satunya jalan menuju target melewati area bahaya. Keputusan menghindar secara mutlak ditangani terpisah di frontend oleh `getEscapeMove()`, yang berjalan sebelum pathfinding diikuti.

### 2.3 Batas depth

Parameter `max_depth` pada `EnemyInfo` diteruskan sebagai `max_depth_limit` ke `run_search`:

- `depth_from[start] = 0`.
- Sebuah node dengan `depth >= max_depth_limit` tetap dihitung sebagai diekspansi, tetapi tetangganya tidak dimasukkan ke frontier.
- `0` berarti tanpa batas (pencarian penuh).
- Jika target berada di luar batas, algoritma berhenti dengan path parsial ke node fallback.
- Batas ini diterapkan pada kelima algoritma, termasuk BFS.

Pilihan UI: 2, 4, 6, 8, 12 (default), 16, 20, dan tak terbatas.

### 2.4 Admissibility heuristik

Heuristik Manhattan menghitung jumlah langkah minimum tanpa memedulikan rintangan. Karena setiap langkah berbiaya minimal `1.0`, berlaku:

```text
h(n) = |r - r_goal| + |c - c_goal| <= biaya sebenarnya dari n ke goal
```

Maka heuristik **admissible** dan **konsisten** terhadap model biaya ini (termasuk biaya kayu, history, dan danger). A\* karena itu optimal terhadap model biaya pada pencarian tanpa batas depth. Dengan batas depth, optimalitas hanya berlaku di dalam ruang yang dapat diekspansi.

## 3. Ekspansi tetangga

```python
for dr, dc in order:                  # urutan 4 arah yang sudah diacak
    if di luar batas: lanjut
    if grid[nr][nc] in (1, 3, 4): lanjut
    step_cost = 4.0 if grid[nr][nc] == 2 else 1.0
    step_cost += 14.0 if bahaya
    step_cost += history_weight
```

- Urutan arah diacak **sekali per pencarian** (`random.shuffle(order)`).
- Pengacakan ini adalah mekanisme *tie-breaking* agar dua bot dengan algoritma sama tidak selalu memilih rute identik dan agar bias arah hilang.
- Dua pemanggilan dengan input identik dapat menghasilkan path berbeda dengan biaya sama.

## 4. Algoritma

### 4.1 Breadth-First Search (BFS)

**Kode API:** `BFS`

BFS menjelajah berdasarkan jumlah langkah dengan antrean FIFO.

```text
queue = [start]; visited = {start}
while queue:
    curr = queue.pop_front()
    nodes++; max_depth = max(max_depth, depth[curr])
    fallback(curr)
    if curr == target: return path
    if max_depth_limit > 0 and depth[curr] >= max_depth_limit: continue
    for nxt in neighbors(curr):
        if nxt not in visited:
            visited.add(nxt); came_from[nxt] = curr; queue.push_back(nxt)
```

Karakteristik:

- Mengabaikan biaya kayu, danger, dan history dalam memilih urutan ekspansi.
- Menjamin jumlah langkah minimum (bukan biaya minimum) pada pencarian tanpa batas depth.
- Berhenti begitu target ditemukan.
- Cocok sebagai *baseline* jumlah node yang dieksplorasi.

### 4.2 Uniform Cost Search (UCS)

**Kode API:** `UCS`

UCS adalah pencarian berbobot dengan prioritas `g(n)` dan *early exit* saat target dikeluarkan dari priority queue.

```text
pq = [(0, start)]; g[start] = 0
while pq:
    g_curr, curr = pq.pop_min()
    if g_curr > g[curr]: continue
    nodes++; fallback(curr)
    if curr == target: return path
    if max_depth_limit > 0 and depth[curr] >= max_depth_limit: continue
    for nxt, cost in neighbors(curr):
        if g_curr + cost < g[nxt]:
            update(g, came_from, pq)
```

Karakteristik:

- Menghormati seluruh komponen biaya.
- Optimal terhadap biaya pada pencarian tanpa batas depth.
- Karena Dijkstra di server juga berhenti di target, jumlah node keduanya praktis sama.

### 4.3 Dijkstra

**Kode API:** `DIJKSTRA`

Dijkstra di server saat ini **berhenti saat target ditemukan**, sama seperti UCS. Algoritma tidak lagi membangun pohon shortest-path untuk seluruh grid. Perbedaannya dengan UCS hanya pada implementasi/penamaan; secara perilaku keduanya setara.

```text
pq = [(0, start)]; g[start] = 0
while pq:
    g_curr, curr = pq.pop_min()
    if g_curr > g[curr]: continue
    nodes++; fallback(curr)
    if curr == target: return path
    if depth limit tercapai: continue
    relax semua tetangga
```

Karakteristik:

- Menghormati biaya kayu, history, dan danger.
- Optimal terhadap biaya tanpa batas depth.
- Komentar lama "shortest-path tree" pada kode tidak lagi menggambarkan perilaku karena ada early exit.

### 4.4 Greedy Best-First Search (GBFS)

**Kode API:** `GBFS`

GBFS hanya memprioritaskan jarak perkiraan ke target.

```text
pq = [(h(start), start)]; visited = {start}
while pq:
    curr = pq.pop_min()
    nodes++; fallback(curr)
    if curr == target: return path
    if depth limit tercapai: continue
    for nxt in neighbors(curr):
        if nxt not in visited:
            visited.add(nxt); came_from[nxt] = curr
            pq.push(h(nxt), nxt)
```

Karakteristik:

- Sangat agresif menuju target; sering mengeksplorasi node paling sedikit.
- Tidak optimal: dapat masuk kantong buntu, menembus kayu meski ada jalan memutar murah, atau melewati zona bahaya.
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
    nodes++; fallback(curr)
    if curr == target: return path
    if depth limit tercapai: continue
    for nxt, cost in neighbors(curr):
        if g_curr + cost < g[nxt]:
            g[nxt] = g_curr + cost
            came_from[nxt] = curr
            pq.push(g[nxt] + h(nxt), g[nxt], nxt)
```

Karakteristik:

- Menghormati seluruh komponen biaya.
- Dengan heuristik admissible dan konsisten, path optimal pada pencarian tanpa batas depth.
- Umumnya menjadi kompromi terbaik antara jumlah node dan kualitas path.
- Pemeriksaan `g_curr > g[curr]` membuang entri lama yang sudah diperbaiki.

## 5. Fallback

Semua algoritma melacak node dengan skor terbaik:

```text
skor(node) = (manhattan(node, target), cost atau depth)
```

- Untuk BFS dan GBFS, komponen kedua adalah `depth`.
- Untuk UCS, Dijkstra, dan A\*, komponen kedua adalah biaya `g`.
- Perbandingan dilakukan secara leksikografis: jarak Manhattan lebih diutamakan.
- Start tidak pernah dijadikan fallback.

Jika target tidak tercapai:

- `full_path` berisi path parsial menuju fallback.
- `solution_depth` diisi `len(path) - 1`, bukan `0`.
- Jika tidak ada node selain start yang ditemukan, `full_path` kosong dan `next_move` sama dengan posisi awal.

Karena `solution_depth` tidak lagi menandai kegagalan, klien harus memeriksa apakah ubin terakhir `full_path` sama dengan target.

## 6. Kompleksitas

Untuk grid 15×13, `V = 195` dan `E ≤ 4V` (maksimal sekitar 780 edge). Dengan batas depth `d`, hanya node hingga kedalaman `d` yang diekspansi.

| Algoritma | Waktu | Memori | Optimal (tanpa depth limit) | Complete |
| --- | --- | --- | --- | --- |
| BFS | `O(V + E)` | `O(V)` | Jumlah langkah | Ya |
| UCS | `O(E log V)` | `O(V)` | Biaya | Ya |
| Dijkstra | `O(E log V)` | `O(V)` | Biaya | Ya |
| GBFS | `O(V log V)` (praktiknya jauh lebih kecil) | `O(V)` | Tidak | Ya |
| A\* | `O(E log V)` hingga `O(V log V)`, bergantung heuristik | `O(V)` | Biaya | Ya |

Dengan depth limit, algoritma dapat berhenti sebelum seluruh ruang keadaan dieksplorasi; konsekuensinya target di luar batas tidak tercapai.

## 7. Metrik

| Field | Definisi | Catatan |
| --- | --- | --- |
| `max_depth_limit` | Batas depth yang dipakai | `0` = tak terbatas |
| `nodes_explored` | Jumlah node yang diekspansi | Entri basi tidak dihitung |
| `max_depth` | Jumlah edge maksimum dari start ke node yang diekspansi | Bukan biaya |
| `solution_depth` | `len(full_path) - 1` | Berlaku juga untuk path fallback |
| `exec_time_ms` | Durasi `run_search` diukur dengan `time.perf_counter()` | Tidak termasuk HTTP/JSON |

Pada panel frontend, nilai "Dikunjungi", "Depth maks.", "Depth solusi", dan "Waktu" menampilkan nilai pemanggilan terakhir; angka dalam tanda kurung adalah rata-rata seri. Baris **Batas Depth** menampilkan batas yang dipakai (`∞` untuk tak terbatas).

## 8. Tie-breaking dan nondeterminisme

Ada tiga lapis pengacakan yang memengaruhi hasil:

1. **Urutan arah** diacak setiap `run_search`, memengaruhi urutan neighbor dan isi heap.
2. **Counter heap** (`itertools.count`) menjamin entri dengan prioritas sama diproses sesuai urutan masuk.
3. **Urutan hasil bot** diacak 50:50 di frontend sebelum aksi diterapkan.

Dampaknya:

- Path dengan biaya sama dapat berbeda antar pemanggilan.
- Benchmark sebaiknya menjalankan banyak trial (notebook memakai 30–50) dan melaporkan rata-rata serta standar deviasi.
- Jangan membandingkan dua algoritma hanya dari satu ronde; gunakan statistik seri.

## 9. Perbedaan notebook dan server

Notebook `benchmarking.ipynb` adalah implementasi terpisah yang disederhanakan untuk eksperimen batch. Angka benchmark tidak boleh dianggap sebagai reproduksi persis metrik UI.

| Aspek | Server (`main.py`) | Notebook |
| --- | --- | --- |
| Biaya kayu | `4.0` | `6.0` |
| History penalty | `0.65 + idx × 0.05` per kunjungan, terakumulasi | `5.0` per kunjungan, terakumulasi |
| Danger penalty | `+14` per ubin | Tidak ada parameter danger |
| Depth limit | Per request (`max_depth`) | Tidak ada |
| BFS | Urutan neighbor acak | Deterministik |
| GBFS | Prioritas `h(n)` murni | Prioritas `h(n)` murni |
| UCS | Implementasi terpisah dengan early exit | Alias ke fungsi Dijkstra |
| Dijkstra | Early exit saat target ditemukan | Early exit saat target ditemukan |
| Fallback | Ya, path parsial ke node terbaik | Tidak ada; path kosong bila gagal |
| Metrik | Nodes, max depth, solution depth, waktu | Nodes, waktu, panjang path |
| Pengukuran waktu | Di endpoint, di sekitar `run_search` | Di dalam tiap fungsi algoritma |
| Pengacakan | Ya | Tidak (kecuali suite yang memakai seed) |
| Peta | Klasik, Koridor, Terbuka dari UI | `MAP_OPEN`, `MAP_COMPLEX`, `MAP_CORRIDOR` |

Implikasi untuk penelitian:

- Gunakan notebook untuk perbandingan relatif antar algoritma pada kondisi yang sama.
- Gunakan UI untuk demonstrasi interaktif, pengaruh depth limit, dan validasi perilaku.
- Jika membutuhkan angka identik, samakan konstanta, batas depth, penanganan danger, dan pengacakan pada kedua implementasi, lalu dokumentasikan perubahannya.

## 10. Referensi konsep

- Russell, S., & Norvig, P. *Artificial Intelligence: A Modern Approach* — BFS, UCS, GBFS, A\*.
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). *A Formal Basis for the Heuristic Determination of Minimum Cost Paths*.
- Dijkstra, E. W. (1959). *A Note on Two Problems in Connexion with Graphs*.
