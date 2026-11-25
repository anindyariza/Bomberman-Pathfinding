# Referensi API

Server dibangun dengan FastAPI dan berjalan secara default di `http://127.0.0.1:8000`.

| Method | Path | Tipe respons | Keterangan |
| --- | --- | --- | --- |
| `GET` | `/` | `text/html` | Antarmuka simulasi tiga layar |
| `POST` | `/api/find-paths-multi` | `application/json` | Hitung path untuk satu atau banyak musuh |
| `GET` | `/docs` | `text/html` | Swagger UI |
| `GET` | `/redoc` | `text/html` | ReDoc |
| `GET` | `/openapi.json` | `application/json` | Skema OpenAPI |

API bersifat **stateless**: tidak ada autentikasi, cookie, atau sesi. Middleware CORS **tidak** dipasang; UI bekerja karena disajikan dari origin yang sama dengan API. Pemanggilan `fetch` dari browser di origin lain akan diblokir. Klien non-browser (cURL, Python, Postman) tidak terpengaruh.

---

## POST `/api/find-paths-multi`

Menghitung rute untuk setiap musuh dalam satu request. Setiap musuh dapat memakai algoritma dan batas depth yang berbeda.

### Request body

```json
{
  "grid": [
    [1, 1, 1, 1, 1],
    [1, 0, 0, 0, 1],
    [1, 0, 2, 0, 1],
    [1, 0, 0, 0, 1],
    [1, 1, 1, 1, 1]
  ],
  "enemies": [
    {
      "id": 1,
      "pos": [1, 1],
      "target": [3, 3],
      "algorithm": "A_STAR",
      "max_depth": 12,
      "history": [],
      "danger": []
    }
  ]
}
```

#### Field level atas

| Field | Tipe | Wajib | Keterangan |
| --- | --- | --- | --- |
| `grid` | `array[array[int]]` | Ya | Grid persegi panjang berisi `0` (lantai), `1` (dinding), `2` (kayu), `3` (bom), `4` (runtuh). Koordinat `(baris, kolom)`, 0-indexed. |
| `enemies` | `array[EnemyInfo]` | Ya | Daftar musuh. Boleh kosong; hasilnya `results: []`. |

#### Objek `EnemyInfo`

| Field | Tipe | Wajib | Default | Keterangan |
| --- | --- | --- | --- | --- |
| `id` | `integer` | Ya | — | Identifier untuk pencocokan hasil. Server tidak memvalidasi keunikan. |
| `pos` | `[int, int]` | Ya | — | Posisi awal `[baris, kolom]`. Harus di dalam grid dan sebaiknya ubin lantai. |
| `target` | `[int, int]` | Ya | — | Posisi tujuan `[baris, kolom]`. Jika tidak terjangkau atau di luar batas depth, server memakai path fallback. |
| `algorithm` | `string` | Tidak | `"A_STAR"` | `BFS`, `UCS`, `DIJKSTRA`, `GBFS`, `A_STAR`, atau `A*`. Case-insensitive. |
| `max_depth` | `integer` | Tidak | `0` | Batas kedalaman ekspansi dalam jumlah edge. `0` berarti tak terbatas. |
| `history` | `array[[int, int]]` | Tidak | `[]` | Posisi yang pernah dilewati, dari terlama ke terbaru. Frontend mengirim maksimal 22 entri. |
| `danger` | `array[[int, int]]` | Tidak | `[]` | Ubin yang berpotensi terkena ledakan. Setiap ubin mendapat penalti biaya `+14`. |

Catatan:

- Nilai di luar `0`/`2` dianggap tidak dapat dilalui.
- `pos == target` menghasilkan `full_path` satu titik, `nodes_explored = 1`, serta `max_depth` dan `solution_depth = 0`.
- `algorithm` berupa string kosong dianggap `A_STAR`; `null` ditolak validasi Pydantic (422).
- `algorithm` yang tidak dikenal akan melewati semua cabang pencarian; hasilnya path kosong dengan metrik nol.
- Tidak ada batas ukuran grid yang ditegakkan. Baris yang tidak konsisten (ragged) dapat memicu error 500; posisi atau target di luar batas umumnya menghasilkan `full_path` kosong, bukan error.
- `max_depth` negatif diperlakukan seperti `0` (tak terbatas) karena pemeriksaan memakai `> 0`.

### Respons sukses

Status `200 OK`:

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

| Field | Tipe | Keterangan |
| --- | --- | --- |
| `status` | `string` | Selalu `"success"` untuk respons normal. |
| `results` | `array` | Satu entri per musuh, **sesuai urutan request**. |
| `results[].id` | `integer` | Sama dengan `id` request. |
| `results[].enemy_pos` | `[int, int]` | Posisi awal yang dikirim. |
| `results[].next_move` | `[int, int]` | Langkah berikutnya: `full_path[1]` jika ada, selain itu posisi awal/titik pertama. |
| `results[].full_path` | `array[[int, int]]` | Path lengkap termasuk start. Dapat kosong jika tidak ada solusi/fallback. |
| `results[].algorithm` | `string` | Kode algoritma yang dikirim (dikembalikan apa adanya). |
| `results[].max_depth_limit` | `integer` | Batas depth yang dipakai; `0` berarti tak terbatas. |
| `results[].nodes_explored` | `integer` | Jumlah node yang diekspansi. |
| `results[].max_depth` | `integer` | Kedalaman ekspansi maksimum (jumlah edge dari start). |
| `results[].solution_depth` | `integer` | `len(full_path) - 1`; juga diisi untuk path fallback. |
| `results[].exec_time_ms` | `number` | Durasi `run_search` dalam milidetik, dibulatkan 3 desimal. |

Contoh path di atas bersifat ilustratif. Karena urutan arah diacak per pencarian, path lain dengan biaya sama dapat muncul.

### Perilaku penting

1. **Target tidak terjangkau** — server mengembalikan path parsial ke node terdekat. Periksa apakah ubin terakhir `full_path` sama dengan target; `solution_depth` tidak lagi bernilai `0` sebagai penanda kegagalan.
2. **Tidak ada node yang lebih dekat** — `full_path` kosong dan `next_move` sama dengan `enemy_pos`.
3. **Depth limit** — node pada kedalaman `>= max_depth` tetap dihitung pada `nodes_explored`, tetapi tetangganya tidak dimasukkan ke frontier. Target yang lebih jauh tidak tercapai dan memicu fallback.
4. **Dinding kayu** — dapat dilalui dengan biaya `4.0`; path dapat menembus kayu.
5. **Danger** — hanya penalti biaya `+14`, bukan larangan. Ubin bahaya tetap dapat dilalui.
6. **History** — menambah `0.65 + 0.05 × indeks` per kemunculan; hanya memengaruhi algoritma berbobot.
7. **Dijkstra** — saat ini berhenti saat target ditemukan, sama seperti UCS.
8. **Banyak musuh** — diproses berurutan, bukan paralel.
9. **Metrik** — `exec_time_ms` bukan waktu respons HTTP; latensi jaringan dan serialisasi tidak dihitung.

### Error

| Status | Kondisi | Body |
| --- | --- | --- |
| `422 Unprocessable Entity` | Body tidak sesuai skema Pydantic (field hilang, tipe salah, dll.) | Detail validasi standar FastAPI |
| `500 Internal Server Error` | Grid tidak konsisten (mis. baris ragged) atau error runtime lain | Pesan error Uvicorn (tidak ada format khusus) |

Tidak ada kode error kustom. Validasi posisi dan bentuk grid menjadi tanggung jawab klien.

---

## Contoh pemanggilan

### cURL (Bash / PowerShell 7+)

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

PowerShell 5.1 tidak mendukung `curl` sebagai alias dengan body multi-baris yang aman; gunakan contoh Python atau JavaScript di bawah.

### Python (`requests`)

```python
import requests

payload = {
    "grid": [
        [1, 1, 1, 1, 1],
        [1, 0, 0, 0, 1],
        [1, 0, 2, 0, 1],
        [1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1],
    ],
    "enemies": [
        {
            "id": 1,
            "pos": [1, 1],
            "target": [3, 3],
            "algorithm": "A_STAR",
            "max_depth": 12,
            "history": [],
            "danger": [],
        }
    ],
}

response = requests.post(
    "http://127.0.0.1:8000/api/find-paths-multi",
    json=payload,
    timeout=10,
)
response.raise_for_status()
data = response.json()
print(data["results"][0]["next_move"])
```

`requests` tidak tercantum dalam `requirements.txt`; instal dengan `pip install requests` bila diperlukan.

### JavaScript (`fetch`)

```javascript
const res = await fetch('/api/find-paths-multi', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ grid, enemies }),
});
const data = await res.json();
if (data.status === 'success') {
  for (const item of data.results) {
    console.log(item.id, item.next_move, item.full_path);
  }
}
```

Pemanggilan ini bekerja bila halaman dan API berada di origin yang sama. Untuk origin berbeda, tambahkan middleware CORS terlebih dahulu.

### Banyak algoritma dalam satu request

```json
{
  "grid": [[1,1,1],[1,0,1],[1,1,1]],
  "enemies": [
    { "id": 1, "pos": [1,1], "target": [1,2], "algorithm": "A_STAR", "max_depth": 0 },
    { "id": 2, "pos": [1,1], "target": [1,2], "algorithm": "GBFS", "max_depth": 2 }
  ]
}
```

Kedua hasil dihitung independen dengan snapshot grid yang sama. Perubahan grid akibat bom tidak dimodelkan di dalam satu request.

### Membandingkan depth limit

```json
{
  "grid": [[1,1,1,1,1],[1,0,0,0,1],[1,0,0,0,1],[1,0,0,0,1],[1,1,1,1,1]],
  "enemies": [
    { "id": 1, "pos": [1,1], "target": [3,3], "algorithm": "A_STAR", "max_depth": 2 },
    { "id": 2, "pos": [1,1], "target": [3,3], "algorithm": "A_STAR", "max_depth": 0 }
  ]
}
```

Musuh pertama akan berhenti pada kedalaman 2 dan mengembalikan path parsial; musuh kedua dapat mencapai target.

---

## GET `/`

Mengembalikan halaman HTML lengkap (CSS dan JavaScript inline) untuk simulasi, termasuk tiga layar setup dan arena. Respons memakai header `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` agar perubahan UI langsung terlihat.

```bash
curl http://127.0.0.1:8000/ -o arena.html
```

Halaman memuat aset font dari Google Fonts; tanpa koneksi internet, font akan jatuh ke fallback sistem tanpa memengaruhi fungsi.

## Dokumentasi interaktif

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- Skema mentah: <http://127.0.0.1:8000/openapi.json>

Gunakan Swagger UI untuk mencoba endpoint secara langsung tanpa menulis klien.
