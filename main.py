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
        <title>Bomberman AI - Balanced Symmetric Arena Engine</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #181825; color: #cdd6f4; text-align: center; margin: 15px; }
            #container { display: flex; justify-content: center; gap: 20px; margin-top: 10px; }
            canvas { border: 3px solid #cba6f7; background: #1e1e2e; border-radius: 8px; }
            #panel { background: #313244; padding: 20px; border-radius: 8px; width: 360px; text-align: left; }
            select, button { padding: 8px; font-size: 13px; width: 100%; margin-top: 5px; border-radius: 4px; border: none; cursor: pointer; }
            button { background: #a6e3a1; color: #11111b; font-weight: bold; margin-top: 12px; padding: 10px; }
            button:hover { background: #94e2d5; }
            .stat { margin-top: 8px; font-weight: bold; background: #45475a; padding: 8px; border-radius: 4px; font-size: 13px; }
            .stat-box { margin-top: 12px; background: #181825; padding: 10px; border-radius: 6px; border: 1px solid #45475a; font-size: 12px; line-height: 1.5; }
            .reload-bar-bg { background: #313244; border: 1px solid #cba6f7; height: 10px; border-radius: 5px; margin-top: 4px; overflow: hidden; }
            .reload-bar-fill { background: #f9e2af; height: 100%; width: 100%; transition: width 0.1s linear; }
            .mode-header { background: #eba0ac; color: #11111b; padding: 6px; border-radius: 4px; font-weight: bold; margin-bottom: 10px; text-align: center; }
            .rules-box { background: #313244; border: 1px solid #eba0ac; border-radius: 6px; padding: 8px; margin-top: 10px; font-size: 11px; line-height: 1.4; }
        </style>
    </head>
    <body>
        <h2>Bomberman AI - Balanced Symmetric Arena Engine</h2>
        <div id="statusMsg" style="font-weight:bold; font-size:17px; min-height:24px;"></div>

        <div id="container">
            <canvas id="gameCanvas" width="600" height="520"></canvas>

            <div id="panel">
                <div class="mode-header">🎮 MODE & KECEPATAN</div>
                <select id="modeSelect">
                    <option value="BvB" selected>Bot vs Bot (BvB Simultan)</option>
                    <option value="PvB">Player vs Bot (PvB)</option>
                </select>

                <select id="speedSelect" style="margin-top: 6px; background: #45475a; color: #f9e2af; font-weight: bold;">
                    <option value="AUTO" selected>⚡ Speed: Auto Eskalasi (1x → 2x → 3x)</option>
                    <option value="1">▶️ Speed: 1x Normal</option>
                    <option value="2">⏩ Speed: 2x Cepat</option>
                    <option value="3">⏭️ Speed: 3x Turbo</option>
                </select>

                <div id="botAControl" style="margin-top: 10px;">
                    <label style="color: #bd93f9;"><b>🤖 Bot 1 (Ungu):</b></label>
                    <select id="algoSelectA">
                        <option value="A_STAR" selected>A* Search Algorithm</option>
                        <option value="DIJKSTRA">Dijkstra Algorithm</option>
                        <option value="UCS">Uniform Cost (UCS)</option>
                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                        <option value="BFS">Breadth-First (BFS)</option>
                    </select>
                </div>

                <div id="botBControl" style="margin-top: 8px;">
                    <label style="color: #89b4fa;"><b>🤖 Bot 2 (Biru):</b></label>
                    <select id="algoSelectB">
                        <option value="A_STAR">A* Search Algorithm</option>
                        <option value="DIJKSTRA" selected>Dijkstra Algorithm</option>
                        <option value="UCS">Uniform Cost (UCS)</option>
                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                        <option value="BFS">Breadth-First (BFS)</option>
                    </select>
                </div>

                <button id="restartBtn">🔄 Restart Ronde Baru</button>

                <div id="playerStats" style="display: none;">
                    <div class="stat">Nyawa Player: <span id="healthVal">❤️ ❤️ ❤️</span></div>
                    <div class="stat">
                        Amunisi Magazin: <span id="ammoVal">💣</span>
                        <div class="reload-bar-bg"><div id="reloadFill" class="reload-bar-fill"></div></div>
                    </div>
                </div>

                <div class="rules-box">
                    <b>⚖️ Fair Arena & Eliminasi KO:</b>
                    <ul style="padding-left: 16px; margin: 4px 0;">
                        <li><b>180° Symmetric Sudden Death:</b> Dinding menyusut berpasangan simetris dari kedua sisi hingga pusat 3×5.</li>
                        <li><b>Unbiased Tie-Breaking:</b> Urutan arah & prioritas langkah diacak 50:50 tiap tick.</li>
                        <li><b>Fixed Blast Range:</b> Jarak ledakan bom dikunci tetap (3 ubin dari pusat) sepanjang pertandingan.</li>
                    </ul>
                </div>

                <div class="stat" id="phaseInfo"></div>

                <div class="stat-box">
                    <b>📊 Analisis Komparasi (<span id="winSummary">B1: 0 | B2: 0 | Seri: 0</span>)</b>
                    <hr style="border: 0.5px solid #45475a; margin: 6px 0;">
                    <div style="color: #bd93f9;">
                        <b>Bot 1 (<span id="algoNameA">A*</span>) — Wins: <span id="winsA">0</span></b><br>
                        • Visited: <span id="nodesA">0</span> (Avg: <span id="avgNodesA">0</span>)<br>
                        • Time: <span id="timeA">0 ms</span> (Avg: <span id="avgTimeA">0 ms</span>) | <span id="stateA" style="color:#a6e3a1;">HUNT</span>
                    </div>
                    <div id="bot2StatsBox" style="color: #89b4fa; margin-top: 6px;">
                        <hr style="border: 0.5px solid #45475a; margin: 6px 0;">
                        <b>Bot 2 (<span id="algoNameB">Dijkstra</span>) — Wins: <span id="winsB">0</span></b><br>
                        • Visited: <span id="nodesB">0</span> (Avg: <span id="avgNodesB">0</span>)<br>
                        • Time: <span id="timeB">0 ms</span> (Avg: <span id="avgTimeB">0 ms</span>) | <span id="stateB" style="color:#a6e3a1;">HUNT</span>
                    </div>
                </div>
            </div>
        </div>

        <script>
            const canvas = document.getElementById('gameCanvas');
            const ctx = canvas.getContext('2d');
            const CELL = 40;
            const ROWS = 13, COLS = 15;
            const DIRS4 = [[-1,0], [1,0], [0,-1], [0,1]];
            const FIXED_BLAST_RANGE = 2; // Pusat + 2 ubin tiap arah = 3 ubin konstan

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
                    return { name: "🔥 SUDDEN DEATH", autoSpeed: 3, maxBombs: 3, range: FIXED_BLAST_RANGE, fuse: 36 };
                }
                if (simTicks >= OVERDRIVE_TICKS) {
                    return { name: "⚡ OVERDRIVE", autoSpeed: 2, maxBombs: 2, range: FIXED_BLAST_RANGE, fuse: 48 };
                }
                return { name: "⚔️ NORMAL", autoSpeed: 1, maxBombs: 1, range: FIXED_BLAST_RANGE, fuse: 60 };
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
                document.getElementById('phaseInfo').innerText =
                    `${phase.name} (${spd}x) | 💣 ${phase.maxBombs} | 💥 Jarak 3 | ⏱️ ${elapsed}s`;
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
                    document.getElementById('playerStats').style.display = 'block';

                    player = {
                        id: 0, r: 1, c: 1, prevR: 1, prevC: 1,
                        alive: true, health: 3, iFrames: 0,
                        ammo: 1, maxAmmo: 1,
                        isReloading: false, reloadTimer: 0, reloadMaxTimer: 150
                    };
                    enemies = [ makeBot(1, "Bot 1", '#bd93f9', 11, 13) ];
                } else {
                    document.getElementById('botBControl').style.display = 'block';
                    document.getElementById('bot2StatsBox').style.display = 'block';
                    document.getElementById('playerStats').style.display = 'none';

                    player = { id: 0, r: 1, c: 1, prevR: 1, prevC: 1, alive: false, health: 0, iFrames: 0, ammo: 0, maxAmmo: 1 };
                    enemies = [
                        makeBot(1, "Bot 1", '#bd93f9', 1, 1),
                        makeBot(2, "Bot 2", '#89b4fa', 11, 13)
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
                let hearts = "";
                for (let i = 0; i < player.health; i++) hearts += "❤️ ";
                if (player.health <= 0) hearts = "💀 Mati";
                document.getElementById('healthVal').innerText = hearts;
            }

            function updateAmmoDisplay() {
                const ammoEl = document.getElementById('ammoVal');
                const fillEl = document.getElementById('reloadFill');

                if (player.isReloading) {
                    let progress = ((player.reloadMaxTimer - player.reloadTimer) / player.reloadMaxTimer) * 100;
                    fillEl.style.width = `${progress}%`;
                    ammoEl.innerText = `🔄 Reloading...`;
                    ammoEl.style.color = "#f9e2af";
                } else {
                    fillEl.style.width = `100%`;
                    ammoEl.innerText = player.ammo > 0 ? "💣 (1/1)" : "Kosong";
                    ammoEl.style.color = "#cdd6f4";
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
                        setGameOver(false, `🤖 Bot 1 (${algo1}) MENANG KO!`);
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
                        setGameOver(false, `🤖 Bot 1 (${algo1}) MENANG (Player terjepit arena)!`);
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
                        setGameOver(true, `🎉 PLAYER MENANG KO mengalahkan Bot 1 (${algoA})!`);
                    }
                } else {
                    if (aliveBots.length === 1) {
                        const winner = aliveBots[0];
                        const winAlgo = winner.id === 1 ? algoA : algoB;
                        if (winner.id === 1) seriesStats.wins1++;
                        else seriesStats.wins2++;
                        updateSeriesHUD();
                        setGameOver(true, `🏆 ${winner.name} (${winAlgo}) MENANG KO!`);
                    } else if (aliveBots.length === 0) {
                        seriesStats.draws++;
                        updateSeriesHUD();
                        setGameOver(false, `💥 DOUBLE KO! Kedua algoritma (${algoA} & ${algoB}) tereliminasi bersamaan!`);
                    }
                }
            }

            function setGameOver(isWin, text) {
                gameOver = true;
                const msg = document.getElementById('statusMsg');
                msg.innerText = text;
                msg.style.color = isWin ? "#a6e3a1" : "#f38ba8";
            }

            function lerp(start, end, amt) { return (1 - amt) * start + amt * end; }

            function drawPlayer(x, y) {
                if (player.iFrames % 10 > 5) return;
                ctx.fillStyle = '#50fa7b';
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + CELL/2, CELL/2 - 4, 0, Math.PI*2);
                ctx.fill();
                ctx.fillStyle = '#1e1e2e';
                ctx.fillRect(x + CELL/2 - 7, y + CELL/2 - 5, 4, 6);
                ctx.fillRect(x + CELL/2 + 3, y + CELL/2 - 5, 4, 6);
            }

            function drawEnemyBot(x, y, color) {
                ctx.fillStyle = color;
                ctx.fillRect(x + 6, y + 8, CELL - 12, CELL - 12);
                ctx.fillStyle = '#ff79c6';
                ctx.fillRect(x + CELL/2 - 2, y + 2, 4, 6);
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + 2, 3, 0, Math.PI*2);
                ctx.fill();
                ctx.fillStyle = '#ff5555';
                ctx.fillRect(x + 10, y + 14, 6, 6);
                ctx.fillRect(x + CELL - 16, y + 14, 6, 6);
            }

            function drawBomb(x, y, timer) {
                let pulse = (timer < 24 && timer % 6 < 3) ? 2 : 0;
                ctx.fillStyle = pulse ? '#ff5555' : '#21222c';
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + CELL/2 + 2, CELL/2 - 6 + pulse, 0, Math.PI*2);
                ctx.fill();

                ctx.fillStyle = '#6272a4';
                ctx.beginPath();
                ctx.arc(x + CELL/2 - 4, y + CELL/2 - 2, 3, 0, Math.PI*2);
                ctx.fill();

                ctx.strokeStyle = '#ffb86c';
                ctx.lineWidth = 3;
                ctx.beginPath();
                ctx.moveTo(x + CELL/2, y + 10);
                ctx.lineTo(x + CELL/2 + 6, y + 4);
                ctx.stroke();

                ctx.fillStyle = '#ff5555';
                ctx.beginPath();
                ctx.arc(x + CELL/2 + 6, y + 4, 4 + (pulse ? 2 : 0), 0, Math.PI*2);
                ctx.fill();
            }

            function render() {
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                for (let r = 0; r < ROWS; r++) {
                    for (let c = 0; c < COLS; c++) {
                        if (grid[r][c] === 1) ctx.fillStyle = '#45475a';
                        else if (grid[r][c] === 2) ctx.fillStyle = '#ffb86c';
                        else if (grid[r][c] === 4) ctx.fillStyle = '#6e3b4e';
                        else ctx.fillStyle = '#1e1e2e';
                        ctx.fillRect(c * CELL, r * CELL, CELL - 1, CELL - 1);
                    }
                }

                aiPaths.forEach(item => {
                    ctx.fillStyle = item.color === '#bd93f9' ? 'rgba(189, 147, 249, 0.25)' : 'rgba(137, 180, 250, 0.25)';
                    item.path.forEach(p => {
                        ctx.fillRect(p[1] * CELL + 10, p[0] * CELL + 10, CELL - 20, CELL - 20);
                    });
                });

                bombs.forEach(b => drawBomb(b.c * CELL, b.r * CELL, b.timer));

                ctx.fillStyle = 'rgba(255, 85, 85, 0.85)';
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