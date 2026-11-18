import time
import heapq
import random
import itertools
from collections import deque
from typing import List, Tuple, Dict
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Bomberman AI - Balanced Symmetric Arena Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# 1. DATA MODELS
# --------------------------------------------------------------------------
class EnemyInfo(BaseModel):
    id: int
    pos: List[int]
    target: List[int]
    algorithm: str
    history: List[List[int]] = []
    danger: List[List[int]] = []

class MultiPathRequest(BaseModel):
    grid: List[List[int]]
    enemies: List[EnemyInfo]

# --------------------------------------------------------------------------
# 2. PATHFINDING ENGINE (A*, DIJKSTRA, UCS, GBFS, BFS)
# --------------------------------------------------------------------------
WOOD_COST = 5.5
DANGER_COST = 35.0
HISTORY_MAX_PENALTY = 16.0  # > WOOD_COST agar bot memilih buka jalur daripada berputar-putar

BASE_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

def random_dir_order():
    dirs = list(BASE_DIRS)
    random.shuffle(dirs)
    return dirs

def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

def get_neighbors(cell, grid, history_weights, danger_cells, order):
    rows, cols = len(grid), len(grid[0])
    r, c = cell
    neighbors = []
    for dr, dc in order:
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            val = grid[nr][nc]
            extra = history_weights.get((nr, nc), 0.0)
            if (nr, nc) in danger_cells:
                extra += DANGER_COST
            if val == 0:
                neighbors.append(((nr, nc), 1.0 + extra))
            elif val == 2:
                neighbors.append(((nr, nc), WOOD_COST + extra))
    return neighbors

def reconstruct_path(came_from: Dict, start, goal) -> List[List[int]]:
    if goal == start:
        return [[start[0], start[1]]]
    if goal not in came_from:
        return []
    path = []
    curr = goal
    while curr in came_from:
        path.append([curr[0], curr[1]])
        curr = came_from[curr]
    path.append([start[0], start[1]])
    path.reverse()
    return path

def run_search(algo, grid, start, target, history, danger):
    if start == target:
        return [[start[0], start[1]]], 0

    order = random_dir_order()
    counter = itertools.count()

    history_weights: Dict[Tuple[int, int], float] = {}
    total_h = len(history)
    for idx, h in enumerate(history):
        t = (h[0], h[1])
        recency = (idx + 1) / total_h if total_h > 0 else 1.0
        history_weights[t] = history_weights.get(t, 0.0) + recency * HISTORY_MAX_PENALTY
    danger_cells = {(d[0], d[1]) for d in danger}

    nodes_explored = 0
    came_from = {}
    best_fallback = start
    best_fallback_dist = manhattan_distance(start, target)
    algo = algo.upper()

    # 1. BFS: Unweighted shortest-hop search (mengabaikan bobot biaya g(n))
    if algo == "BFS":
        queue = deque([start])
        visited = {start}
        while queue:
            curr = queue.popleft()
            nodes_explored += 1
            d_curr = manhattan_distance(curr, target)
            if d_curr < best_fallback_dist:
                best_fallback_dist = d_curr
                best_fallback = curr
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            for (nxt, _) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    queue.append(nxt)

    # 2. UCS: Weighted lowest-cost search dengan early-exit saat target tercapai
    elif algo == "UCS":
        pq = [(0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float('inf')):
                continue
            nodes_explored += 1
            d_curr = manhattan_distance(curr, target)
            if d_curr < best_fallback_dist:
                best_fallback_dist = d_curr
                best_fallback = curr
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float('inf')):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    heapq.heappush(pq, (new_g, next(counter), nxt))

    # 3. DIJKSTRA: Membangun full shortest-path tree pada seluruh grid terjangkau
    elif algo == "DIJKSTRA":
        pq = [(0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float('inf')):
                continue
            nodes_explored += 1
            d_curr = manhattan_distance(curr, target)
            if d_curr < best_fallback_dist:
                best_fallback_dist = d_curr
                best_fallback = curr
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float('inf')):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    heapq.heappush(pq, (new_g, next(counter), nxt))
        if target in came_from:
            return reconstruct_path(came_from, start, target), nodes_explored

    # 4. GBFS: Pure heuristic f(n) = h(n)
    elif algo == "GBFS":
        pq = [(float(manhattan_distance(start, target)), next(counter), start)]
        visited = {start}
        while pq:
            _, _, curr = heapq.heappop(pq)
            nodes_explored += 1
            d_curr = manhattan_distance(curr, target)
            if d_curr < best_fallback_dist:
                best_fallback_dist = d_curr
                best_fallback = curr
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            for (nxt, _) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    priority = float(manhattan_distance(nxt, target))
                    heapq.heappush(pq, (priority, next(counter), nxt))

    # 5. A*: Optimal f(n) = g(n) + h(n)
    elif algo in ["A_STAR", "A*"]:
        pq = [(float(manhattan_distance(start, target)), 0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            f, curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float('inf')):
                continue
            nodes_explored += 1
            d_curr = manhattan_distance(curr, target)
            if d_curr < best_fallback_dist:
                best_fallback_dist = d_curr
                best_fallback = curr
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float('inf')):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    new_f = new_g + float(manhattan_distance(nxt, target))
                    heapq.heappush(pq, (new_f, new_g, next(counter), nxt))

    if best_fallback != start:
        return reconstruct_path(came_from, start, best_fallback), nodes_explored
    return [], nodes_explored

# --------------------------------------------------------------------------
# 3. FASTAPI REST ENDPOINT
# --------------------------------------------------------------------------
@app.post("/api/find-paths-multi")
def find_paths_multi(req: MultiPathRequest):
    results = []
    for enemy_info in req.enemies:
        start_tuple = (enemy_info.pos[0], enemy_info.pos[1])
        target_tuple = (enemy_info.target[0], enemy_info.target[1])

        t_start = time.perf_counter()
        path, nodes = run_search(
            enemy_info.algorithm,
            req.grid,
            start_tuple,
            target_tuple,
            enemy_info.history,
            enemy_info.danger
        )
        exec_time = round((time.perf_counter() - t_start) * 1000, 3)

        next_move = path[1] if len(path) > 1 else (path[0] if path else enemy_info.pos)
        results.append({
            "id": enemy_info.id,
            "enemy_pos": enemy_info.pos,
            "next_move": next_move,
            "full_path": path,
            "algorithm": enemy_info.algorithm,
            "nodes_explored": nodes,
            "exec_time_ms": exec_time
        })

    return {"status": "success", "results": results}

# --------------------------------------------------------------------------
# 4. FRONTEND
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def get_frontend():
    return """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Bomberman AI | Arena Benchmark</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Barlow+Semi+Condensed:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
        <style>
            :root { --page:#191a18; --panel:#222421; --raised:#292b27; --line:#41443e; --text:#f0f0e9; --muted:#b7b9af; --accent:#d6a84f; --bot-a:#55b8aa; --bot-b:#d6a84f; --danger:#ef6248; --floor:#252723; --wall:#343731; --brick:#62533e; --collapse:#8f3429; --ui:'Barlow Semi Condensed','Arial Narrow',sans-serif; --mono:'IBM Plex Mono','Cascadia Mono',Consolas,monospace; --space:12px; }
            * { box-sizing:border-box; }
            body { margin:0; padding:20px; background:var(--page); color:var(--text); font:16px/1.4 var(--ui); }
            h1 { margin:0 0 4px; font-size:24px; font-weight:600; }
            .page-head { max-width:1160px; margin:0 auto 14px; }
            .page-kicker,.field-label { color:var(--muted); font-size:13px; }
            #statusMsg { min-height:24px; font-size:16px; font-weight:600; }
            #container { display:flex; align-items:flex-start; justify-content:center; gap:14px; max-width:1160px; margin:0 auto; }
            #gameCanvas { display:block; width:min(600px,calc(100vw - 420px)); height:auto; border:1px solid var(--line); background:var(--floor); }
            #panel { background:var(--panel); padding:16px; width:360px; flex:0 0 360px; max-height:calc(100vh - 36px); overflow-y:auto; text-align:left; border:1px solid var(--line); }
            .mode-header,.section-title { margin:0 0 var(--space); padding-bottom:8px; border-bottom:1px solid var(--line); font-size:18px; font-weight:600; }
            .field { display:block; margin:0 0 10px; }
            .field-label { display:block; margin-bottom:4px; }
            select,button { display:block; width:100%; min-height:36px; padding:7px 9px; border:1px solid var(--line); border-radius:3px; background:var(--raised); color:var(--text); font:15px var(--ui); }
            select { cursor:pointer; }
            button { margin:12px 0; background:var(--accent); color:var(--page); border-color:var(--accent); font-weight:700; cursor:pointer; transition:filter .12s ease; }
            button:hover { filter:brightness(1.08); }
            button:disabled { opacity:.55; cursor:not-allowed; }
            :focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
            .bot-a-label { border-left:3px solid var(--bot-a); padding-left:7px; }
            .bot-b-label { border-left:3px solid var(--bot-b); padding-left:7px; }
            .stat { margin-top:8px; padding:8px; background:var(--raised); font-size:14px; }
            .status-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; }
            .status-strip span { min-width:0; }
            .status-strip small { display:block; color:var(--muted); font:12px var(--ui); }
            .status-strip b { font:13px var(--mono); font-variant-numeric:tabular-nums; }
            .status-strip .status-phase { grid-column:1/-1; padding-bottom:5px; border-bottom:1px solid var(--line); color:var(--text); font-weight:600; }
            .stat-box { margin-top:var(--space); padding:10px; border:1px solid var(--line); font-size:14px; }
            .metric-value,.stats-table td { font-family:var(--mono); font-variant-numeric:tabular-nums; }
            .stats-table { width:100%; border-collapse:collapse; margin-top:8px; }
            .stats-table th,.stats-table td { padding:7px 5px; border-bottom:1px solid var(--line); text-align:left; }
            .stats-table th { font-size:14px; font-weight:600; }
            .stats-table td:first-child { color:var(--muted); font-family:var(--ui); }
            .bot-a-head { border-left:3px solid var(--bot-a); padding-left:6px!important; }
            .bot-b-head { border-left:3px solid var(--bot-b); padding-left:6px!important; }
            .rules-box { margin-top:var(--space); padding:8px 0; color:var(--muted); font-size:13px; }
            .rules-box summary { color:var(--text); cursor:pointer; font-size:14px; }
            .rules-box ul { margin:8px 0 0; padding-left:18px; }
            .rules-box li { margin:5px 0; }
            .reload-bar-bg { height:8px; margin-top:5px; overflow:hidden; background:var(--page); border:1px solid var(--line); }
            .reload-bar-fill { width:100%; height:100%; background:var(--accent); transition:width .1s linear; }
            @media(max-width:900px) { body{padding:14px} #container{flex-direction:column;align-items:stretch} #gameCanvas{width:min(100%,600px);margin:0 auto} #panel{width:100%;flex:auto;max-height:none} }
            @media(prefers-reduced-motion:reduce) { *,*::before,*::after{scroll-behavior:auto!important;transition-duration:.01ms!important;animation-duration:.01ms!important} }
        </style>
    </head>
    <body>
        <header class="page-head">
            <h1>Bomberman AI</h1>
            <div class="page-kicker">Arena benchmark</div>
            <div id="statusMsg"></div>
        </header>

        <div id="container">
            <canvas id="gameCanvas" width="600" height="520"></canvas>

            <div id="panel">
                <div class="mode-header">Kontrol ronde</div>
                <label class="field"><span class="field-label">Mode permainan</span><select id="modeSelect">
                    <option value="BvB" selected>Bot vs Bot (BvB Simultan)</option>
                    <option value="PvB">Player vs Bot (PvB)</option>
                </select></label>

                <label class="field"><span class="field-label">Kecepatan</span><select id="speedSelect">
                    <option value="AUTO" selected>Otomatis (eskalasi 1x ke 3x)</option>
                    $11x Normal</option>
                    $12x Cepat</option>
                    $13x Turbo</option>
                </select></label>

                <div id="botAControl" class="field">
                    <label class="field-label bot-a-label"><b>Bot 1 · Persegi</b></label>
                    <select id="algoSelectA">
                        <option value="A_STAR" selected>A* Search Algorithm</option>
                        <option value="DIJKSTRA">Dijkstra Algorithm</option>
                        <option value="UCS">Uniform Cost (UCS)</option>
                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                        <option value="BFS">Breadth-First (BFS)</option>
                    </select>
                </div>

                <div id="botBControl" class="field">
                    <label class="field-label bot-b-label"><b>Bot 2 · Berlian</b></label>
                    <select id="algoSelectB">
                        <option value="A_STAR">A* Search Algorithm</option>
                        <option value="DIJKSTRA" selected>Dijkstra Algorithm</option>
                        <option value="UCS">Uniform Cost (UCS)</option>
                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                        <option value="BFS">Breadth-First (BFS)</option>
                    </select>
                </div>

                <button id="restartBtn">Mulai ronde baru</button>

                <div id="playerStats" style="display: none;">
                    <div class="stat">Nyawa pemain: <span id="healthVal">3</span></div>
                    <div class="stat">
                        Amunisi magazin: <span id="ammoVal">1</span>
                        <div class="reload-bar-bg"><div id="reloadFill" class="reload-bar-fill"></div></div>
                    </div>
                </div>

                <details class="rules-box">
                    <summary>Aturan arena dan eliminasi KO</summary>
                    <ul>
                        <li>Penyusutan simetris 180°: dinding menyusut berpasangan dari kedua sisi hingga pusat 3×5.</li>
                        <li>Pemecah seri seimbang: urutan arah dan prioritas langkah diacak 50:50 tiap tick.</li>
                        <li>Jangkauan ledakan tetap: 3 ubin, mencakup pusat dan satu ubin tiap arah.</li>
                    </ul>
                </details>
                <div class="stat status-strip" id="phaseInfo"></div>

                <section class="stat-box">
                    <h2 class="section-title">Analisis komparasi <span id="winSummary" class="metric-value">B1: 0 | B2: 0 | Seri: 0</span></h2>
                    <table class="stats-table">
                        <thead><tr><th></th><th class="bot-a-head">Bot 1</th><th id="bot2StatsBox" class="bot-b-head bot-b-column">Bot 2</th></tr></thead>
                        <tbody>
                            <tr><td>Algoritma</td><td id="algoNameA">A*</td><td class="bot-b-column" id="algoNameB">Dijkstra</td></tr>
                            <tr><td>Wins</td><td id="winsA">0</td><td class="bot-b-column" id="winsB">0</td></tr>
                            <tr><td>Visited (Avg)</td><td><span id="nodesA">0</span> (<span id="avgNodesA">0</span>)</td><td class="bot-b-column"><span id="nodesB">0</span> (<span id="avgNodesB">0</span>)</td></tr>
                            <tr><td>Time (Avg)</td><td><span id="timeA">0 ms</span> (<span id="avgTimeA">0 ms</span>)</td><td class="bot-b-column"><span id="timeB">0 ms</span> (<span id="avgTimeB">0 ms</span>)</td></tr>
                            <tr><td>Status</td><td id="stateA">HUNT</td><td class="bot-b-column" id="stateB">HUNT</td></tr>
                        </tbody>
                    </table>
                </section>
            </div>
        </div>
        <script>
            const canvas = document.getElementById('gameCanvas');
            const ctx = canvas.getContext('2d');
            const CELL = 40;
            const ROWS = 13, COLS = 15;
            const DIRS4 = [[-1,0], [1,0], [0,-1], [0,1]];
            const FIXED_BLAST_RANGE = 1; // Pusat + 1 ubin tiap arah = 3 ubin konstan
            const COLORS = {
                botA: '#55b8aa', botB: '#d6a84f', player: '#f0f0e9', ink: '#191a18', line: '#41443e', grid: '#30322e',
                floor: '#252723', wall: '#343731', brick: '#62533e', collapse: '#8f3429',
                danger: '#ef6248', pathA: 'rgba(85,184,170,0.22)', pathB: 'rgba(214,168,79,0.22)'
            };

            const MAP_TEMPLATE = [
                [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
                [1,0,0,2,2,2,2,2,2,2,2,2,0,0,1],
                [1,0,1,2,1,2,1,2,1,2,1,2,1,0,1],
                [1,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,0,2,2,2,2,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,2,2,2,2,0,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
                [1,0,1,2,1,2,1,2,1,2,1,2,1,0,1],
                [1,0,0,2,2,2,2,2,2,2,2,2,0,0,1],
                [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
            ];

            // Pasangan koordinat simetris putar 180 derajat agar kedua bot terhimpit secara adil
            function buildSymmetricSpiralPairs() {
                const pairs = [];
                const seen = new Set();
                const addPair = (r, c) => {
                    const mr = ROWS - 1 - r;
                    const mc = COLS - 1 - c;
                    const k1 = `${r},${c}`;
                    const k2 = `${mr},${mc}`;
                    if (seen.has(k1) || seen.has(k2)) return;
                    // Sisakan arena tengah 3x5 (r: 5..7, c: 5..9) tepat di pusat peta
                    if (r >= 5 && r <= 7 && c >= 5 && c <= 9) return;
                    seen.add(k1);
                    seen.add(k2);
                    pairs.push([[r, c], [mr, mc]]);
                };

                for (let layer = 1; layer <= 4; layer++) {
                    const top = layer, bottom = ROWS - 1 - layer;
                    const left = layer, right = COLS - 1 - layer;
                    for (let c = left; c <= right; c++) addPair(top, c);
                    for (let r = top + 1; r <= bottom - 1; r++) addPair(r, right);
                }
                return pairs;
            }
            const SYMMETRIC_SPIRAL_PAIRS = buildSymmetricSpiralPairs();

            let grid, player, enemies, bombs, explosions;
            let playerPixel, enemyPixels;
            let gameOver = false;
            let aiPaths = [];
            let isFetching = false;
            let simTicks = 0;
            let currentGameMode = "BvB";
            let spiralPairIndex = 0;
            let suddenDeathDropTimer = 0;

            let seriesStats = {
                wins1: 0, wins2: 0, draws: 0,
                nodesSum1: 0, timeSum1: 0, calls1: 0,
                nodesSum2: 0, timeSum2: 0, calls2: 0
            };

            function resetSeriesStats() {
                seriesStats = {
                    wins1: 0, wins2: 0, draws: 0,
                    nodesSum1: 0, timeSum1: 0, calls1: 0,
                    nodesSum2: 0, timeSum2: 0, calls2: 0
                };
                updateSeriesHUD();
            }

            function updateSeriesHUD() {
                document.getElementById('winsA').innerText = seriesStats.wins1;
                document.getElementById('winsB').innerText = seriesStats.wins2;
                document.getElementById('winSummary').innerText =
                    `B1: ${seriesStats.wins1} | B2: ${seriesStats.wins2} | Seri: ${seriesStats.draws}`;

                const avgN1 = seriesStats.calls1 ? (seriesStats.nodesSum1 / seriesStats.calls1).toFixed(1) : "0";
                const avgT1 = seriesStats.calls1 ? (seriesStats.timeSum1 / seriesStats.calls1).toFixed(3) + " ms" : "0 ms";
                document.getElementById('avgNodesA').innerText = avgN1;
                document.getElementById('avgTimeA').innerText = avgT1;

                const avgN2 = seriesStats.calls2 ? (seriesStats.nodesSum2 / seriesStats.calls2).toFixed(1) : "0";
                const avgT2 = seriesStats.calls2 ? (seriesStats.timeSum2 / seriesStats.calls2).toFixed(3) + " ms" : "0 ms";
                document.getElementById('avgNodesB').innerText = avgN2;
                document.getElementById('avgTimeB').innerText = avgT2;
            }

            const OVERDRIVE_TICKS = 1200;    // 20 detik
            const SUDDEN_DEATH_TICKS = 2100; // 35 detik

            function getCurrentPhase() {
                if (simTicks >= SUDDEN_DEATH_TICKS) {
                    return { name: "SUDDEN DEATH", autoSpeed: 3, maxBombs: 3, range: FIXED_BLAST_RANGE, fuse: 36 };
                }
                if (simTicks >= OVERDRIVE_TICKS) {
                    return { name: "OVERDRIVE", autoSpeed: 2, maxBombs: 2, range: FIXED_BLAST_RANGE, fuse: 48 };
                }
                return { name: "NORMAL", autoSpeed: 1, maxBombs: 1, range: FIXED_BLAST_RANGE, fuse: 60 };
            }

            function getEffectiveSpeed() {
                const sel = document.getElementById('speedSelect').value;
                if (sel !== "AUTO") return parseInt(sel, 10);
                return getCurrentPhase().autoSpeed;
            }

            function updatePhaseHUD() {
                const phase = getCurrentPhase();
                const spd = getEffectiveSpeed();
                const elapsed = Math.floor(simTicks / 60);
                document.getElementById('phaseInfo').innerHTML =
                    `<span class="status-phase">${phase.name}</span>` +
                    `<span><small>Kecepatan</small><b>${spd}x</b></span>` +
                    `<span><small>Bom</small><b>${phase.maxBombs}</b></span>` +
                    `<span><small>Jangkauan</small><b>3 ubin</b></span>` +
                    `<span><small>Waktu</small><b>${elapsed}s</b></span>`;
            }

            function makeBot(id, name, color, r, c) {
                return {
                    id, name, color, r, c,
                    prevR: r, prevC: c,
                    alive: true,
                    history: [[r, c]],
                    state: 'HUNT',
                    stateTimer: 0,
                    altTarget: null,
                    idle: 0,
                    bombCooldown: 0,
                    recentBombSpots: []
                };
            }

            function initGame() {
                grid = JSON.parse(JSON.stringify(MAP_TEMPLATE));
                currentGameMode = document.getElementById('modeSelect').value;

                if (currentGameMode === "PvB") {
                    document.getElementById('botBControl').style.display = 'none';
                    document.getElementById('bot2StatsBox').style.display = 'none';
                    document.querySelectorAll('.bot-b-column').forEach(el => { el.style.display = 'none'; });
                    document.getElementById('playerStats').style.display = 'block';

                    player = {
                        id: 0, r: 1, c: 1, prevR: 1, prevC: 1,
                        alive: true, health: 3, iFrames: 0,
                        ammo: 1, maxAmmo: 1,
                        isReloading: false, reloadTimer: 0, reloadMaxTimer: 150
                    };
                    enemies = [ makeBot(1, "Bot 1", COLORS.botA, 11, 13) ];
                } else {
                    document.getElementById('botBControl').style.display = 'block';
                    document.getElementById('bot2StatsBox').style.display = '';
                    document.querySelectorAll('.bot-b-column').forEach(el => { el.style.display = ''; });
                    document.getElementById('playerStats').style.display = 'none';

                    player = { id: 0, r: 1, c: 1, prevR: 1, prevC: 1, alive: false, health: 0, iFrames: 0, ammo: 0, maxAmmo: 1 };
                    enemies = [
                        makeBot(1, "Bot 1", COLORS.botA, 1, 1),
                        makeBot(2, "Bot 2", COLORS.botB, 11, 13)
                    ];
                }

                bombs = [];
                explosions = [];
                aiPaths = [];
                gameOver = false;
                isFetching = false;
                simTicks = 0;
                spiralPairIndex = 0;
                suddenDeathDropTimer = 0;
                updatePhaseHUD();

                document.getElementById('statusMsg').innerText = '';
                updateHealthDisplay();
                updateAmmoDisplay();

                playerPixel = { x: player.c * CELL, y: player.r * CELL };
                enemyPixels = enemies.map(e => ({ x: e.c * CELL, y: e.r * CELL }));
            }

            function updateHealthDisplay() {
                document.getElementById('healthVal').innerText = `${player.health} / 3${player.health <= 0 ? ' · Mati' : ''}`;
            }

            function updateAmmoDisplay() {
                const ammoEl = document.getElementById('ammoVal');
                const fillEl = document.getElementById('reloadFill');

                if (player.isReloading) {
                    let progress = ((player.reloadMaxTimer - player.reloadTimer) / player.reloadMaxTimer) * 100;
                    fillEl.style.width = `${progress}%`;
                    ammoEl.innerText = `Mengisi ulang...`;
                    ammoEl.style.color = "";
                } else {
                    fillEl.style.width = `100%`;
                    ammoEl.innerText = player.ammo > 0 ? "1 / 1" : "Kosong";
                    ammoEl.style.color = "";
                }
            }

            function damagePlayer() {
                if (player.iFrames <= 0 && player.alive) {
                    player.health--;
                    player.iFrames = 60;
                    updateHealthDisplay();
                    if (player.health <= 0) {
                        player.alive = false;
                        const algo1 = document.getElementById('algoSelectA').value;
                        seriesStats.wins1++;
                        updateSeriesHUD();
                        setGameOver(false, `Bot 1 (${algo1}) menang KO!`);
                    }
                }
            }

            const STEP_FRAMES = 12;
            const SAFETY_MARGIN = 3;

            function shuffled(arr) {
                const a = [...arr];
                for (let i = a.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [a[i], a[j]] = [a[j], a[i]];
                }
                return a;
            }

            function blastTiles(r, c, range) {
                const tiles = [[r, c]];
                for (const [dr, dc] of DIRS4) {
                    for (let i = 1; i <= range; i++) {
                        const nr = r + dr * i, nc = c + dc * i;
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) break;
                        if (grid[nr][nc] === 1 || grid[nr][nc] === 4) break;
                        tiles.push([nr, nc]);
                        if (grid[nr][nc] === 2 || grid[nr][nc] === 3) break;
                    }
                }
                return tiles;
            }

            function getDangerTimes() {
                const sets = bombs.map(b => blastTiles(b.r, b.c, FIXED_BLAST_RANGE));
                const eff = bombs.map(b => b.timer);
                let changed = true, guard = 0;
                while (changed && guard++ < 10) {
                    changed = false;
                    for (let i = 0; i < bombs.length; i++) {
                        for (let j = 0; j < bombs.length; j++) {
                            if (i !== j && eff[j] < eff[i] &&
                                sets[j].some(t => t[0] === bombs[i].r && t[1] === bombs[i].c)) {
                                eff[i] = eff[j];
                                changed = true;
                            }
                        }
                    }
                }
                const times = new Map();
                sets.forEach((tiles, i) => {
                    tiles.forEach(([nr, nc]) => {
                        const key = `${nr},${nc}`;
                        if (!times.has(key) || times.get(key) > eff[i]) times.set(key, eff[i]);
                    });
                });
                return times;
            }

            function getEscapeMove(startR, startC, times, dirs, blocked) {
                if (!times.has(`${startR},${startC}`)) {
                    return { nextStep: [startR, startC], safeFound: true };
                }
                const MAX_STEPS = 8;
                const queue = [[startR, startC, 0, null]];
                const seen = new Set([`${startR},${startC},0`]);

                while (queue.length > 0) {
                    const [r, c, k, first] = queue.shift();
                    if (k > 0 && !times.has(`${r},${c}`)) {
                        return { nextStep: first, safeFound: true };
                    }
                    if (k >= MAX_STEPS) continue;

                    for (const [dr, dc] of [...dirs, [0, 0]]) {
                        const nr = r + dr, nc = c + dc, nk = k + 1;
                        const stayStep = (dr === 0 && dc === 0);
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) continue;
                        if (!stayStep && grid[nr][nc] !== 0) continue;
                        const key = `${nr},${nc}`;
                        if (!stayStep && blocked && blocked.has(key)) continue;
                        const t = times.get(key);
                        if (t !== undefined && t <= nk * STEP_FRAMES + SAFETY_MARGIN) continue;
                        const sk = `${nr},${nc},${nk}`;
                        if (seen.has(sk)) continue;
                        seen.add(sk);
                        queue.push([nr, nc, nk, first || [nr, nc]]);
                    }
                }
                return { nextStep: [startR, startC], safeFound: false };
            }

            function escapeAfterBomb(r, c, dirs, others) {
                const phase = getCurrentPhase();
                bombs.push({ r, c, timer: phase.fuse, ownerId: -1, range: FIXED_BLAST_RANGE });
                const times = getDangerTimes();
                bombs.pop();
                return getEscapeMove(r, c, times, dirs, others);
            }

            function manhattan(a, b) { return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]); }

            function hasAdjacentWood(r, c) {
                for (const [dr, dc] of DIRS4) {
                    const nr = r + dr, nc = c + dc;
                    if (nr >= 0 && nr < ROWS && nc >= 0 && nc < COLS && grid[nr][nc] === 2) return true;
                }
                return false;
            }

            function walkableNeighborCount(r, c) {
                let count = 0;
                for (const [dr, dc] of DIRS4) {
                    const nr = r + dr, nc = c + dc;
                    if (nr >= 0 && nr < ROWS && nc >= 0 && nc < COLS && grid[nr][nc] === 0) count++;
                }
                return count;
            }

            function isLooping(history) {
                if (!history || history.length < 6) return false;

                const shortRec = history.slice(-8);
                const shortUnique = new Set(shortRec.map(p => `${p[0]},${p[1]}`));
                if (shortRec.length >= 8 && shortUnique.size <= 3) return true;

                const medRec = history.slice(-18);
                if (medRec.length >= 14) {
                    const counts = new Map();
                    let minR = ROWS, maxR = 0, minC = COLS, maxC = 0;
                    for (const [r, c] of medRec) {
                        const k = `${r},${c}`;
                        counts.set(k, (counts.get(k) || 0) + 1);
                        if (r < minR) minR = r;
                        if (r > maxR) maxR = r;
                        if (c < minC) minC = c;
                        if (c > maxC) maxC = c;
                    }
                    for (const cnt of counts.values()) {
                        if (cnt >= 3) return true;
                    }
                    if ((maxR - minR) + (maxC - minC) <= 4) return true;
                }
                return false;
            }

            function getBreakLoopTarget(botR, botC, hunt) {
                const flankCandidates = [];
                for (let r = 1; r < ROWS - 1; r++) {
                    for (let c = 1; c < COLS - 1; c++) {
                        if (grid[r][c] === 0 || grid[r][c] === 2) {
                            const dSelf = manhattan([r, c], [botR, botC]);
                            const dEnemy = manhattan([r, c], hunt);
                            if (dSelf >= 4 && dEnemy <= 4) flankCandidates.push([r, c]);
                        }
                    }
                }
                if (flankCandidates.length > 0) {
                    return flankCandidates[Math.floor(Math.random() * flankCandidates.length)];
                }
                return [Math.floor(ROWS / 2), Math.floor(COLS / 2)];
            }

            function getInterceptTarget(bot, opponent) {
                const oppPos = [opponent.r, opponent.c];
                const dist = manhattan([bot.r, bot.c], oppPos);
                if (dist <= 2) return oppPos;

                const dr = opponent.r - (opponent.prevR ?? opponent.r);
                const dc = opponent.c - (opponent.prevC ?? opponent.c);
                if (dr === 0 && dc === 0) return oppPos;

                for (let step = 2; step >= 1; step--) {
                    const ir = opponent.r + dr * step;
                    const ic = opponent.c + dc * step;
                    if (ir >= 1 && ir < ROWS - 1 && ic >= 1 && ic < COLS - 1 &&
                        grid[ir][ic] !== 1 && grid[ir][ic] !== 4) {
                        return [ir, ic];
                    }
                }
                return oppPos;
            }

            function pickTarget(e, aliveEnemies) {
                let opponent = player;
                if (currentGameMode === "BvB") {
                    const other = aliveEnemies.find(o => o.id !== e.id);
                    if (other) opponent = other;
                }
                const hunt = [opponent.r, opponent.c];

                if (e.state === 'BREAK_LOOP') {
                    const reached = e.altTarget && e.r === e.altTarget[0] && e.c === e.altTarget[1];
                    if (e.stateTimer > 0 && e.altTarget && !reached &&
                        grid[e.altTarget[0]][e.altTarget[1]] !== 4) {
                        e.stateTimer--;
                        return { target: e.altTarget, hunt };
                    }
                    e.state = 'HUNT';
                    e.altTarget = null;
                    e.stateTimer = 0;
                }

                if (isLooping(e.history) || e.idle >= 8) {
                    e.state = 'BREAK_LOOP';
                    e.stateTimer = 18;
                    e.altTarget = getBreakLoopTarget(e.r, e.c, hunt);
                    e.idle = 0;
                    e.history = [[e.r, e.c]];
                    return { target: e.altTarget, hunt };
                }

                const intercept = getInterceptTarget(e, opponent);
                return { target: intercept, hunt };
            }

            function wouldHitEnemy(e, hunt) {
                const phase = getCurrentPhase();
                bombs.push({ r: e.r, c: e.c, timer: phase.fuse, ownerId: -1, range: FIXED_BLAST_RANGE });
                const t2 = getDangerTimes();
                bombs.pop();
                return t2.has(`${hunt[0]},${hunt[1]}`);
            }

            function decideAction(e, resItem, hunt, times, blocked) {
                const stay = { nextR: e.r, nextC: e.c, bomb: false, waitingBomb: false };
                const dirs = shuffled(DIRS4);
                const phase = getCurrentPhase();

                // 1. Jika berada di zona bahaya ledakan -> wajib menghindar dulu
                if (times.has(`${e.r},${e.c}`)) {
                    const esc = getEscapeMove(e.r, e.c, times, dirs, blocked);
                    if (esc.safeFound) return { nextR: esc.nextStep[0], nextC: esc.nextStep[1], bomb: false, waitingBomb: false };
                    return stay;
                }

                const ownBombsCount = bombs.filter(b => b.ownerId === e.id).length;
                const canPlaceMoreBombs = (ownBombsCount < phase.maxBombs) &&
                                          grid[e.r][e.c] === 0 &&
                                          !bombs.some(b => b.r === e.r && b.c === e.c);

                const path = resItem.full_path || [];
                const next = path.length > 1 ? path[1] : null;

                const tryBomb = () => {
                    if (!canPlaceMoreBombs) return null;
                    const esc = escapeAfterBomb(e.r, e.c, dirs, blocked);
                    if (esc.safeFound) return { nextR: esc.nextStep[0], nextC: esc.nextStep[1], bomb: true, waitingBomb: false };
                    return null;
                };

                // 2. Hancurkan kotak kayu yang menghalangi rute menuju lawan
                if (next && grid[next[0]][next[1]] === 2) {
                    const b = tryBomb();
                    if (b) return b;
                    if (ownBombsCount > 0) return { nextR: e.r, nextC: e.c, bomb: false, waitingBomb: true };
                    return stay;
                }

                // 3. Serangan langsung & Pinch Trap
                const bombedRecentlyHere = e.recentBombSpots.some(s => s.r === e.r && s.c === e.c);
                const enemyCornered = walkableNeighborCount(hunt[0], hunt[1]) <= 2;
                const distToEnemy = manhattan([e.r, e.c], hunt);

                const directHit = (distToEnemy <= FIXED_BLAST_RANGE) && wouldHitEnemy(e, hunt);
                const pinchTrap = (phase.maxBombs >= 2) && (distToEnemy <= FIXED_BLAST_RANGE + 1) && (ownBombsCount === 1);

                const canOffensiveBomb = (e.bombCooldown <= 0) &&
                                         (!bombedRecentlyHere || hasAdjacentWood(e.r, e.c) || enemyCornered || pinchTrap);

                if (canPlaceMoreBombs && canOffensiveBomb && (directHit || pinchTrap)) {
                    const b = tryBomb();
                    if (b) return b;
                }

                // 4. Ikuti jalur pathfinding
                if (next) {
                    const [nr, nc] = next;
                    const key = `${nr},${nc}`;
                    if (grid[nr][nc] === 0 && !times.has(key) && !blocked.has(key)) {
                        return { nextR: nr, nextC: nc, bomb: false, waitingBomb: false };
                    }
                    if (times.has(key) && ownBombsCount > 0) {
                        return { nextR: e.r, nextC: e.c, bomb: false, waitingBomb: true };
                    }
                    if (blocked.has(key)) {
                        for (const [dr, dc] of dirs) {
                            const fr = e.r + dr, fc = e.c + dc;
                            const fkey = `${fr},${fc}`;
                            if (fr >= 0 && fr < ROWS && fc >= 0 && fc < COLS &&
                                grid[fr][fc] === 0 && !times.has(fkey) && !blocked.has(fkey)) {
                                return { nextR: fr, nextC: fc, bomb: false, waitingBomb: false };
                            }
                        }
                    }
                    return stay;
                }

                // 5. Fallback langkah aman
                if (e.state === 'BREAK_LOOP') e.stateTimer = 0;
                for (const [dr, dc] of dirs) {
                    const fr = e.r + dr, fc = e.c + dc;
                    const key = `${fr},${fc}`;
                    if (fr >= 0 && fr < ROWS && fc >= 0 && fc < COLS && grid[fr][fc] === 0 &&
                        !times.has(key) && !blocked.has(key)) {
                        return { nextR: fr, nextC: fc, bomb: false, waitingBomb: false };
                    }
                }
                return stay;
            }

            async function moveEnemiesRealtime() {
                if (gameOver || isFetching) return;
                const aliveEnemies = enemies.filter(e => e.alive);
                if (aliveEnemies.length === 0) return;

                isFetching = true;
                const algoA = document.getElementById('algoSelectA').value;
                const algoB = document.getElementById('algoSelectB').value;
                document.getElementById('algoNameA').innerText = algoA;
                document.getElementById('algoNameB').innerText = algoB;

                const dangerBefore = [...getDangerTimes().keys()].map(s => s.split(',').map(Number));
                const huntTargets = {};

                const enemyPayload = aliveEnemies.map(e => {
                    if (e.bombCooldown > 0) e.bombCooldown--;
                    e.recentBombSpots = e.recentBombSpots
                        .map(s => ({ ...s, ttl: s.ttl - 1 }))
                        .filter(s => s.ttl > 0);

                    const { target, hunt } = pickTarget(e, aliveEnemies);
                    huntTargets[e.id] = hunt;
                    document.getElementById(e.id === 1 ? 'stateA' : 'stateB').innerText = e.state;
                    return {
                        id: e.id,
                        pos: [e.r, e.c],
                        target: target,
                        algorithm: e.id === 1 ? algoA : algoB,
                        history: e.history || [],
                        danger: dangerBefore
                    };
                });

                try {
                    const res = await fetch('/api/find-paths-multi', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ grid: grid, enemies: enemyPayload })
                    });
                    const data = await res.json();

                    if (data.status === 'success') {
                        aiPaths = [];
                        const claimedTiles = new Set();
                        if (player.alive) claimedTiles.add(`${player.r},${player.c}`);
                        aliveEnemies.forEach(e => claimedTiles.add(`${e.r},${e.c}`));

                        const orderedResults = (Math.random() < 0.5)
                            ? [...data.results].reverse()
                            : data.results;

                        orderedResults.forEach((resItem) => {
                            const enemyObj = enemies.find(e => e.id === resItem.id);
                            if (!enemyObj || !enemyObj.alive) return;

                            if (enemyObj.id === 1) {
                                document.getElementById('nodesA').innerText = resItem.nodes_explored;
                                document.getElementById('timeA').innerText = resItem.exec_time_ms + ' ms';
                                seriesStats.nodesSum1 += resItem.nodes_explored;
                                seriesStats.timeSum1 += resItem.exec_time_ms;
                                seriesStats.calls1++;
                            } else {
                                document.getElementById('nodesB').innerText = resItem.nodes_explored;
                                document.getElementById('timeB').innerText = resItem.exec_time_ms + ' ms';
                                seriesStats.nodesSum2 += resItem.nodes_explored;
                                seriesStats.timeSum2 += resItem.exec_time_ms;
                                seriesStats.calls2++;
                            }
                            updateSeriesHUD();

                            aiPaths.push({ path: resItem.full_path, color: enemyObj.color });

                            claimedTiles.delete(`${enemyObj.r},${enemyObj.c}`);
                            const times = getDangerTimes();
                            const action = decideAction(enemyObj, resItem, huntTargets[enemyObj.id], times, claimedTiles);

                            if (action.bomb) {
                                placeBotBomb(enemyObj.r, enemyObj.c, enemyObj.id);
                                enemyObj.recentBombSpots.push({ r: enemyObj.r, c: enemyObj.c, ttl: 12 });
                                enemyObj.bombCooldown = 2;
                            }

                            const moved = (action.nextR !== enemyObj.r || action.nextC !== enemyObj.c);
                            enemyObj.prevR = enemyObj.r;
                            enemyObj.prevC = enemyObj.c;
                            enemyObj.r = action.nextR;
                            enemyObj.c = action.nextC;
                            claimedTiles.add(`${enemyObj.r},${enemyObj.c}`);

                            if (moved) {
                                enemyObj.idle = 0;
                                enemyObj.history.push([enemyObj.r, enemyObj.c]);
                                if (enemyObj.history.length > 22) enemyObj.history.shift();
                            } else if (!action.waitingBomb) {
                                enemyObj.idle++;
                            }
                        });
                    }
                } catch (err) {
                    console.error("Error API:", err);
                } finally {
                    isFetching = false;
                }
            }

            function placeBomb() {
                if (currentGameMode === "BvB" || !player.alive || gameOver || player.isReloading || player.ammo <= 0) return;
                if (bombs.some(b => b.ownerId === player.id)) return;
                if (grid[player.r][player.c] !== 0 || bombs.some(b => b.r === player.r && b.c === player.c)) return;

                bombs.push({ id: Date.now(), ownerId: player.id, r: player.r, c: player.c, timer: 110, maxTimer: 110, range: FIXED_BLAST_RANGE });
                grid[player.r][player.c] = 3;

                player.ammo--;
                updateAmmoDisplay();
                player.isReloading = true;
                player.reloadTimer = player.reloadMaxTimer;
            }

            function placeBotBomb(r, c, botId) {
                const phase = getCurrentPhase();
                const ownCount = bombs.filter(b => b.ownerId === botId).length;
                if (ownCount >= phase.maxBombs) return;
                if (grid[r][c] !== 0 || bombs.some(b => b.r === r && b.c === c)) return;

                bombs.push({
                    id: Date.now() + Math.random(),
                    ownerId: botId,
                    r: r,
                    c: c,
                    timer: phase.fuse,
                    maxTimer: phase.fuse,
                    range: FIXED_BLAST_RANGE
                });
                grid[r][c] = 3;
            }

            function updateSuddenDeathCollapse() {
                if (simTicks < SUDDEN_DEATH_TICKS) return;
                suddenDeathDropTimer++;
                if (suddenDeathDropTimer >= 75 && spiralPairIndex < SYMMETRIC_SPIRAL_PAIRS.length) {
                    suddenDeathDropTimer = 0;
                    const pair = SYMMETRIC_SPIRAL_PAIRS[spiralPairIndex++];
                    for (const [sr, sc] of pair) {
                        if (grid[sr][sc] !== 1) {
                            for (let i = bombs.length - 1; i >= 0; i--) {
                                if (bombs[i].r === sr && bombs[i].c === sc) bombs.splice(i, 1);
                            }
                            grid[sr][sc] = 4;
                            if (player.alive && player.r === sr && player.c === sc) {
                                player.alive = false;
                            }
                            enemies.forEach(e => {
                                if (e.alive && e.r === sr && e.c === sc) e.alive = false;
                            });
                        }
                    }
                    if (currentGameMode === "PvB" && !player.alive) {
                        const algo1 = document.getElementById('algoSelectA').value;
                        seriesStats.wins1++;
                        updateSeriesHUD();
                        setGameOver(false, `Bot 1 (${algo1}) menang; pemain terjepit arena.`);
                    } else {
                        checkWinCondition();
                    }
                }
            }

            function updateBombsAndExplosions() {
                for (let i = bombs.length - 1; i >= 0; i--) {
                    let b = bombs[i];
                    b.timer--;
                    if (b.timer <= 0) {
                        if (grid[b.r][b.c] === 3) grid[b.r][b.c] = 0;
                        let bombR = b.r, bombC = b.c;
                        bombs.splice(i, 1);
                        explodeBomb(bombR, bombC, FIXED_BLAST_RANGE);
                    }
                }

                for (let i = explosions.length - 1; i >= 0; i--) {
                    let ex = explosions[i];
                    ex.timer--;
                    if (ex.timer <= 0) explosions.splice(i, 1);
                }

                if (player.iFrames > 0) player.iFrames--;

                if (player.isReloading) {
                    player.reloadTimer--;
                    updateAmmoDisplay();
                    if (player.reloadTimer <= 0) {
                        player.isReloading = false;
                        player.ammo = player.maxAmmo;
                        updateAmmoDisplay();
                    }
                }
            }

            function explodeBomb(r, c, range) {
                explosions.push({ r, c, timer: 20 });
                if (player.alive && player.r === r && player.c === c) damagePlayer();
                enemies.forEach(e => { if (e.alive && e.r === r && e.c === c) e.alive = false; });

                for (const [dr, dc] of DIRS4) {
                    for (let i = 1; i <= range; i++) {
                        let nr = r + dr * i, nc = c + dc * i;
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) break;
                        if (grid[nr][nc] === 1 || grid[nr][nc] === 4) break;

                        explosions.push({ r: nr, c: nc, timer: 20 });

                        if (player.alive && player.r === nr && player.c === nc) damagePlayer();
                        enemies.forEach(e => { if (e.alive && e.r === nr && e.c === nc) e.alive = false; });

                        if (grid[nr][nc] === 2) {
                            grid[nr][nc] = 0;
                            break;
                        }
                        if (grid[nr][nc] === 3) {
                            let chainedBomb = bombs.find(b => b.r === nr && b.c === nc);
                            if (chainedBomb) chainedBomb.timer = 0;
                            break;
                        }
                    }
                }

                checkWinCondition();
            }

            function checkWinCondition() {
                if (gameOver) return;
                const aliveBots = enemies.filter(e => e.alive);
                const algoA = document.getElementById('algoSelectA').value;
                const algoB = document.getElementById('algoSelectB').value;

                if (currentGameMode === "PvB") {
                    if (aliveBots.length === 0 && player.alive) {
                        seriesStats.wins2++;
                        updateSeriesHUD();
                        setGameOver(true, `Pemain menang KO mengalahkan Bot 1 (${algoA})!`);
                    }
                } else {
                    if (aliveBots.length === 1) {
                        const winner = aliveBots[0];
                        const winAlgo = winner.id === 1 ? algoA : algoB;
                        if (winner.id === 1) seriesStats.wins1++;
                        else seriesStats.wins2++;
                        updateSeriesHUD();
                        setGameOver(true, `${winner.name} (${winAlgo}) menang KO!`);
                    } else if (aliveBots.length === 0) {
                        seriesStats.draws++;
                        updateSeriesHUD();
                        setGameOver(false, `Double KO! Kedua algoritma (${algoA} & ${algoB}) tereliminasi bersamaan!`);
                    }
                }
            }

            function setGameOver(isWin, text) {
                gameOver = true;
                const msg = document.getElementById('statusMsg');
                msg.innerText = text;
                msg.style.color = isWin ? 'var(--bot-a)' : 'var(--danger)';
            }

            function lerp(start, end, amt) { return (1 - amt) * start + amt * end; }

            function drawPlayer(x, y) {
                if (player.iFrames % 10 > 5) return;
                ctx.fillStyle = COLORS.player;
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + CELL/2, CELL/2 - 5, 0, Math.PI*2);
                ctx.fill();
                ctx.strokeStyle = COLORS.ink;
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.fillStyle = COLORS.ink;
                ctx.fillRect(x + CELL/2 - 7, y + CELL/2 - 4, 3, 5);
                ctx.fillRect(x + CELL/2 + 4, y + CELL/2 - 4, 3, 5);
            }

            function drawEnemyBot(x, y, color) {
                ctx.fillStyle = color;
                ctx.beginPath();
                if (color === COLORS.botA) {
                    ctx.rect(x + 7, y + 7, CELL - 14, CELL - 14);
                } else {
                    ctx.moveTo(x + CELL/2, y + 5);
                    ctx.lineTo(x + CELL - 5, y + CELL/2);
                    ctx.lineTo(x + CELL/2, y + CELL - 5);
                    ctx.lineTo(x + 5, y + CELL/2);
                    ctx.closePath();
                }
                ctx.fill();
                ctx.strokeStyle = COLORS.ink;
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.fillStyle = COLORS.ink;
                ctx.fillRect(x + CELL/2 - 7, y + CELL/2 - 4, 4, 5);
                ctx.fillRect(x + CELL/2 + 3, y + CELL/2 - 4, 4, 5);
            }

            function drawBomb(x, y, timer) {
                let pulse = (timer < 24 && timer % 6 < 3) ? 2 : 0;
                ctx.fillStyle = pulse ? COLORS.danger : COLORS.wall;
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + CELL/2 + 2, CELL/2 - 6 + pulse, 0, Math.PI*2);
                ctx.fill();

                ctx.fillStyle = COLORS.player;
                ctx.beginPath();
                ctx.arc(x + CELL/2 - 4, y + CELL/2 - 2, 3, 0, Math.PI*2);
                ctx.fill();

                ctx.strokeStyle = COLORS.botB;
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.moveTo(x + CELL/2, y + 10);
                ctx.lineTo(x + CELL/2 + 6, y + 4);
                ctx.stroke();

                ctx.fillStyle = COLORS.danger;
                ctx.beginPath();
                ctx.arc(x + CELL/2 + 6, y + 4, 4 + (pulse ? 2 : 0), 0, Math.PI*2);
                ctx.fill();
            }

            function render() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                for (let r = 0; r < ROWS; r++) {
                    for (let c = 0; c < COLS; c++) {
                        const x = c * CELL, y = r * CELL;
                        if (grid[r][c] === 1) {
                            ctx.fillStyle = COLORS.wall;
                            ctx.fillRect(x, y, CELL, CELL);
                            ctx.strokeStyle = COLORS.line;
                            ctx.lineWidth = 1;
                            ctx.strokeRect(x + 4, y + 4, CELL - 8, CELL - 8);
                        } else if (grid[r][c] === 2) {
                            ctx.fillStyle = COLORS.brick;
                            ctx.fillRect(x, y, CELL, CELL);
                            ctx.strokeStyle = COLORS.floor;
                            ctx.lineWidth = 2;
                            ctx.beginPath();
                            ctx.moveTo(x, y + 13); ctx.lineTo(x + CELL, y + 13);
                            ctx.moveTo(x, y + 27); ctx.lineTo(x + CELL, y + 27);
                            ctx.moveTo(x + 13, y); ctx.lineTo(x + 13, y + 13);
                            ctx.moveTo(x + 27, y + 13); ctx.lineTo(x + 27, y + 27);
                            ctx.moveTo(x + 13, y + 27); ctx.lineTo(x + 13, y + CELL);
                            ctx.stroke();
                        } else if (grid[r][c] === 4) {
                            ctx.fillStyle = COLORS.collapse;
                            ctx.fillRect(x, y, CELL, CELL);
                            ctx.strokeStyle = COLORS.danger;
                            ctx.lineWidth = 2;
                            ctx.strokeRect(x + 4, y + 4, CELL - 8, CELL - 8);
                            ctx.beginPath(); ctx.moveTo(x + 7, y + 33); ctx.lineTo(x + 33, y + 7); ctx.stroke();
                        } else {
                            ctx.fillStyle = COLORS.floor;
                            ctx.fillRect(x, y, CELL, CELL);
                            ctx.strokeStyle = COLORS.grid;
                            ctx.lineWidth = 1;
                            ctx.strokeRect(x, y, CELL, CELL);
                        }
                    }
                }

                aiPaths.forEach(item => {
                    ctx.fillStyle = item.color === COLORS.botA ? COLORS.pathA : COLORS.pathB;
                    item.path.forEach(p => {
                        ctx.fillRect(p[1] * CELL + 10, p[0] * CELL + 10, CELL - 20, CELL - 20);
                    });
                });

                bombs.forEach(b => drawBomb(b.c * CELL, b.r * CELL, b.timer));

                ctx.fillStyle = COLORS.danger;
                explosions.forEach(ex => ctx.fillRect(ex.c * CELL, ex.r * CELL, CELL - 1, CELL - 1));

                if (player.alive) {
                    playerPixel.x = lerp(playerPixel.x, player.c * CELL, 0.32);
                    playerPixel.y = lerp(playerPixel.y, player.r * CELL, 0.32);
                    drawPlayer(playerPixel.x, playerPixel.y);
                }

                enemies.forEach((e, idx) => {
                    if (e.alive) {
                        enemyPixels[idx].x = lerp(enemyPixels[idx].x, e.c * CELL, 0.32);
                        enemyPixels[idx].y = lerp(enemyPixels[idx].y, e.r * CELL, 0.32);
                        drawEnemyBot(enemyPixels[idx].x, enemyPixels[idx].y, e.color);
                    }
                });
            }

            function stepSimulationOnce() {
                if (gameOver) return;
                simTicks++;
                if (simTicks % 20 === 0) updatePhaseHUD();
                updateSuddenDeathCollapse();
                updateBombsAndExplosions();
                if (!gameOver && simTicks % 12 === 0) {
                    moveEnemiesRealtime();
                }
            }

            function gameLoop() {
                const steps = gameOver ? 0 : getEffectiveSpeed();
                for (let s = 0; s < steps; s++) {
                    stepSimulationOnce();
                    if (gameOver) break;
                }
                render();
                requestAnimationFrame(gameLoop);
            }

            window.addEventListener('keydown', (e) => {
                if (gameOver || !player.alive || currentGameMode === "BvB") return;

                let nr = player.r, nc = player.c;
                if (e.key === 'w' || e.key === 'ArrowUp') nr--;
                if (e.key === 's' || e.key === 'ArrowDown') nr++;
                if (e.key === 'a' || e.key === 'ArrowLeft') nc--;
                if (e.key === 'd' || e.key === 'ArrowRight') nc++;

                if (grid[nr] && grid[nr][nc] === 0) {
                    player.prevR = player.r;
                    player.prevC = player.c;
                    player.r = nr;
                    player.c = nc;
                }

                if (e.code === 'Space') {
                    e.preventDefault();
                    placeBomb();
                }
            });

            document.getElementById('modeSelect').addEventListener('change', () => { resetSeriesStats(); initGame(); });
            document.getElementById('speedSelect').addEventListener('change', updatePhaseHUD);
            document.getElementById('algoSelectA').addEventListener('change', () => { resetSeriesStats(); initGame(); });
            document.getElementById('algoSelectB').addEventListener('change', () => { resetSeriesStats(); initGame(); });
            document.getElementById('restartBtn').addEventListener('click', initGame);

            initGame();
            gameLoop();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
