import time
import heapq
import itertools
from collections import deque
from typing import List, Tuple, Dict
from pydantic import BaseModel
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Bomberman AI - Anti Endless Loop Engine (Fixed)")

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
# 2. PATHFINDING (Balanced Costs so Bots Break Walls Instead of Looping)
# --------------------------------------------------------------------------
WOOD_COST = 6.0
DANGER_COST = 35.0
HISTORY_MAX_PENALTY = 14.0  # > WOOD_COST (6.0) agar bot memilih hancurkan kayu daripada muter-muter

DIR_ORDER = [
    [(-1, 0), (1, 0), (0, -1), (0, 1)],
    [(1, 0), (-1, 0), (0, 1), (0, -1)],
]

def dir_order_for(bot_id: int):
    return DIR_ORDER[(bot_id + 1) % 2]

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

def reconstruct_path(came_from: Dict, start, target) -> List[List[int]]:
    path = []
    curr = target
    while curr in came_from:
        path.append([curr[0], curr[1]])
        curr = came_from[curr]
    path.append([start[0], start[1]])
    path.reverse()
    return path

def run_search(algo, grid, start, target, history, danger, bot_id):
    if start == target:
        return [[start[0], start[1]]], 0

    order = dir_order_for(bot_id)
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
    algo = algo.upper()

    if algo == "BFS":
        queue = deque([start])
        visited = {start}
        while queue:
            curr = queue.popleft()
            nodes_explored += 1
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            nbrs = get_neighbors(curr, grid, history_weights, danger_cells, order)
            nbrs.sort(key=lambda x: x[1])
            for (nxt, _) in nbrs:
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    queue.append(nxt)

    elif algo in ["DIJKSTRA", "UCS"]:
        pq = [(0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            curr_g, _, curr = heapq.heappop(pq)
            nodes_explored += 1
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            if curr_g > g_score.get(curr, float('inf')):
                continue
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float('inf')):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    heapq.heappush(pq, (new_g, next(counter), nxt))

    elif algo == "GBFS":
        pq = [(float(manhattan_distance(start, target)), next(counter), start)]
        visited = {start}
        while pq:
            _, _, curr = heapq.heappop(pq)
            nodes_explored += 1
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    priority = float(manhattan_distance(nxt, target)) + (cost - 1.0)
                    heapq.heappush(pq, (priority, next(counter), nxt))

    elif algo in ["A_STAR", "A*"]:
        pq = [(float(manhattan_distance(start, target)), 0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            f, curr_g, _, curr = heapq.heappop(pq)
            nodes_explored += 1
            if curr == target:
                return reconstruct_path(came_from, start, target), nodes_explored
            if curr_g > g_score.get(curr, float('inf')):
                continue
            for (nxt, cost) in get_neighbors(curr, grid, history_weights, danger_cells, order):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float('inf')):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    new_f = new_g + float(manhattan_distance(nxt, target))
                    heapq.heappush(pq, (new_f, new_g, next(counter), nxt))

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
            enemy_info.danger,
            enemy_info.id
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
        <title>Bomberman AI - Fixed Anti Loop Engine</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #181825; color: #cdd6f4; text-align: center; margin: 15px; }
            #container { display: flex; justify-content: center; gap: 20px; margin-top: 10px; }
            canvas { border: 3px solid #cba6f7; background: #1e1e2e; border-radius: 8px; }
            #panel { background: #313244; padding: 20px; border-radius: 8px; width: 340px; text-align: left; }
            select, button { padding: 8px; font-size: 13px; width: 100%; margin-top: 5px; border-radius: 4px; border: none; cursor: pointer; }
            button { background: #a6e3a1; color: #11111b; font-weight: bold; margin-top: 12px; padding: 10px; }
            button:hover { background: #94e2d5; }
            .stat { margin-top: 8px; font-weight: bold; background: #45475a; padding: 8px; border-radius: 4px; font-size: 13px; }
            .stat-box { margin-top: 12px; background: #181825; padding: 10px; border-radius: 6px; border: 1px solid #45475a; font-size: 12px; line-height: 1.5; }
            .reload-bar-bg { background: #313244; border: 1px solid #cba6f7; height: 10px; border-radius: 5px; margin-top: 4px; overflow: hidden; }
            .reload-bar-fill { background: #f9e2af; height: 100%; width: 100%; transition: width 0.1s linear; }
            .mode-header { background: #eba0ac; color: #11111b; padding: 6px; border-radius: 4px; font-weight: bold; margin-bottom: 10px; text-align: center; }
            .badge-active { background: #a6e3a1; color: #11111b; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; }
            .rules-box { background: #313244; border: 1px solid #eba0ac; border-radius: 6px; padding: 8px; margin-top: 10px; font-size: 11px; line-height: 1.4; }
        </style>
    </head>
    <body>
        <h2>Bomberman AI - Fixed Anti Loop Engine</h2>
        <div id="statusMsg" style="font-weight:bold; font-size:16px; min-height:22px;"></div>

        <div id="container">
            <canvas id="gameCanvas" width="600" height="520"></canvas>

            <div id="panel">
                <div class="mode-header">🎮 MODE GAME</div>
                <select id="modeSelect">
                    <option value="PvB" selected>Player vs Bot (PvB)</option>
                    <option value="BvB">Bot vs Bot (BvB Simultan)</option>
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

                <div id="botBControl" style="margin-top: 8px; display: none;">
                    <label style="color: #89b4fa;"><b>🤖 Bot 2 (Biru):</b></label>
                    <select id="algoSelectB">
                        <option value="A_STAR">A* Search Algorithm</option>
                        <option value="DIJKSTRA" selected>Dijkstra Algorithm</option>
                        <option value="UCS">Uniform Cost (UCS)</option>
                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                        <option value="BFS">Breadth-First (BFS)</option>
                    </select>
                </div>

                <button id="restartBtn">🔄 Restart Game</button>

                <div id="playerStats">
                    <div class="stat">Nyawa Player: <span id="healthVal">❤️ ❤️ ❤️</span></div>
                    <div class="stat">
                        Amunisi Magazin: <span id="ammoVal">💣</span>
                        <div class="reload-bar-bg"><div id="reloadFill" class="reload-bar-fill"></div></div>
                    </div>
                </div>

                <div class="rules-box">
                    <b>🛡️ Anti-Looping Engine Rules:</b>
                    <ul style="padding-left: 16px; margin: 4px 0;">
                        <li><b>Immediate Evasion:</b> Bot langsung menjauh dari bom tanpa membeku di atas sumbu.</li>
                        <li><b>Anti Repeat-Spot Bombing:</b> Mencegah bot menaruh bom berulang di ubin terbuka yang sama.</li>
                        <li><b>Multi-Cycle Breaker:</b> Mendeteksi pola bolak-balik 2-tile maupun muter 4-6 tile di pilar.</li>
                        <li><b>Sequential Reservation:</b> Dua bot tidak lagi saling bertumpuk di satu ubin kabur.</li>
                    </ul>
                </div>

                <div class="stat" id="blastInfo"></div>

                <div class="stat-box">
                    <b>🧠 Anti-Deadlock System: <span class="badge-active">ACTIVE</span></b>
                    <hr style="border: 0.5px solid #45475a; margin: 6px 0;">
                    <div style="color: #bd93f9;">
                        <b>Bot 1 (<span id="algoNameA">A*</span>):</b><br>
                        • Visited: <span id="nodesA">0</span> nodes | Time: <span id="timeA">0 ms</span><br>
                        • State: <span id="stateA" style="font-weight:bold; color:#a6e3a1;">HUNT</span>
                    </div>
                    <div id="bot2StatsBox" style="color: #89b4fa; margin-top: 6px; display: none;">
                        <hr style="border: 0.5px solid #45475a; margin: 6px 0;">
                        <b>Bot 2 (<span id="algoNameB">Dijkstra</span>):</b><br>
                        • Visited: <span id="nodesB">0</span> nodes | Time: <span id="timeB">0 ms</span><br>
                        • State: <span id="stateB" style="font-weight:bold; color:#a6e3a1;">HUNT</span>
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

            let grid, player, enemies, bombs, explosions;
            let playerPixel, enemyPixels;
            let gameOver = false;
            let aiPaths = [];
            let isFetching = false;
            let currentGameMode = "PvB";
            let matchFrames = 0;
            const MATCH_LIMIT_FRAMES = 5400; // 90 detik
            let scores = { 1: 0, 2: 0 };

            function currentBlastRange() {
                // Sudden Death setelah 45 detik di mode BvB -> jangkauan bom naik jadi 2 agar duel cepat selesai
                if (currentGameMode === "BvB" && matchFrames >= 2700) return 2;
                return 1;
            }

            function updateScoreText() {
                const sdTag = (currentGameMode === "BvB" && matchFrames >= 2700) ? " | 🔥 SUDDEN DEATH (Range 2)" : "";
                document.getElementById('blastInfo').innerText =
                    currentGameMode === "BvB"
                        ? `🧱 Kayu: Bot 1 (${scores[1]}) vs Bot 2 (${scores[2]})${sdTag}`
                        : '🎯 Mode Player vs Bot — Tekan WASD/Panah & Spasi';
            }

            function tickMatch() {
                if (gameOver || currentGameMode !== "BvB") return;
                matchFrames++;
                if (matchFrames % 60 === 0) updateScoreText();
                if (!gameOver && matchFrames >= MATCH_LIMIT_FRAMES) {
                    if (scores[1] > scores[2]) setGameOver(true, `⏱️ Waktu habis! 🏆 Bot 1 menang poin (${scores[1]} : ${scores[2]} kayu hancur)`);
                    else if (scores[2] > scores[1]) setGameOver(true, `⏱️ Waktu habis! 🏆 Bot 2 menang poin (${scores[2]} : ${scores[1]} kayu hancur)`);
                    else setGameOver(false, `⏱️ SERI! Waktu habis, poin sama (${scores[1]} : ${scores[2]}).`);
                }
            }

            function makeBot(id, name, color, r, c) {
                return {
                    id, name, color, r, c,
                    alive: true,
                    history: [[r, c]],
                    state: 'HUNT',
                    stateTimer: 0,
                    altTarget: null,
                    idle: 0,
                    bombCooldown: 0,
                    lastBombPos: null
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
                        id: 0, r: 1, c: 1,
                        alive: true, health: 3, iFrames: 0,
                        ammo: 1, maxAmmo: 1,
                        isReloading: false, reloadTimer: 0, reloadMaxTimer: 180
                    };
                    enemies = [ makeBot(1, "Bot 1", '#bd93f9', 11, 13) ];
                } else {
                    document.getElementById('botBControl').style.display = 'block';
                    document.getElementById('bot2StatsBox').style.display = 'block';
                    document.getElementById('playerStats').style.display = 'none';

                    player = { id: 0, r: 1, c: 1, alive: false, health: 0, iFrames: 0, ammo: 0, maxAmmo: 1 };
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
                matchFrames = 0;
                scores = { 1: 0, 2: 0 };
                updateScoreText();
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
                        setGameOver(false, "Player Kalah!");
                    }
                }
            }

            const STEP_FRAMES = 12;
            const SAFETY_MARGIN = 3;

            function dirsFor(botId) {
                return (botId % 2 === 1)
                    ? [[-1,0], [1,0], [0,-1], [0,1]]
                    : [[1,0], [-1,0], [0,1], [0,-1]];
            }

            function blastTiles(r, c, range) {
                const tiles = [[r, c]];
                for (const [dr, dc] of DIRS4) {
                    for (let i = 1; i <= range; i++) {
                        const nr = r + dr * i, nc = c + dc * i;
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) break;
                        if (grid[nr][nc] === 1) break;
                        tiles.push([nr, nc]);
                        if (grid[nr][nc] === 2 || grid[nr][nc] === 3) break;
                    }
                }
                return tiles;
            }

            function getDangerTimes() {
                const sets = bombs.map(b => blastTiles(b.r, b.c, b.range || 1));
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

            // BFS sadar-waktu: prioritas bergerak menjauh ([...dirs, [0, 0]]) agar bot langsung lari dari sumbu bom
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
                bombs.push({ r, c, timer: 60, ownerId: -1, range: currentBlastRange() });
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

            // Deteksi 2-tile oscillation (A-B-A-B) maupun multi-tile cycle (muter pilar / A-B-C-B-A)
            function isLooping(history) {
                if (!history || history.length < 6) return false;
                const recent = history.slice(-10);
                const unique = new Set(recent.map(p => `${p[0]},${p[1]}`));
                // Jika dalam 10 langkah terakhir hanya mengulang <= 3 ubin unik -> terjebak siklus kecil
                if (recent.length >= 8 && unique.size <= 3) return true;
                // Jika dalam 10 langkah terakhir hanya mengulang <= 4 ubin unik -> muter-muter di area sempit
                if (recent.length === 10 && unique.size <= 4) return true;
                return false;
            }

            function getFarExplorationTarget(botR, botC) {
                let emptyFar = [];
                let woodCandidates = [];
                for (let r = 1; r < ROWS - 1; r++) {
                    for (let c = 1; c < COLS - 1; c++) {
                        const d = manhattan([r, c], [botR, botC]);
                        if (grid[r][c] === 0 && d >= 6) emptyFar.push([r, c]);
                        else if (grid[r][c] === 2 && d >= 4) woodCandidates.push([r, c]);
                    }
                }
                if (emptyFar.length > 0) return emptyFar[Math.floor(Math.random() * emptyFar.length)];
                if (woodCandidates.length > 0) return woodCandidates[Math.floor(Math.random() * woodCandidates.length)];
                return [botR <= 6 ? 11 : 1, botC <= 7 ? 13 : 1];
            }

            function pickTarget(e, aliveEnemies) {
                let hunt = [player.r, player.c];
                if (currentGameMode === "BvB") {
                    const other = aliveEnemies.find(o => o.id !== e.id);
                    if (other) hunt = [other.r, other.c];
                }

                if (e.state === 'BREAK_LOOP') {
                    const reached = e.altTarget && e.r === e.altTarget[0] && e.c === e.altTarget[1];
                    if (e.stateTimer > 0 && e.altTarget && !reached) {
                        e.stateTimer--;
                        return { target: e.altTarget, hunt };
                    }
                    e.state = 'HUNT';
                    e.altTarget = null;
                    e.stateTimer = 0;
                }

                if (isLooping(e.history) || e.idle >= 10) {
                    e.state = 'BREAK_LOOP';
                    e.stateTimer = 30;
                    e.altTarget = getFarExplorationTarget(e.r, e.c);
                    e.idle = 0;
                    e.history = [[e.r, e.c]];
                    return { target: e.altTarget, hunt };
                }
                return { target: hunt, hunt };
            }

            function wouldHitEnemy(e, hunt) {
                bombs.push({ r: e.r, c: e.c, timer: 60, ownerId: -1, range: currentBlastRange() });
                const t2 = getDangerTimes();
                bombs.pop();
                return t2.has(`${hunt[0]},${hunt[1]}`);
            }

            function shuffled(arr) {
                const a = [...arr];
                for (let i = a.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    [a[i], a[j]] = [a[j], a[i]];
                }
                return a;
            }

            function decideAction(e, resItem, hunt, times, blocked) {
                const stay = { nextR: e.r, nextC: e.c, bomb: false };
                const dirs = dirsFor(e.id);

                // 1. Jika di zona bahaya -> WAJIB kabur dulu (jangan pernah taruh bom baru saat terancam)
                if (times.has(`${e.r},${e.c}`)) {
                    const esc = getEscapeMove(e.r, e.c, times, dirs, blocked);
                    if (esc.safeFound) return { nextR: esc.nextStep[0], nextC: esc.nextStep[1], bomb: false };
                    return stay;
                }

                const ownBomb = bombs.some(b => b.ownerId === e.id);
                const bombFree = !ownBomb && grid[e.r][e.c] !== 3;
                const path = resItem.full_path || [];
                const next = path.length > 1 ? path[1] : null;

                const tryBomb = () => {
                    if (!bombFree) return null;
                    const esc = escapeAfterBomb(e.r, e.c, dirs, blocked);
                    if (esc.safeFound) return { nextR: esc.nextStep[0], nextC: esc.nextStep[1], bomb: true };
                    return null;
                };

                // 2. Langkah berikutnya terhalang tembok kayu -> bom untuk membuka jalan
                if (next && grid[next[0]][next[1]] === 2) {
                    return tryBomb() || stay;
                }

                // 3. Serangan taktis ke musuh (hanya saat HUNT, cooldown habis, & tidak mengulang bom di ubin terbuka yang sama)
                const sameAsLastBomb = e.lastBombPos && e.lastBombPos[0] === e.r && e.lastBombPos[1] === e.c;
                const enemyCornered = walkableNeighborCount(hunt[0], hunt[1]) <= 2;
                const canOffensiveBomb = (e.state === 'HUNT') &&
                                         (e.bombCooldown <= 0) &&
                                         (!sameAsLastBomb || hasAdjacentWood(e.r, e.c) || enemyCornered);

                if (bombFree && canOffensiveBomb &&
                    manhattan([e.r, e.c], hunt) <= currentBlastRange() &&
                    wouldHitEnemy(e, hunt)) {
                    const b = tryBomb();
                    if (b) return b;
                }

                // 4. Gerak normal sepanjang jalur pathfinding
                if (next) {
                    const [nr, nc] = next;
                    const key = `${nr},${nc}`;
                    if (grid[nr][nc] === 0 && !times.has(key) && !blocked.has(key)) {
                        return { nextR: nr, nextC: nc, bomb: false };
                    }
                    // Jika jalur terblokir oleh bot lain, coba geser ke ubin aman lain agar tidak deadlock
                    if (blocked.has(key)) {
                        for (const [dr, dc] of shuffled(dirs)) {
                            const fr = e.r + dr, fc = e.c + dc;
                            const fkey = `${fr},${fc}`;
                            if (fr >= 0 && fr < ROWS && fc >= 0 && fc < COLS &&
                                grid[fr][fc] === 0 && !times.has(fkey) && !blocked.has(fkey)) {
                                return { nextR: fr, nextC: fc, bomb: false };
                            }
                        }
                    }
                    return stay;
                }

                // 5. Fallback langkah aman
                if (e.state === 'BREAK_LOOP') e.stateTimer = 0;
                for (const [dr, dc] of shuffled(DIRS4)) {
                    const fr = e.r + dr, fc = e.c + dc;
                    const key = `${fr},${fc}`;
                    if (fr >= 0 && fr < ROWS && fc >= 0 && fc < COLS && grid[fr][fc] === 0 &&
                        !times.has(key) && !blocked.has(key)) {
                        return { nextR: fr, nextC: fc, bomb: false };
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
                        // Lacak posisi yang sudah diklaim pada tick ini agar dua bot tidak bertumpuk di satu tile
                        const claimedTiles = new Set();
                        if (player.alive) claimedTiles.add(`${player.r},${player.c}`);
                        aliveEnemies.forEach(e => claimedTiles.add(`${e.r},${e.c}`));

                        data.results.forEach((resItem) => {
                            const enemyObj = enemies.find(e => e.id === resItem.id);
                            if (!enemyObj || !enemyObj.alive) return;

                            if (enemyObj.id === 1) {
                                document.getElementById('nodesA').innerText = resItem.nodes_explored;
                                document.getElementById('timeA').innerText = resItem.exec_time_ms + ' ms';
                            } else {
                                document.getElementById('nodesB').innerText = resItem.nodes_explored;
                                document.getElementById('timeB').innerText = resItem.exec_time_ms + ' ms';
                            }

                            aiPaths.push({ path: resItem.full_path, color: enemyObj.color });

                            // Bebaskan posisi lama bot ini dari claimedTiles saat menghitung langkahnya
                            claimedTiles.delete(`${enemyObj.r},${enemyObj.c}`);
                            const times = getDangerTimes();
                            const action = decideAction(enemyObj, resItem, huntTargets[enemyObj.id], times, claimedTiles);

                            if (action.bomb) {
                                placeBotBomb(enemyObj.r, enemyObj.c, enemyObj.id);
                                enemyObj.lastBombPos = [enemyObj.r, enemyObj.c];
                                enemyObj.bombCooldown = 3; // jeda 3 langkah sebelum boleh bom ofensif lagi
                            }

                            const moved = (action.nextR !== enemyObj.r || action.nextC !== enemyObj.c);
                            enemyObj.r = action.nextR;
                            enemyObj.c = action.nextC;
                            claimedTiles.add(`${enemyObj.r},${enemyObj.c}`);

                            if (moved) {
                                enemyObj.idle = 0;
                                enemyObj.history.push([enemyObj.r, enemyObj.c]);
                                if (enemyObj.history.length > 25) enemyObj.history.shift();
                            } else {
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
                if (grid[player.r][player.c] === 3 || bombs.some(b => b.r === player.r && b.c === player.c)) return;

                bombs.push({ id: Date.now(), ownerId: player.id, r: player.r, c: player.c, timer: 120, maxTimer: 120, range: 1 });
                grid[player.r][player.c] = 3;

                player.ammo--;
                updateAmmoDisplay();
                player.isReloading = true;
                player.reloadTimer = player.reloadMaxTimer;
            }

            function placeBotBomb(r, c, botId) {
                if (bombs.some(b => b.ownerId === botId)) return;
                if (grid[r][c] === 3 || bombs.some(b => b.r === r && b.c === c)) return;

                bombs.push({
                    id: Date.now() + Math.random(),
                    ownerId: botId,
                    r: r,
                    c: c,
                    timer: 60,
                    maxTimer: 60,
                    range: currentBlastRange()
                });
                grid[r][c] = 3;
            }

            function updateBombsAndExplosions() {
                for (let i = bombs.length - 1; i >= 0; i--) {
                    let b = bombs[i];
                    b.timer--;
                    if (b.timer <= 0) {
                        grid[b.r][b.c] = 0;
                        let bombR = b.r, bombC = b.c, ownerId = b.ownerId, range = b.range || 1;
                        bombs.splice(i, 1);
                        explodeBomb(bombR, bombC, ownerId, range);
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

            function explodeBomb(r, c, ownerId, range) {
                explosions.push({ r, c, timer: 20 });
                if (player.alive && player.r === r && player.c === c) damagePlayer();
                enemies.forEach(e => { if (e.alive && e.r === r && e.c === c) e.alive = false; });

                for (const [dr, dc] of DIRS4) {
                    for (let i = 1; i <= range; i++) {
                        let nr = r + dr * i, nc = c + dc * i;
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) break;
                        if (grid[nr][nc] === 1) break;

                        explosions.push({ r: nr, c: nc, timer: 20 });

                        if (player.alive && player.r === nr && player.c === nc) damagePlayer();
                        enemies.forEach(e => { if (e.alive && e.r === nr && e.c === nc) e.alive = false; });

                        if (grid[nr][nc] === 2) {
                            grid[nr][nc] = 0;
                            if (scores[ownerId] !== undefined) {
                                scores[ownerId]++;
                                updateScoreText();
                            }
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
                const aliveBots = enemies.filter(e => e.alive);
                if (currentGameMode === "PvB") {
                    if (aliveBots.length === 0 && player.alive) {
                        setGameOver(true, "🎉 KAMU MENANG! Bot berhasil dikalahkan!");
                    }
                } else {
                    if (aliveBots.length === 1) {
                        setGameOver(true, `🏆 ${aliveBots[0].name} BERHASIL MENANG!`);
                    } else if (aliveBots.length === 0) {
                        setGameOver(false, "💥 SERI! Kedua bot tereliminasi bersamaan!");
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
                let pulse = (timer < 30 && timer % 6 < 3) ? 2 : 0;
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
                    playerPixel.x = lerp(playerPixel.x, player.c * CELL, 0.25);
                    playerPixel.y = lerp(playerPixel.y, player.r * CELL, 0.25);
                    drawPlayer(playerPixel.x, playerPixel.y);
                }

                enemies.forEach((e, idx) => {
                    if (e.alive) {
                        enemyPixels[idx].x = lerp(enemyPixels[idx].x, e.c * CELL, 0.25);
                        enemyPixels[idx].y = lerp(enemyPixels[idx].y, e.r * CELL, 0.25);
                        drawEnemyBot(enemyPixels[idx].x, enemyPixels[idx].y, e.color);
                    }
                });
            }

            let frameCount = 0;
            function gameLoop() {
                frameCount++;
                tickMatch();
                updateBombsAndExplosions();
                render();

                if (frameCount % 12 === 0) {
                    moveEnemiesRealtime();
                }

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
                    player.r = nr;
                    player.c = nc;
                }

                if (e.code === 'Space') {
                    e.preventDefault();
                    placeBomb();
                }
            });

            document.getElementById('modeSelect').addEventListener('change', initGame);
            document.getElementById('algoSelectA').addEventListener('change', moveEnemiesRealtime);
            document.getElementById('algoSelectB').addEventListener('change', moveEnemiesRealtime);
            document.getElementById('restartBtn').addEventListener('click', initGame);

            initGame();
            gameLoop();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)