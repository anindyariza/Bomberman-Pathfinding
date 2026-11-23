# Referensi API

Server dibangun dengan FastAPI dan berjalan secara default di `http://127.0.0.1:8000`.

| Method | Path | Tipe respons | Keterangan |
| --- | --- | --- | --- |
| `GET` | `/` | `text/html` | Antarmuka simulasi |
| `POST` | `/api/find-paths-multi` | `application/json` | Hitung path untuk satu atau banyak musuh |
| `GET` | `/docs` | `text/html` | Swagger UI |
| `GET` | `/redoc` | `text/html` | ReDoc |
| `GET` | `/openapi.json` | `application/json` | Skema OpenAPI |

API bersifat **stateless**: tidak ada autentikasi, cookie, atau sesi. CORS terbuka untuk semua origin (`allow_origins=["*"]`), sehingga cocok untuk alat lokal dan eksperimen.

---

## POST `/api/find-paths-multi`

Menghitung rute untuk setiap musuh dalam satu request. Setiap musuh dapat memakai algoritma yang berbeda.

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
| `id` | `integer` | Ya | — | Identifier unik untuk pencocokan hasil. Server tidak memvalidasi keunikan. |
| `pos` | `[int, int]` | Ya | — | Posisi awal `[baris, kolom]`. Harus di dalam grid dan sebaiknya ubin lantai. |
| `target` | `[int, int]` | Ya | — | Posisi tujuan `[baris, kolom]`. Jika tidak terjangkau, server memakai path fallback. |
| `algorithm` | `string` | Ya | — | `BFS`, `UCS`, `DIJKSTRA`, `GBFS`, `A_STAR`, atau `A*`. Case-insensitive. |
| `history` | `array[[int, int]]` | Tidak | `[]` | Posisi yang pernah dilewati, dari terlama ke terbaru. Frontend mengirim maksimal 22 entri. |
| `danger` | `array[[int, int]]` | Tidak | `[]` | Ubin yang berpotensi terkena ledakan. Setiap ubin mendapat penalti biaya `+35`. |

Catatan:

- Nilai di luar `0`/`2` dianggap tidak dapat dilalui.
- `pos == target` menghasilkan path satu titik dan metrik nol.
- `algorithm` yang tidak dikenal akan melewati semua cabang pencarian; hasilnya path kosong dengan metrik nol.
- Tidak ada batas ukuran grid yang ditegakkan, tetapi baris harus konsisten dan minimal satu sel. Grid kosong atau posisi di luar batas dapat memicu error 500.

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
      "nodes_explored": 8,
      "max_depth": 4,
      "solution_depth": 4,
      "exec_time_ms": 0.067
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
| `results[].algorithm` | `string` | Kode algoritma yang dikirim. |
| `results[].nodes_explored` | `integer` | Jumlah node yang diekspansi. |
| `results[].max_depth` | `integer` | Kedalaman ekspansi maksimum (jumlah edge dari start). |
| `results[].solution_depth` | `integer` | `len(full_path) - 1` bila target tercapai; `0` untuk path fallback. |
| `results[].exec_time_ms` | `number` | Durasi `run_search` dalam milidetik, dibulatkan 3 desimal. |

Contoh path di atas bersifat ilustratif. Karena urutan arah diacak per pencarian, path lain dengan biaya sama dapat muncul.

### Perilaku penting

1. **Target tidak terjangkau** — server mengembalikan path parsial ke node terdekat dari target. `solution_depth` bernilai `0`.
2. **Tidak ada node yang lebih dekat** — `full_path` kosong dan `next_move` sama dengan `enemy_pos`.
3. **Dinding kayu** — dapat dilalui dengan biaya `5.5`; path dapat menembus kayu.
4. **Danger** — hanya penalti biaya, bukan larangan. Ubin bahaya tetap dapat dilalui.
5. **History** — memengaruhi algoritma berbobot; BFS dan GBFS tidak memakai biaya sehingga tidak terpengaruh langsung.
6. **Banyak musuh** — diproses berurutan, bukan paralel. Waktu total kira-kira jumlah waktu masing-masing.
7. **Metrik** — `exec_time_ms` bukan waktu respons HTTP; latensi jaringan dan serialisasi tidak dihitung.

### Error

| Status | Kondisi | Body |
| --- | --- | --- |
| `422 Unprocessable Entity` | Body tidak sesuai skema Pydantic (field hilang, tipe salah, dll.) | Detail validasi standar FastAPI |
| `500 Internal Server Error` | Posisi di luar batas grid, grid tidak konsisten, atau error runtime lain | Pesan error Uvicorn (tidak ada format khusus) |

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

### Banyak algoritma dalam satu request

```json
{
  "grid": [[1,1,1],[1,0,1],[1,1,1]],
  "enemies": [
    { "id": 1, "pos": [1,1], "target": [1,2], "algorithm": "A_STAR" },
    { "id": 2, "pos": [1,1], "target": [1,2], "algorithm": "GBFS" }
  ]
}
```

Kedua hasil dihitung independen dengan snapshot grid yang sama. Perubahan grid akibat bom tidak dimodelkan di dalam satu request.

---

## GET `/`

Mengembalikan halaman HTML lengkap (CSS dan JavaScript inline) untuk simulasi. Tidak ada parameter.

```bash
curl http://127.0.0.1:8000/ -o arena.html
```

Halaman memuat aset font dari Google Fonts; tanpa koneksi internet, font akan jatuh ke fallback sistem tanpa memengaruhi fungsi.

## Dokumentasi interaktif

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- Skema mentah: <http://127.0.0.1:8000/openapi.json>

Gunakan Swagger UI untuk mencoba endpoint secara langsung tanpa menulis klien.
