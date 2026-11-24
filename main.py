import heapq
import itertools
import random
import time
from collections import deque
from typing import Dict, List, Set, Tuple

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="BOMBERMAN Pathfinding")

DIRS4: List[Tuple[int, int]] = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# --------------------------------------------------------------------------
# 1. DATA MODELS
# --------------------------------------------------------------------------
class EnemyInfo(BaseModel):
    id: int
    pos: List[int]
    target: List[int]
    algorithm: str = "A_STAR"
    max_depth: int = 0
    history: List[List[int]] = []
    danger: List[List[int]] = []


class MultiPathRequest(BaseModel):
    grid: List[List[int]]
    enemies: List[EnemyInfo]


# --------------------------------------------------------------------------
# 2. PATHFINDING HELPERS & SEARCH ALGORITHMS
# --------------------------------------------------------------------------
def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def reconstruct_path(
    came_from: Dict[Tuple[int, int], Tuple[int, int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> List[List[int]]:
    path: List[List[int]] = []
    curr = goal
    while curr != start:
        path.append([curr[0], curr[1]])
        if curr not in came_from:
            break
        curr = came_from[curr]
    path.append([start[0], start[1]])
    path.reverse()
    return path


def get_neighbors(
    curr: Tuple[int, int],
    grid: List[List[int]],
    history_weights: Dict[Tuple[int, int], float],
    danger_cells: Set[Tuple[int, int]],
    order: List[Tuple[int, int]],
) -> List[Tuple[Tuple[int, int], float]]:
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    neighbors: List[Tuple[Tuple[int, int], float]] = []

    for dr, dc in order:
        nr, nc = curr[0] + dr, curr[1] + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            tile = grid[nr][nc]
            # 1 = dinding permanen, 3 = bom aktif, 4 = dinding sudden death
            if tile in (1, 3, 4):
                continue

            # 0 = lantai kosong (cost 1), 2 = blok kayu dapat dihancurkan (cost 4)
            step_cost = 4.0 if tile == 2 else 1.0
            nxt = (nr, nc)

            if nxt in danger_cells:
                step_cost += 14.0
            if nxt in history_weights:
                step_cost += history_weights[nxt]

            neighbors.append((nxt, step_cost))

    return neighbors


def run_search(
    algo: str,
    grid: List[List[int]],
    start: Tuple[int, int],
    target: Tuple[int, int],
    history: List[List[int]],
    danger: List[List[int]],
    max_depth_limit: int = 0,
) -> Tuple[List[List[int]], int, int, int]:
    algo = (algo or "A_STAR").upper()
    counter = itertools.count()

    order = list(DIRS4)
    random.shuffle(order)

    history_weights: Dict[Tuple[int, int], float] = {}
    for idx, pos in enumerate(history):
        if len(pos) >= 2:
            key = (pos[0], pos[1])
            history_weights[key] = history_weights.get(key, 0.0) + 0.65 + (idx * 0.05)

    danger_cells: Set[Tuple[int, int]] = {
        (pos[0], pos[1]) for pos in danger if len(pos) >= 2
    }

    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    depth_from: Dict[Tuple[int, int], int] = {start: 0}

    nodes_explored = 0
    max_depth = 0

    best_fallback: Tuple[int, int] | None = None
    best_fallback_score = (float("inf"), float("inf"))

    def update_fallback(
        node: Tuple[int, int], depth: int, cost: float, use_cost: bool
    ) -> None:
        nonlocal best_fallback, best_fallback_score
        if node == start:
            return
        h = float(manhattan_distance(node, target))
        secondary = cost if use_cost else float(depth)
        score = (h, secondary)
        if score < best_fallback_score:
            best_fallback_score = score
            best_fallback = node

    # 1. BFS: Unweighted breadth-first search dengan batas kedalaman
    if algo == "BFS":
        queue = deque([start])
        visited = {start}
        while queue:
            curr = queue.popleft()
            curr_depth = depth_from[curr]
            nodes_explored += 1
            max_depth = max(max_depth, curr_depth)
            update_fallback(curr, curr_depth, float(curr_depth), use_cost=False)
            if curr == target:
                path = reconstruct_path(came_from, start, target)
                return path, nodes_explored, max_depth, max(0, len(path) - 1)
            if max_depth_limit > 0 and curr_depth >= max_depth_limit:
                continue
            for nxt, _ in get_neighbors(
                curr, grid, history_weights, danger_cells, order
            ):
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    depth_from[nxt] = curr_depth + 1
                    queue.append(nxt)

    # 2. UCS: Uniform-Cost Search dengan batas kedalaman
    elif algo == "UCS":
        pq = [(0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float("inf")):
                continue
            curr_depth = depth_from[curr]
            nodes_explored += 1
            max_depth = max(max_depth, curr_depth)
            update_fallback(curr, curr_depth, curr_g, use_cost=True)
            if curr == target:
                path = reconstruct_path(came_from, start, target)
                return path, nodes_explored, max_depth, max(0, len(path) - 1)
            if max_depth_limit > 0 and curr_depth >= max_depth_limit:
                continue
            for nxt, cost in get_neighbors(
                curr, grid, history_weights, danger_cells, order
            ):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float("inf")):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    depth_from[nxt] = curr_depth + 1
                    heapq.heappush(pq, (new_g, next(counter), nxt))

    # 3. DIJKSTRA: Shortest-path tree terbatas pada kedalaman max_depth_limit
    elif algo == "DIJKSTRA":
        pq = [(0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float("inf")):
                continue
            curr_depth = depth_from[curr]
            nodes_explored += 1
            max_depth = max(max_depth, curr_depth)
            update_fallback(curr, curr_depth, curr_g, use_cost=True)
            if curr == target:
                path = reconstruct_path(came_from, start, target)
                return path, nodes_explored, max_depth, max(0, len(path) - 1)
            if max_depth_limit > 0 and curr_depth >= max_depth_limit:
                continue
            for nxt, cost in get_neighbors(
                curr, grid, history_weights, danger_cells, order
            ):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float("inf")):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    depth_from[nxt] = curr_depth + 1
                    heapq.heappush(pq, (new_g, next(counter), nxt))
        if target in came_from:
            path = reconstruct_path(came_from, start, target)
            return path, nodes_explored, max_depth, max(0, len(path) - 1)

    # 4. GBFS: Pure heuristic f(n) = h(n) dengan batas kedalaman
    elif algo == "GBFS":
        pq = [(float(manhattan_distance(start, target)), next(counter), start)]
        visited = {start}
        while pq:
            _, _, curr = heapq.heappop(pq)
            curr_depth = depth_from[curr]
            nodes_explored += 1
            max_depth = max(max_depth, curr_depth)
            update_fallback(curr, curr_depth, 0.0, use_cost=False)
            if curr == target:
                path = reconstruct_path(came_from, start, target)
                return path, nodes_explored, max_depth, max(0, len(path) - 1)
            if max_depth_limit > 0 and curr_depth >= max_depth_limit:
                continue
            for nxt, _ in get_neighbors(
                curr, grid, history_weights, danger_cells, order
            ):
                if nxt not in visited:
                    visited.add(nxt)
                    came_from[nxt] = curr
                    depth_from[nxt] = curr_depth + 1
                    priority = float(manhattan_distance(nxt, target))
                    heapq.heappush(pq, (priority, next(counter), nxt))

    # 5. A*: Optimal f(n) = g(n) + h(n) dengan batas kedalaman
    elif algo in ["A_STAR", "A*"]:
        pq = [(float(manhattan_distance(start, target)), 0.0, next(counter), start)]
        g_score = {start: 0.0}
        while pq:
            f, curr_g, _, curr = heapq.heappop(pq)
            if curr_g > g_score.get(curr, float("inf")):
                continue
            curr_depth = depth_from[curr]
            nodes_explored += 1
            max_depth = max(max_depth, curr_depth)
            update_fallback(curr, curr_depth, curr_g, use_cost=True)
            if curr == target:
                path = reconstruct_path(came_from, start, target)
                return path, nodes_explored, max_depth, max(0, len(path) - 1)
            if max_depth_limit > 0 and curr_depth >= max_depth_limit:
                continue
            for nxt, cost in get_neighbors(
                curr, grid, history_weights, danger_cells, order
            ):
                new_g = curr_g + cost
                if new_g < g_score.get(nxt, float("inf")):
                    g_score[nxt] = new_g
                    came_from[nxt] = curr
                    depth_from[nxt] = curr_depth + 1
                    new_f = new_g + float(manhattan_distance(nxt, target))
                    heapq.heappush(pq, (new_f, new_g, next(counter), nxt))

    if best_fallback is not None:
        path = reconstruct_path(came_from, start, best_fallback)
        return path, nodes_explored, max_depth, max(0, len(path) - 1)
    return [], nodes_explored, max_depth, 0


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
        path, nodes, max_depth, solution_depth = run_search(
            enemy_info.algorithm,
            req.grid,
            start_tuple,
            target_tuple,
            enemy_info.history,
            enemy_info.danger,
            enemy_info.max_depth,
        )
        exec_time = round((time.perf_counter() - t_start) * 1000, 3)

        next_move = (
            path[1] if len(path) > 1 else (path[0] if path else enemy_info.pos)
        )
        results.append(
            {
                "id": enemy_info.id,
                "enemy_pos": enemy_info.pos,
                "next_move": next_move,
                "full_path": path,
                "algorithm": enemy_info.algorithm,
                "max_depth_limit": enemy_info.max_depth,
                "nodes_explored": nodes,
                "max_depth": max_depth,
                "solution_depth": solution_depth,
                "exec_time_ms": exec_time,
            }
        )

    return {"status": "success", "results": results}


# --------------------------------------------------------------------------
# 4. FRONTEND
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def get_frontend():
    html_content = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
        <title>BOMBERMAN Pathfinding</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Chakra+Petch:ital,wght@0,600;0,700;1,700&family=IBM+Plex+Mono:wght@500;600&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
        <style>
            :root {
                --forest: #09251C;
                --forest-mid: #10382B;
                --forest-line: #1E5442;
                --amber: #A55704;
                --amber-hover: #BD6406;
                --sand: #F3D2AF;
                --cream: #F8EADC;

                --bot-a: #4FD1C5;
                --bot-b: #F6AD55;
                --danger: #EF6248;

                --font-display: 'Chakra Petch', sans-serif;
                --font-ui: 'Plus Jakarta Sans', sans-serif;
                --font-mono: 'IBM Plex Mono', monospace;

                --border-thick: 3px solid var(--forest);
            }

            * {
                box-sizing: border-box;
                -webkit-tap-highlight-color: transparent;
            }

            html, body {
                margin: 0;
                padding: 0;
                width: 100vw;
                height: 100dvh;
                overflow: hidden;
                background-color: var(--forest);
                color: var(--cream);
                font-family: var(--font-ui);
            }

            body::before {
                content: "";
                position: fixed;
                inset: 0;
                background-image:
                    linear-gradient(to right, rgba(248, 234, 220, 0.04) 1px, transparent 1px),
                    linear-gradient(to bottom, rgba(248, 234, 220, 0.04) 1px, transparent 1px);
                background-size: clamp(28px, 4vw, 48px) clamp(28px, 4vw, 48px);
                pointer-events: none;
                z-index: 0;
            }

            /* =========================================================
               3-SCREEN SETUP & MENU UI FLOW
            ========================================================= */
            #ui-flow {
                position: fixed;
                inset: 0;
                z-index: 20;
                user-select: none;
            }

            body.playing #ui-flow {
                display: none;
            }

            .screen {
                position: fixed;
                inset: 0;
                width: 100vw;
                height: 100dvh;
                padding: clamp(12px, 2.2vh, 26px) clamp(14px, 3vw, 40px);
                display: flex;
                flex-direction: column;
                opacity: 0;
                visibility: hidden;
                transform: translateY(14px) scale(0.99);
                transition: opacity 0.26s cubic-bezier(0.22, 1, 0.36, 1),
                            transform 0.26s cubic-bezier(0.22, 1, 0.36, 1),
                            visibility 0.26s;
            }

            .screen.active {
                opacity: 1;
                visibility: visible;
                transform: translateY(0) scale(1);
            }

            .screen-inner {
                width: 100%;
                max-width: 1160px;
                height: 100%;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: clamp(12px, 2.2vh, 24px);
            }

            .btn-arcade {
                font-family: var(--font-display);
                font-weight: 700;
                letter-spacing: 0.04em;
                border-radius: 999px;
                border: var(--border-thick);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                transition: transform 0.12s ease, box-shadow 0.12s ease, background-color 0.15s ease;
            }

            .btn-arcade:hover {
                transform: translateY(-2px);
            }

            .btn-arcade:active {
                transform: translateY(3px);
                box-shadow: 0 1px 0 var(--forest) !important;
            }

            .btn-primary {
                background-color: var(--amber);
                color: var(--cream);
                border-color: var(--cream);
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.55);
            }

            .btn-primary:hover {
                background-color: var(--amber-hover);
            }

            .btn-sand {
                background-color: var(--sand);
                color: var(--forest);
                border-color: var(--cream);
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.55);
            }

            .btn-sand:hover {
                background-color: var(--cream);
            }

            .pill-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: clamp(6px, 1vh, 10px) clamp(16px, 2.2vw, 28px);
                border-radius: 999px;
                font-family: var(--font-display);
                font-weight: 700;
                letter-spacing: 0.03em;
            }

            /* --- LAYAR 1: MAIN MENU --- */
            #screen-menu {
                justify-content: center;
                align-items: center;
                gap: clamp(24px, 4.5vh, 46px);
                text-align: center;
            }

            .title-block {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: clamp(4px, 0.8vh, 10px);
            }

            .main-title {
                margin: 0;
                font-family: var(--font-display);
                font-style: italic;
                font-weight: 700;
                font-size: clamp(2.6rem, 7.5vw, 5.6rem);
                line-height: 0.95;
                letter-spacing: 0.03em;
                color: var(--cream);
                text-shadow:
                    0 4px 0 var(--amber),
                    0 8px 0 rgba(0, 0, 0, 0.5);
            }

            .sub-title {
                margin: 0;
                font-family: var(--font-display);
                font-style: italic;
                font-weight: 700;
                font-size: clamp(1.3rem, 3.2vw, 2.35rem);
                color: var(--sand);
                letter-spacing: 0.06em;
                text-shadow: 0 3px 0 rgba(0, 0, 0, 0.45);
            }

            .menu-actions {
                display: flex;
                flex-direction: column;
                gap: clamp(14px, 2.5vh, 24px);
                width: min(380px, 86vw);
            }

            .menu-btn {
                width: 100%;
                padding: clamp(14px, 2.3vh, 22px) 24px;
                font-size: clamp(1.2rem, 2.6vw, 1.75rem);
            }

            /* --- LAYAR 2: PILIH MAP & SETTINGS --- */
            .setup-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: clamp(14px, 2.5vw, 32px);
                flex: 0 0 auto;
            }

            .setup-header-left {
                display: flex;
                flex-direction: column;
                gap: clamp(10px, 1.6vh, 18px);
                flex: 0 0 auto;
            }

            .section-heading {
                margin: 0;
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(1.85rem, 4vw, 3.2rem);
                line-height: 1;
                color: var(--cream);
                letter-spacing: 0.03em;
                text-shadow: 0 4px 0 rgba(0, 0, 0, 0.45);
            }

            .mode-indicator-row {
                display: flex;
                align-items: center;
                gap: clamp(10px, 1.5vw, 18px);
                flex-wrap: wrap;
            }

            .mode-label {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(1.1rem, 2.1vw, 1.65rem);
                color: var(--sand);
            }

            .mode-badge-active {
                background-color: var(--amber);
                color: var(--cream);
                border: 2px solid var(--cream);
                box-shadow: 0 4px 0 rgba(0, 0, 0, 0.45);
                font-size: clamp(0.92rem, 1.6vw, 1.25rem);
            }

            .map-picker-box {
                background-color: var(--sand);
                border: 3px solid var(--cream);
                border-radius: clamp(18px, 2.2vw, 26px);
                padding: clamp(10px, 1.5vh, 16px) clamp(14px, 2vw, 22px);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: clamp(12px, 1.8vw, 22px);
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.45);
            }

            .map-card {
                background-color: var(--cream);
                border: var(--border-thick);
                border-radius: clamp(14px, 1.6vw, 20px);
                padding: clamp(8px, 1.1vh, 12px);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: clamp(6px, 0.8vh, 9px);
                cursor: pointer;
                transition: transform 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
            }

            .map-card:hover {
                transform: translateY(-2px);
            }

            .map-card.selected {
                background-color: var(--amber);
                color: var(--cream);
                box-shadow: 0 4px 0 var(--forest);
                transform: translateY(-2px);
            }

            .map-preview-canvas {
                width: clamp(104px, 17.5vh, 152px);
                height: auto;
                aspect-ratio: 15 / 13;
                background-color: var(--forest);
                border-radius: 10px;
                border: 2px solid var(--forest);
                display: block;
            }

            .map-card-title {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.88rem, 1.45vw, 1.14rem);
                color: var(--forest);
            }

            .map-card.selected .map-card-title {
                color: var(--cream);
            }

            /* Bottom Settings Panel */
            .setup-bottom-panel {
                flex: 0 1 auto;
                height: clamp(275px, 50vh, 390px);
                background-color: var(--sand);
                border: 3px solid var(--cream);
                border-radius: clamp(18px, 2.4vw, 28px);
                padding: clamp(12px, 2vh, 22px) clamp(14px, 2.2vw, 26px);
                display: grid;
                grid-template-columns: 1.25fr 1.15fr 0.48fr;
                gap: clamp(12px, 2vw, 24px);
                box-shadow: 0 8px 0 rgba(0, 0, 0, 0.5);
            }

            .settings-left {
                display: flex;
                flex-direction: column;
                gap: clamp(8px, 1.2vh, 12px);
                min-height: 0;
            }

            .settings-pill-title {
                align-self: flex-start;
                background-color: var(--forest);
                color: var(--cream);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.95rem, 1.65vw, 1.35rem);
                padding: clamp(5px, 0.9vh, 9px) clamp(16px, 2.2vw, 26px);
                border-radius: 999px;
            }

            .character-box {
                flex: 1 1 auto;
                min-height: 0;
                background-color: var(--cream);
                border: var(--border-thick);
                border-radius: clamp(14px, 1.8vw, 20px);
                padding: clamp(10px, 1.5vh, 16px);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: clamp(8px, 1.2vh, 14px);
            }

            .char-header-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                flex-wrap: wrap;
            }

            .char-static-tag {
                background-color: var(--forest);
                color: var(--cream);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.8rem, 1.3vw, 1rem);
                padding: 5px 14px;
                border-radius: 999px;
            }

            .entity-tabs {
                display: inline-flex;
                background-color: var(--forest);
                padding: 3px;
                border-radius: 999px;
                gap: 4px;
            }

            .entity-tab {
                border: none;
                background: transparent;
                color: var(--sand);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.78rem, 1.25vw, 0.96rem);
                padding: 4px 13px;
                border-radius: 999px;
                cursor: pointer;
                transition: background-color 0.15s ease, color 0.15s ease;
            }

            .entity-tab.active {
                background-color: var(--amber);
                color: var(--cream);
            }

            .char-cards-grid {
                flex: 1 1 auto;
                min-height: 0;
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: clamp(8px, 1.1vw, 14px);
            }

            .char-card {
                background-color: var(--sand);
                border: var(--border-thick);
                border-radius: clamp(12px, 1.4vw, 16px);
                padding: clamp(8px, 1.1vh, 12px) 6px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: clamp(6px, 0.9vh, 10px);
                cursor: pointer;
                transition: transform 0.14s ease, background-color 0.14s ease, box-shadow 0.14s ease;
                min-height: 0;
            }

            .char-card:hover {
                transform: translateY(-2px);
            }

            .char-card.selected {
                background-color: var(--amber);
                color: var(--cream);
                box-shadow: 0 4px 0 var(--forest);
                transform: translateY(-2px);
            }

            .char-avatar {
                width: clamp(52px, 9vh, 82px);
                height: clamp(52px, 9vh, 82px);
                flex-shrink: 0;
            }

            .char-name {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.82rem, 1.25vw, 1.05rem);
                color: var(--forest);
                text-align: center;
                line-height: 1.1;
            }

            .char-card.selected .char-name {
                color: var(--cream);
            }

            /* Center Column: Algorithm & Depth */
            .settings-center {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: clamp(10px, 1.5vh, 16px);
                min-height: 0;
            }

            .control-group-card {
                flex: 1 1 auto;
                background-color: var(--forest);
                border: var(--border-thick);
                border-radius: clamp(14px, 1.8vw, 20px);
                padding: clamp(10px, 1.4vh, 16px) clamp(12px, 1.6vw, 20px);
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: clamp(6px, 1vh, 10px);
                min-height: 0;
            }

            .control-label-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                flex-wrap: wrap;
            }

            .control-pill-label {
                align-self: flex-start;
                background-color: var(--amber);
                color: var(--cream);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.82rem, 1.3vw, 1.04rem);
                padding: 4px 15px;
                border-radius: 999px;
            }

            .depth-hint-pill {
                display: inline-flex;
                align-items: center;
                background-color: var(--forest-mid);
                border: 1.5px solid var(--sand);
                color: var(--sand);
                font-family: var(--font-mono);
                font-size: clamp(0.68rem, 1vw, 0.82rem);
                font-weight: 600;
                padding: 3px 10px;
                border-radius: 999px;
            }

            .dual-algo-wrapper {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: clamp(8px, 1.2vw, 14px);
            }

            .sub-select-block {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .sub-select-block .control-pill-label {
                font-size: clamp(0.74rem, 1.1vw, 0.92rem);
                padding: 4px 11px;
            }

            .select-wrap {
                position: relative;
                width: 100%;
            }

            .arcade-select {
                width: 100%;
                appearance: none;
                -webkit-appearance: none;
                background-color: var(--cream);
                color: var(--forest);
                border: 2px solid var(--sand);
                border-radius: 999px;
                padding: clamp(7px, 1.2vh, 11px) 36px clamp(7px, 1.2vh, 11px) 15px;
                font-family: var(--font-ui);
                font-weight: 800;
                font-size: clamp(0.8rem, 1.25vw, 0.98rem);
                cursor: pointer;
                outline: none;
                transition: border-color 0.15s ease, background-color 0.15s ease;
            }

            .arcade-select:focus,
            .arcade-select:hover {
                background-color: var(--sand);
                border-color: var(--amber);
            }

            .select-wrap::after {
                content: "";
                position: absolute;
                right: 14px;
                top: 50%;
                transform: translateY(-35%);
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid var(--amber);
                pointer-events: none;
            }

            .settings-right {
                display: flex;
                flex-direction: column;
                justify-content: space-evenly;
                align-items: stretch;
                gap: clamp(10px, 1.6vh, 18px);
            }

            .nav-side-btn {
                width: 100%;
                padding: clamp(11px, 1.8vh, 18px) 10px;
                font-size: clamp(0.98rem, 1.6vw, 1.3rem);
                border-radius: 18px;
            }

            /* --- LAYAR 3: PILIHAN KAMU --- */
            .confirm-top-bar {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                flex: 0 0 auto;
            }

            .confirm-header-pill {
                background-color: var(--sand);
                color: var(--forest);
                border: 3px solid var(--cream);
                box-shadow: 0 5px 0 rgba(0, 0, 0, 0.45);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(1.25rem, 2.8vw, 2.15rem);
                padding: clamp(7px, 1.2vh, 13px) clamp(22px, 3.2vw, 40px);
                border-radius: 999px;
                letter-spacing: 0.04em;
            }

            .confirm-grid {
                flex: 0 1 auto;
                display: grid;
                grid-template-columns: 0.9fr 1.2fr;
                gap: clamp(14px, 2.4vw, 30px);
                align-items: stretch;
            }

            .confirm-left {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: clamp(12px, 1.8vh, 18px);
            }

            .confirm-mode-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                background-color: rgba(243, 210, 175, 0.08);
                border: 2px solid rgba(248, 234, 220, 0.25);
                border-radius: 20px;
                padding: clamp(10px, 1.5vh, 16px) clamp(14px, 2vw, 22px);
            }

            .confirm-map-row {
                flex: 1 1 auto;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: clamp(12px, 2vw, 20px);
                background-color: rgba(243, 210, 175, 0.08);
                border: 2px solid rgba(248, 234, 220, 0.25);
                border-radius: 22px;
                padding: clamp(12px, 1.8vh, 20px) clamp(14px, 2vw, 22px);
            }

            .confirm-label {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(1.1rem, 2.1vw, 1.65rem);
                color: var(--cream);
            }

            .selected-map-showcase {
                background-color: var(--amber);
                border: 3px solid var(--cream);
                border-radius: 20px;
                padding: clamp(10px, 1.4vh, 14px);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 8px;
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.45);
            }

            .selected-map-showcase .map-preview-canvas {
                width: clamp(124px, 20vh, 178px);
            }

            .selected-map-showcase span {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.95rem, 1.5vw, 1.22rem);
                color: var(--cream);
            }

            .confirm-right {
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: clamp(12px, 1.8vh, 18px);
            }

            .confirm-chars-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: clamp(12px, 2vw, 22px);
            }

            .confirm-char-card {
                background-color: var(--cream);
                border: 3px solid var(--sand);
                border-radius: 20px;
                padding: clamp(8px, 1.2vh, 12px);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.45);
            }

            .confirm-char-role {
                width: 100%;
                text-align: center;
                background-color: var(--forest);
                color: var(--cream);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.88rem, 1.45vw, 1.15rem);
                padding: 5px 12px;
                border-radius: 999px;
            }

            .confirm-char-art-box {
                width: 100%;
                height: clamp(118px, 19.5vh, 168px);
                background-color: var(--sand);
                border: var(--border-thick);
                border-radius: 15px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: 8px;
                gap: 6px;
            }

            .confirm-char-art-box svg {
                width: clamp(62px, 11vh, 96px);
                height: clamp(62px, 11vh, 96px);
            }

            .confirm-char-art-box strong {
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.92rem, 1.35vw, 1.12rem);
                color: var(--forest);
            }

            .params-summary-panel {
                background-color: var(--sand);
                border: 3px solid var(--cream);
                border-radius: 20px;
                padding: clamp(10px, 1.4vh, 15px) clamp(14px, 2vw, 22px);
                display: flex;
                flex-direction: column;
                gap: clamp(7px, 1vh, 10px);
                box-shadow: 0 6px 0 rgba(0, 0, 0, 0.45);
            }

            .param-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: clamp(10px, 1.8vw, 20px);
                align-items: center;
            }

            .param-key {
                background-color: var(--forest);
                color: var(--cream);
                font-family: var(--font-display);
                font-weight: 700;
                font-size: clamp(0.82rem, 1.3vw, 1.04rem);
                padding: clamp(5px, 0.9vh, 8px) 14px;
                border-radius: 999px;
                text-align: center;
            }

            .param-val {
                background-color: var(--amber);
                color: var(--cream);
                border: 2px solid var(--forest);
                font-family: var(--font-ui);
                font-weight: 800;
                font-size: clamp(0.82rem, 1.3vw, 1.04rem);
                padding: clamp(5px, 0.9vh, 8px) 14px;
                border-radius: 999px;
                text-align: center;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .confirm-actions {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: clamp(16px, 4vw, 56px);
                flex: 0 0 auto;
            }

            .confirm-btn {
                width: min(250px, 42vw);
                padding: clamp(11px, 1.8vh, 17px) 20px;
                font-size: clamp(1.05rem, 2vw, 1.45rem);
            }

            /* =========================================================
               ARENA SCREEN (GAMEPLAY VIEW)
            ========================================================= */
            #arena-wrapper {
                display: none;
                position: relative;
                z-index: 1;
                width: 100vw;
                height: 100dvh;
                padding: clamp(10px, 1.8vh, 18px) clamp(14px, 2.2vw, 26px);
                flex-direction: column;
                gap: 10px;
            }

            body.playing #arena-wrapper {
                display: flex;
            }

            .page-head {
                width: 100%;
                max-width: 1480px;
                margin: 0 auto;
                display: flex;
                align-items: center;
                gap: 14px;
                flex: 0 0 auto;
            }

            .page-head h1 {
                margin: 0;
                font-family: var(--font-display);
                font-style: italic;
                font-size: clamp(1.25rem, 2.2vw, 1.75rem);
                font-weight: 700;
                color: var(--cream);
                text-shadow: 0 2px 0 var(--amber);
            }

            #container {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                align-items: stretch;
                justify-content: center;
                gap: 16px;
                width: 100%;
                max-width: 1480px;
                margin: 0 auto;
            }

            #gameCanvas {
                display: block;
                width: auto;
                height: 100%;
                max-width: calc(100vw - 440px);
                aspect-ratio: 15 / 13;
                border: 3px solid var(--cream);
                border-radius: 18px;
                background: var(--forest-mid);
                box-shadow: 0 8px 0 rgba(0, 0, 0, 0.5);
            }

            #panel {
                background: var(--sand);
                color: var(--forest);
                padding: 12px 14px;
                width: 396px;
                flex: 0 0 396px;
                height: 100%;
                overflow-y: auto;
                text-align: left;
                border: 3px solid var(--cream);
                border-radius: 20px;
                box-shadow: 0 8px 0 rgba(0, 0, 0, 0.5);
                display: flex;
                flex-direction: column;
                gap: 7px;
            }

            .mode-header {
                margin: 0 0 4px;
                padding-bottom: 6px;
                border-bottom: 2px solid var(--forest);
                font-family: var(--font-display);
                font-size: 16px;
                font-weight: 700;
                color: var(--forest);
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                min-height: 28px;
            }

            #statusMsg {
                font-family: var(--font-display);
                font-size: 12.5px;
                font-weight: 700;
                padding: 3px 10px;
                border-radius: 999px;
                background: var(--forest);
                color: var(--bot-a);
                border: 1.5px solid var(--forest);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            #statusMsg:empty {
                display: none;
            }

            .section-title {
                margin: 0 0 4px;
                padding-bottom: 6px;
                border-bottom: 2px solid var(--forest);
                font-family: var(--font-display);
                font-size: 16px;
                font-weight: 700;
                color: var(--forest);
            }

            /* Read-only setup summary in Arena Panel */
            .active-config-box {
                background: var(--cream);
                border: 2px solid var(--forest);
                border-radius: 14px;
                padding: 8px 10px;
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .config-grid-2 {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 5px 8px;
            }

            .config-chip {
                background: rgba(9, 37, 28, 0.06);
                border-radius: 8px;
                padding: 5px 8px;
                font-size: 11.5px;
            }

            .config-chip small {
                display: block;
                font-size: 10px;
                font-weight: 700;
                color: rgba(9, 37, 28, 0.65);
                text-transform: uppercase;
            }

            .config-chip b {
                font-family: var(--font-display);
                font-size: 12.5px;
                color: var(--forest);
            }

            .mini-char-row {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-top: 2px;
            }

            .mini-char-icon {
                width: 24px;
                height: 24px;
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }

            .mini-char-icon svg {
                width: 100%;
                height: 100%;
            }

            .table-head-flex {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                vertical-align: middle;
            }

            .table-head-flex svg {
                width: 18px;
                height: 18px;
                flex-shrink: 0;
            }

            .config-hint {
                font-size: 11px;
                color: rgba(9, 37, 28, 0.75);
                font-weight: 600;
                text-align: center;
                padding-top: 3px;
                border-top: 1px dashed rgba(9, 37, 28, 0.25);
            }

            #panel button {
                display: block;
                width: 100%;
                min-height: 34px;
                padding: 6px 10px;
                border: 2px solid var(--forest);
                border-radius: 999px;
                background: var(--cream);
                color: var(--forest);
                font: 700 13.5px var(--font-display);
                cursor: pointer;
                transition: transform 0.1s ease, background-color 0.12s ease;
            }

            #panel button:hover {
                background: #ffffff;
            }

            #restartBtn {
                background: var(--amber) !important;
                color: var(--cream) !important;
                border-color: var(--forest) !important;
                font-weight: 700;
            }

            #restartBtn:hover {
                background: var(--amber-hover) !important;
            }

            #settingsBackBtn {
                background: var(--forest) !important;
                color: var(--cream) !important;
            }

            #settingsBackBtn:hover {
                background: var(--forest-mid) !important;
            }

            .button-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 8px;
            }

            .stat {
                padding: 6px 10px;
                background: var(--cream);
                border: 2px solid var(--forest);
                border-radius: 12px;
                font-size: 13px;
                color: var(--forest);
            }

            .status-strip {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 6px;
            }

            .status-strip span { min-width: 0; }
            .status-strip small { display: block; color: rgba(9, 37, 28, 0.72); font: 700 11px var(--font-ui); }
            .status-strip b { font: 600 12.5px var(--font-mono); font-variant-numeric: tabular-nums; color: var(--forest); }
            .status-strip .status-phase {
                grid-column: 1 / -1;
                padding-bottom: 4px;
                border-bottom: 1.5px solid rgba(9, 37, 28, 0.25);
                color: var(--amber);
                font-family: var(--font-display);
                font-weight: 700;
            }

            .stat-box {
                padding: 8px 10px;
                background: var(--cream);
                border: 2px solid var(--forest);
                border-radius: 14px;
                font-size: 13px;
            }

            .metric-value, .stats-table td {
                font-family: var(--font-mono);
                font-variant-numeric: tabular-nums;
            }

            .analysis-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 6px;
                margin: 0 0 4px;
                font-size: 12px;
            }

            #winSummary {
                font-weight: 700;
                color: var(--amber);
                white-space: nowrap;
            }

            .rules-note {
                margin: 4px 0;
                color: rgba(9, 37, 28, 0.75);
                font-size: 11.5px;
                line-height: 1.3;
            }

            .stats-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 4px;
                font-size: 12px;
            }

            .stats-table th, .stats-table td {
                padding: 4px 3px;
                border-bottom: 1px solid rgba(9, 37, 28, 0.2);
                text-align: left;
            }

            .stats-table th {
                font-family: var(--font-display);
                font-size: 13px;
                font-weight: 700;
            }

            .stats-table td:first-child {
                color: rgba(9, 37, 28, 0.8);
                font-family: var(--font-ui);
                font-weight: 600;
            }

            .bot-a-head { border-left: 3px solid #0d9488; padding-left: 6px !important; }
            .bot-b-head { border-left: 3px solid var(--amber); padding-left: 6px !important; }

            .reload-bar-bg {
                height: 8px;
                margin-top: 4px;
                overflow: hidden;
                background: var(--forest);
                border-radius: 999px;
            }

            .reload-bar-fill {
                width: 100%;
                height: 100%;
                background: var(--amber);
                transition: width .1s linear;
            }

            @media (max-width: 860px) {
                .setup-top {
                    flex-direction: column;
                    align-items: stretch;
                    gap: 8px;
                }

                .setup-header-left {
                    flex-direction: row;
                    align-items: center;
                    justify-content: space-between;
                }

                .map-preview-canvas {
                    width: clamp(74px, 12vh, 102px);
                }

                .setup-bottom-panel {
                    height: auto;
                    flex: 1 1 auto;
                    grid-template-columns: 1fr;
                    grid-template-rows: 1.1fr auto auto;
                    gap: 10px;
                    padding: 12px;
                }

                .settings-pill-title {
                    display: none;
                }

                .settings-center {
                    flex-direction: row;
                    gap: 10px;
                }

                .settings-right {
                    flex-direction: row;
                    gap: 12px;
                }

                .nav-side-btn {
                    padding: 10px 14px;
                    border-radius: 999px;
                }

                .confirm-grid {
                    grid-template-columns: 1fr;
                    gap: 10px;
                }

                .confirm-left {
                    flex-direction: row;
                    gap: 10px;
                }

                .confirm-mode-row {
                    flex-direction: column;
                    justify-content: center;
                    flex: 0.7;
                }

                .confirm-map-row {
                    flex: 1.3;
                    padding: 8px 12px;
                }

                .selected-map-showcase .map-preview-canvas {
                    width: clamp(78px, 12vh, 108px);
                }

                .confirm-char-art-box {
                    height: clamp(86px, 14vh, 120px);
                }

                .confirm-char-art-box svg {
                    width: clamp(44px, 8vh, 66px);
                    height: clamp(44px, 8vh, 66px);
                }
            }

            @media (max-width: 520px) {
                .settings-center {
                    flex-direction: column;
                    gap: 8px;
                }

                .control-group-card {
                    padding: 8px 12px;
                    gap: 6px;
                }

                .arcade-select {
                    padding: 6px 32px 6px 12px;
                    font-size: 0.8rem;
                }

                .char-avatar {
                    width: 40px;
                    height: 40px;
                }
            }
        </style>
    </head>
    <body>
        <!-- =========================================================
             3-SCREEN UI FLOW (MENU -> PILIH MAP & SETTINGS -> PILIHAN KAMU)
        ========================================================= -->
        <div id="ui-flow">
            <!-- LAYAR 1: MAIN MENU -->
            <main id="screen-menu" class="screen active" aria-label="Menu Utama">
                <div class="title-block">
                    <h1 class="main-title">BOMBERMAN</h1>
                    <p class="sub-title">Pathfinding</p>
                </div>

                <div class="menu-actions">
                    <button type="button" class="btn-arcade btn-primary menu-btn" onclick="selectUIMode('PvB')">
                        Player Vs Bot
                    </button>
                    <button type="button" class="btn-arcade btn-sand menu-btn" onclick="selectUIMode('BvB')">
                        Bot Vs Bot
                    </button>
                </div>
            </main>

            <!-- LAYAR 2: PILIH MAP & SETTINGS -->
            <section id="screen-setup" class="screen" aria-label="Pilih Map dan Pengaturan">
                <div class="screen-inner">
                    <header class="setup-top">
                        <div class="setup-header-left">
                            <h2 class="section-heading">PILIH MAP</h2>
                            <div class="mode-indicator-row">
                                <span class="mode-label">Mode</span>
                                <span id="setup-mode-badge" class="pill-badge mode-badge-active">Player Vs Bot</span>
                            </div>
                        </div>

                        <div class="map-picker-box" id="ui-map-picker">
                            <div class="map-card selected" data-map="classic" onclick="chooseUIMap('classic')">
                                <canvas class="map-preview-canvas" width="150" height="130"></canvas>
                                <span class="map-card-title">Klasik</span>
                            </div>
                            <div class="map-card" data-map="corridor" onclick="chooseUIMap('corridor')">
                                <canvas class="map-preview-canvas" width="150" height="130"></canvas>
                                <span class="map-card-title">Koridor</span>
                            </div>
                            <div class="map-card" data-map="open" onclick="chooseUIMap('open')">
                                <canvas class="map-preview-canvas" width="150" height="130"></canvas>
                                <span class="map-card-title">Terbuka</span>
                            </div>
                        </div>
                    </header>

                    <div class="setup-bottom-panel">
                        <!-- Panel Kiri: Karakter (Desain Visual Tanpa Buff) -->
                        <div class="settings-left">
                            <div class="settings-pill-title">Settings</div>
                            <div class="character-box">
                                <div class="char-header-row">
                                    <span class="char-static-tag">Karakter</span>
                                    <div class="entity-tabs" id="entity-tabs"></div>
                                </div>
                                <div class="char-cards-grid" id="char-cards-grid"></div>
                            </div>
                        </div>

                        <!-- Panel Tengah: Algoritma & Depth -->
                        <div class="settings-center">
                            <div id="algo-single-card" class="control-group-card">
                                <label for="ui-algo-single" class="control-pill-label">Pilih Algoritma Bot</label>
                                <div class="select-wrap">
                                    <select id="ui-algo-single" class="arcade-select" onchange="syncSetupState()">
                                        <option value="A_STAR" selected>A* Search Algorithm</option>
                                        <option value="DIJKSTRA">Dijkstra Algorithm</option>
                                        <option value="UCS">Uniform Cost (UCS)</option>
                                        <option value="GBFS">Greedy Best-First (GBFS)</option>
                                        <option value="BFS">Breadth-First (BFS)</option>
                                    </select>
                                </div>
                            </div>

                            <div id="algo-dual-card" class="control-group-card" style="display: none;">
                                <div class="dual-algo-wrapper">
                                    <div class="sub-select-block">
                                        <label for="ui-algo-bot1" class="control-pill-label">Algoritma Bot 1</label>
                                        <div class="select-wrap">
                                            <select id="ui-algo-bot1" class="arcade-select" onchange="syncSetupState()">
                                                <option value="A_STAR" selected>A* Search Algorithm</option>
                                                <option value="DIJKSTRA">Dijkstra Algorithm</option>
                                                <option value="UCS">Uniform Cost (UCS)</option>
                                                <option value="GBFS">Greedy Best-First (GBFS)</option>
                                                <option value="BFS">Breadth-First (BFS)</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="sub-select-block">
                                        <label for="ui-algo-bot2" class="control-pill-label">Algoritma Bot 2</label>
                                        <div class="select-wrap">
                                            <select id="ui-algo-bot2" class="arcade-select" onchange="syncSetupState()">
                                                <option value="A_STAR">A* Search Algorithm</option>
                                                <option value="DIJKSTRA" selected>Dijkstra Algorithm</option>
                                                <option value="UCS">Uniform Cost (UCS)</option>
                                                <option value="GBFS">Greedy Best-First (GBFS)</option>
                                                <option value="BFS">Breadth-First (BFS)</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="control-group-card">
                                <div class="control-label-row">
                                    <label for="ui-depth-select" class="control-pill-label">Depth</label>
                                    <span class="depth-hint-pill">Kedalaman Pencarian AI</span>
                                </div>
                                <div class="select-wrap">
                                    <select id="ui-depth-select" class="arcade-select" onchange="syncSetupState()">
                                        <option value="2">Depth 2 (Sangat Dangkal)</option>
                                        <option value="4">Depth 4 (Dangkal)</option>
                                        <option value="6">Depth 6 (Terbatas)</option>
                                        <option value="8">Depth 8 (Menengah)</option>
                                        <option value="12" selected>Depth 12 (Sedang)</option>
                                        <option value="16">Depth 16 (Jauh)</option>
                                        <option value="20">Depth 20 (Sangat Jauh)</option>
                                        <option value="0">Tak Terbatas (Penuh)</option>
                                    </select>
                                </div>
                            </div>
                        </div>

                        <!-- Panel Kanan: Navigasi -->
                        <div class="settings-right">
                            <button type="button" class="btn-arcade btn-sand nav-side-btn" onclick="goToUIScreen('screen-menu')">
                                Menu
                            </button>
                            <button type="button" class="btn-arcade btn-primary nav-side-btn" onclick="goToConfirmScreen()">
                                Mulai
                            </button>
                        </div>
                    </div>
                </div>
            </section>

            <!-- LAYAR 3: PILIHAN KAMU -->
            <section id="screen-confirm" class="screen" aria-label="Konfirmasi Pilihan">
                <div class="screen-inner">
                    <div class="confirm-top-bar">
                        <div class="confirm-header-pill">PILIHAN KAMU</div>
                    </div>

                    <div class="confirm-grid">
                        <div class="confirm-left">
                            <div class="confirm-mode-row">
                                <span class="confirm-label">Mode</span>
                                <span id="confirm-mode-badge" class="pill-badge mode-badge-active">Player Vs Bot</span>
                            </div>

                            <div class="confirm-map-row">
                                <span class="confirm-label">Pilihan Map</span>
                                <div id="confirm-map-showcase" class="selected-map-showcase">
                                    <canvas id="confirm-map-canvas" class="map-preview-canvas" width="150" height="130"></canvas>
                                    <span id="confirm-map-name">Klasik</span>
                                </div>
                            </div>
                        </div>

                        <div class="confirm-right">
                            <div class="confirm-chars-row" id="confirm-chars-row"></div>
                            <div class="params-summary-panel" id="confirm-params-panel"></div>
                        </div>
                    </div>

                    <div class="confirm-actions">
                        <button type="button" class="btn-arcade btn-sand confirm-btn" onclick="goToUIScreen('screen-setup')">
                            BALIK
                        </button>
                        <button type="button" id="omkeGasBtn" class="btn-arcade btn-primary confirm-btn">
                            OMKE GAS
                        </button>
                    </div>
                </div>
            </section>
        </div>

        <!-- =========================================================
             ARENA GAMEPLAY VIEW
        ========================================================= -->
        <div id="arena-wrapper">
            <header class="page-head">
                <h1>BOMBERMAN Pathfinding</h1>
            </header>

            <div id="container">
                <canvas id="gameCanvas" width="600" height="520"></canvas>

                <div id="panel">
                    <div class="mode-header">
                        <span>Kontrol simulasi</span>
                        <span id="statusMsg"></span>
                    </div>

                    <!-- Ringkasan Pengaturan dari Halaman Settings (Read-Only) -->
                    <div class="active-config-box">
                        <div class="config-grid-2">
                            <div class="config-chip">
                                <small>Mode</small>
                                <b id="summaryMode">Player vs Bot</b>
                            </div>
                            <div class="config-chip">
                                <small>Depth Pencarian</small>
                                <b id="summaryDepth">Depth 12</b>
                            </div>
                            <div class="config-chip" id="summaryEntity1Wrap">
                                <small id="summaryEntity1Role">Player · IGNIS</small>
                                <div class="mini-char-row">
                                    <span class="mini-char-icon" id="summaryEntity1Icon"></span>
                                    <b id="summaryEntity1Sub">WASD / Panah + Spasi</b>
                                </div>
                            </div>
                            <div class="config-chip" id="summaryEntity2Wrap">
                                <small id="summaryEntity2Role">Bot · VECTRA</small>
                                <div class="mini-char-row">
                                    <span class="mini-char-icon" id="summaryEntity2Icon"></span>
                                    <b id="summaryEntity2Sub">A* Search Algorithm</b>
                                </div>
                            </div>
                        </div>
                        <div class="config-hint">Karakter, bot, peta &amp; depth diatur di halaman Settings</div>
                    </div>

                    <button id="restartBtn" type="button">Ulang ronde</button>
                    <div class="button-row">
                        <button id="pauseBtn" type="button">Jeda</button>
                        <button id="stepBtn" type="button">Step satu tick</button>
                    </div>
                    <div class="button-row">
                        <button id="settingsBackBtn" type="button">Ubah di Settings</button>
                        <button id="menuBtn" type="button">Menu Utama</button>
                    </div>

                    <div class="stat">Tick <b id="tickValue" class="metric-value">0</b> · Peta <b id="mapNameGame">Klasik</b></div>

                    <div id="playerStats" style="display: none;">
                        <div class="stat">
                            <div class="mini-char-row" style="margin-top:0;">
                                <span class="mini-char-icon" id="playerHudIcon"></span>
                                <span><span id="playerHealthLabel">Nyawa pemain</span>: <b id="healthVal">3</b></span>
                            </div>
                        </div>
                        <div class="stat">
                            Amunisi magazin: <span id="ammoVal">1</span>
                            <div class="reload-bar-bg"><div id="reloadFill" class="reload-bar-fill"></div></div>
                        </div>
                    </div>

                    <div class="stat status-strip" id="phaseInfo"></div>

                    <section class="stat-box">
                        <h2 class="section-title">Analisis pencarian</h2>
                        <div class="analysis-meta">
                            <span>Peta: <b id="mapNameAnalysis">Klasik</b></span>
                            <span id="winSummary" class="metric-value">B1: 0 | B2: 0 | Seri: 0</span>
                        </div>
                        <p class="rules-note">Jangkauan ledakan tetap kotak 3x3 (9 ubin). Max depth: ekspansi terdalam; solution depth: panjang langkah solusi.</p>
                        <table class="stats-table">
                            <thead>
                                <tr>
                                    <th></th>
                                    <th class="bot-a-head" id="bot1StatsBox">Bot 1</th>
                                    <th id="bot2StatsBox" class="bot-b-head bot-b-column">Bot 2</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr><td>Algoritma</td><td id="algoNameA">A*</td><td class="bot-b-column" id="algoNameB">Dijkstra</td></tr>
                                <tr><td>Batas Depth</td><td id="limitDepthA">12</td><td class="bot-b-column" id="limitDepthB">12</td></tr>
                                <tr><td>Wins</td><td id="winsA">0</td><td class="bot-b-column" id="winsB">0</td></tr>
                                <tr><td>Dikunjungi (rata-rata)</td><td><span id="nodesA">0</span> (<span id="avgNodesA">0</span>)</td><td class="bot-b-column"><span id="nodesB">0</span> (<span id="avgNodesB">0</span>)</td></tr>
                                <tr><td>Depth maks. (rata-rata)</td><td><span id="depthA">0</span> (<span id="avgDepthA">0</span>)</td><td class="bot-b-column"><span id="depthB">0</span> (<span id="avgDepthB">0</span>)</td></tr>
                                <tr><td>Depth solusi (rata-rata)</td><td><span id="solutionA">0</span> (<span id="avgSolutionA">0</span>)</td><td class="bot-b-column"><span id="solutionB">0</span> (<span id="avgSolutionB">0</span>)</td></tr>
                                <tr><td>Waktu (rata-rata)</td><td><span id="timeA">0 ms</span> (<span id="avgTimeA">0 ms</span>)</td><td class="bot-b-column"><span id="timeB">0 ms</span> (<span id="avgTimeB">0 ms</span>)</td></tr>
                                <tr><td>Status</td><td id="stateA">HUNT</td><td class="bot-b-column" id="stateB">HUNT</td></tr>
                            </tbody>
                        </table>
                    </section>
                </div>
            </div>
        </div>

        <script>
            const canvas = document.getElementById('gameCanvas');
            const ctx = canvas.getContext('2d');
            const CELL = 40;
            const ROWS = 13, COLS = 15;
            const DIRS4 = [[-1,0], [1,0], [0,-1], [0,1]];
            const COLORS = {
                botA: '#4FD1C5', botB: '#F6AD55', player: '#F8EADC', ink: '#09251C', line: '#F3D2AF', grid: '#174234',
                floor: '#0C2F24', wall: '#1A4D3D', brick: '#A55704', collapse: '#5C1916',
                danger: '#EF6248', pathA: 'rgba(79,209,197,0.24)', pathB: 'rgba(246,173,85,0.24)'
            };

            // Karakter murni variasi desain visual (tanpa buff / perubahan stat)
            const CHARACTERS = [
                {
                    id: 0,
                    name: "IGNIS",
                    svg: `
                        <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <line x1="40" y1="6" x2="40" y2="18" stroke="#09251C" stroke-width="5" stroke-linecap="round"/>
                            <circle cx="40" cy="7" r="5" fill="#A55704" stroke="#09251C" stroke-width="3"/>
                            <rect x="16" y="18" width="48" height="42" rx="20" fill="#F8EADC" stroke="#09251C" stroke-width="4"/>
                            <rect x="23" y="28" width="34" height="18" rx="9" fill="#09251C"/>
                            <circle cx="32" cy="37" r="4" fill="#F3D2AF"/>
                            <circle cx="48" cy="37" r="4" fill="#F3D2AF"/>
                            <rect x="26" y="60" width="28" height="12" rx="6" fill="#A55704" stroke="#09251C" stroke-width="3.5"/>
                        </svg>
                    `
                },
                {
                    id: 1,
                    name: "VECTRA",
                    svg: `
                        <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M22 22L14 10L28 17" fill="#A55704" stroke="#09251C" stroke-width="3.5" stroke-linejoin="round"/>
                            <path d="M58 22L66 10L52 17" fill="#A55704" stroke="#09251C" stroke-width="3.5" stroke-linejoin="round"/>
                            <rect x="16" y="18" width="48" height="42" rx="14" fill="#F8EADC" stroke="#09251C" stroke-width="4"/>
                            <rect x="21" y="29" width="38" height="15" rx="5" fill="#A55704" stroke="#09251C" stroke-width="3"/>
                            <rect x="27" y="34" width="10" height="5" rx="2" fill="#F8EADC"/>
                            <rect x="43" y="34" width="10" height="5" rx="2" fill="#F8EADC"/>
                            <rect x="24" y="60" width="32" height="12" rx="6" fill="#09251C"/>
                        </svg>
                    `
                },
                {
                    id: 2,
                    name: "KRONOS",
                    svg: `
                        <svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <rect x="33" y="8" width="14" height="12" rx="4" fill="#A55704" stroke="#09251C" stroke-width="3.5"/>
                            <path d="M16 40C16 25.6406 26.7452 16 40 16C53.2548 16 64 25.6406 64 40V52C64 56.4183 60.4183 60 56 60H24C19.5817 60 16 56.4183 16 52V40Z" fill="#F8EADC" stroke="#09251C" stroke-width="4"/>
                            <path d="M23 33H57L52 46H28L23 33Z" fill="#09251C"/>
                            <circle cx="40" cy="39.5" r="4.5" fill="#A55704"/>
                            <rect x="25" y="60" width="30" height="12" rx="6" fill="#A55704" stroke="#09251C" stroke-width="3.5"/>
                        </svg>
                    `
                }
            ];

            const charImages = {};
            CHARACTERS.forEach(c => {
                const img = new Image();
                img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(c.svg.trim());
                charImages[c.id] = img;
            });

            const ALGO_LABELS = {
                "A_STAR": "A* Search Algorithm",
                "DIJKSTRA": "Dijkstra Algorithm",
                "UCS": "Uniform Cost (UCS)",
                "GBFS": "Greedy Best-First (GBFS)",
                "BFS": "Breadth-First (BFS)"
            };

            const DEPTH_LABELS = {
                "2": "Depth 2 (Sangat Dangkal)",
                "4": "Depth 4 (Dangkal)",
                "6": "Depth 6 (Terbatas)",
                "8": "Depth 8 (Menengah)",
                "12": "Depth 12 (Sedang)",
                "16": "Depth 16 (Jauh)",
                "20": "Depth 20 (Sangat Jauh)",
                "0": "Tak Terbatas (Penuh)"
            };

            const uiState = {
                mode: "PvB",
                mapKey: "classic",
                activeTab: 0,
                selectedChars: [0, 1],
                algoSingle: "A_STAR",
                algoBot1: "A_STAR",
                algoBot2: "DIJKSTRA",
                maxDepth: 12
            };

            const MAP_TEMPLATE = [
                [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
                [1,0,0,0,2,2,2,2,2,2,2,2,0,0,1],
                [1,0,1,2,1,2,1,2,1,2,1,2,1,0,1],
                [1,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,0,2,2,2,2,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,2,2,2,2,0,2,2,2,2,1],
                [1,2,1,2,1,2,1,2,1,2,1,2,1,2,1],
                [1,2,2,2,2,2,2,2,2,2,2,2,2,2,1],
                [1,0,1,2,1,2,1,2,1,2,1,2,1,0,1],
                [1,0,0,2,2,2,2,2,2,2,2,0,0,0,1],
                [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
            ];
            const MAPS = {
                classic: { name: 'Klasik', grid: MAP_TEMPLATE },
                corridor: { name: 'Koridor', grid: makeVariantMap('corridor') },
                open: { name: 'Terbuka', grid: makeVariantMap('open') }
            };
            function makeVariantMap(kind) {
                const g = Array.from({length: ROWS}, (_,r) => Array.from({length: COLS}, (_,c) =>
                    r === 0 || c === 0 || r === ROWS-1 || c === COLS-1 ? 1 : 2));
                for (let r=1;r<ROWS-1;r++) for(let c=1;c<COLS-1;c++) {
                    const mr=ROWS-1-r, mc=COLS-1-c;
                    if (r>mr || (r===mr && c>mc)) continue;
                    let permanent = kind === 'corridor'
                        ? ((c===3 || c===7 || c===11) && (r%4!==1)) || ((r===4 || r===8) && (c%4===1))
                        : ((r===3 || r===9) && (c===4 || c===10));
                    const safe = (r<=2 && c<=2) || (mr<=2 && mc<=2) || (r>=ROWS-3 && c>=COLS-3) || (mr>=ROWS-3 && mc>=COLS-3);
                    const center = r>=5 && r<=7 && c>=5 && c<=9;
                    if (safe || center) permanent=false;
                    g[r][c]=g[mr][mc]=permanent ? 1 : (kind==='open' && ((r*7+c*3)%5!==0) ? 0 : 2);
                }
                [[1,1],[1,2],[1,3],[2,1],[11,13],[11,12],[11,11],[10,13]].forEach(([r,c])=>g[r][c]=0);
                return g;
            }
            function validateMaps() {
                Object.entries(MAPS).forEach(([key,m]) => {
                    for(let r=0;r<ROWS;r++) for(let c=0;c<COLS;c++) {
                        if(m.grid[r][c]!==m.grid[ROWS-1-r][COLS-1-c]) throw new Error(`Peta ${key} tidak simetris`);
                    }
                    const q=[[1,1]], seen=new Set(['1,1']);
                    while(q.length){const [r,c]=q.shift(); for(const [dr,dc] of DIRS4){const nr=r+dr,nc=c+dc,k=`${nr},${nc}`; if(nr>0&&nr<ROWS-1&&nc>0&&nc<COLS-1&&m.grid[nr][nc]!==1&&!seen.has(k)){seen.add(k);q.push([nr,nc]);}}}
                    if(!seen.has('11,13')) throw new Error(`Spawn terputus pada peta ${key}`);
                    for (const [r,c] of [[1,1],[11,13]]) {
                        const lSafe = [[r,c],[r,c+(c<7?1:-1)],[r+(r<6?1:-1),c]];
                        if(lSafe.some(([sr,sc])=>m.grid[sr][sc]!==0)) throw new Error(`Area spawn tidak aman pada peta ${key}`);
                    }
                });
            }

            function renderGridToMiniCanvas(canvasEl, mapKey) {
                const g = MAPS[mapKey].grid;
                const c = canvasEl.getContext('2d');
                const w = canvasEl.width / COLS;
                const h = canvasEl.height / ROWS;
                c.clearRect(0, 0, canvasEl.width, canvasEl.height);
                for (let r = 0; r < ROWS; r++) {
                    for (let col = 0; col < COLS; col++) {
                        c.fillStyle = g[r][col] === 1 ? '#1E5442' : (g[r][col] === 2 ? '#A55704' : '#09251C');
                        c.fillRect(col * w, r * h, Math.ceil(w) - 0.5, Math.ceil(h) - 0.5);
                    }
                }
                c.fillStyle = '#F8EADC';
                c.fillRect(w + 1, h + 1, w - 2, h - 2);
                c.fillStyle = '#F3D2AF';
                c.fillRect((COLS - 2) * w + 1, (ROWS - 2) * h + 1, w - 2, h - 2);
            }

            function drawMapPreviews() {
                document.querySelectorAll('#ui-map-picker .map-card').forEach(card => {
                    renderGridToMiniCanvas(card.querySelector('canvas'), card.dataset.map);
                });
            }

            /* =========================================================
               3-SCREEN UI CONTROLLERS
            ========================================================= */
            function goToUIScreen(screenId) {
                document.querySelectorAll('#ui-flow .screen').forEach(el => el.classList.remove('active'));
                const target = document.getElementById(screenId);
                if (target) target.classList.add('active');
            }

            function selectUIMode(modeCode) {
                uiState.mode = modeCode;
                uiState.activeTab = 0;
                renderUISetupScreen();
                goToUIScreen('screen-setup');
            }

            function chooseUIMap(mapKey) {
                uiState.mapKey = mapKey;
                document.querySelectorAll('#ui-map-picker .map-card').forEach(card => {
                    card.classList.toggle('selected', card.dataset.map === mapKey);
                });
                syncSetupState();
            }

            function renderEntityTabs() {
                const tabsContainer = document.getElementById('entity-tabs');
                const labels = uiState.mode === 'PvB' ? ['Player', 'Bot'] : ['Bot 1', 'Bot 2'];
                tabsContainer.innerHTML = labels.map((label, idx) => `
                    <button
                        type="button"
                        class="entity-tab ${uiState.activeTab === idx ? 'active' : ''}"
                        onclick="switchEntityTab(${idx})"
                    >${label}</button>
                `).join('');
            }

            function switchEntityTab(tabIndex) {
                uiState.activeTab = tabIndex;
                renderEntityTabs();
                renderCharacterCards();
            }

            function renderCharacterCards() {
                const gridEl = document.getElementById('char-cards-grid');
                const currentPicked = uiState.selectedChars[uiState.activeTab];
                gridEl.innerHTML = CHARACTERS.map(char => `
                    <div class="char-card ${currentPicked === char.id ? 'selected' : ''}" onclick="chooseUICharacter(${char.id})">
                        <div class="char-avatar">${char.svg}</div>
                        <span class="char-name">${char.name}</span>
                    </div>
                `).join('');
            }

            function chooseUICharacter(charId) {
                uiState.selectedChars[uiState.activeTab] = charId;
                renderCharacterCards();
            }

            function syncSetupState() {
                uiState.algoSingle = document.getElementById('ui-algo-single').value;
                uiState.algoBot1 = document.getElementById('ui-algo-bot1').value;
                uiState.algoBot2 = document.getElementById('ui-algo-bot2').value;
                uiState.maxDepth = parseInt(document.getElementById('ui-depth-select').value, 10) || 0;
            }

            function renderUISetupScreen() {
                const isPvB = uiState.mode === 'PvB';
                document.getElementById('setup-mode-badge').textContent = isPvB ? 'Player Vs Bot' : 'Bot Vs Bot';
                document.getElementById('algo-single-card').style.display = isPvB ? 'flex' : 'none';
                document.getElementById('algo-dual-card').style.display = isPvB ? 'none' : 'flex';

                document.getElementById('ui-algo-single').value = uiState.algoSingle;
                document.getElementById('ui-algo-bot1').value = uiState.algoBot1;
                document.getElementById('ui-algo-bot2').value = uiState.algoBot2;
                document.getElementById('ui-depth-select').value = String(uiState.maxDepth);

                document.querySelectorAll('#ui-map-picker .map-card').forEach(card => {
                    card.classList.toggle('selected', card.dataset.map === uiState.mapKey);
                });

                renderEntityTabs();
                renderCharacterCards();
                syncSetupState();
            }

            function goToConfirmScreen() {
                syncSetupState();
                const isPvB = uiState.mode === 'PvB';
                document.getElementById('confirm-mode-badge').textContent = isPvB ? 'Player Vs Bot' : 'Bot Vs Bot';

                const mapObj = MAPS[uiState.mapKey] || MAPS.classic;
                document.getElementById('confirm-map-name').textContent = mapObj.name;
                renderGridToMiniCanvas(document.getElementById('confirm-map-canvas'), uiState.mapKey);

                const roles = isPvB ? ['Player', 'Bot'] : ['Bot 1', 'Bot 2'];
                document.getElementById('confirm-chars-row').innerHTML = roles.map((role, idx) => {
                    const charObj = CHARACTERS[uiState.selectedChars[idx]];
                    return `
                        <div class="confirm-char-card">
                            <div class="confirm-char-role">${role}</div>
                            <div class="confirm-char-art-box">
                                ${charObj.svg}
                                <strong>${charObj.name}</strong>
                            </div>
                        </div>
                    `;
                }).join('');

                const depthText = DEPTH_LABELS[String(uiState.maxDepth)] || `Depth ${uiState.maxDepth}`;
                const paramsPanel = document.getElementById('confirm-params-panel');
                if (isPvB) {
                    paramsPanel.innerHTML = `
                        <div class="param-row">
                            <div class="param-key">Algoritma Bot</div>
                            <div class="param-val">${ALGO_LABELS[uiState.algoSingle]}</div>
                        </div>
                        <div class="param-row">
                            <div class="param-key">Depth</div>
                            <div class="param-val">${depthText}</div>
                        </div>
                    `;
                } else {
                    paramsPanel.innerHTML = `
                        <div class="param-row">
                            <div class="param-key">Algoritma Bot 1</div>
                            <div class="param-val">${ALGO_LABELS[uiState.algoBot1]}</div>
                        </div>
                        <div class="param-row">
                            <div class="param-key">Algoritma Bot 2</div>
                            <div class="param-val">${ALGO_LABELS[uiState.algoBot2]}</div>
                        </div>
                        <div class="param-row">
                            <div class="param-key">Depth</div>
                            <div class="param-val">${depthText}</div>
                        </div>
                    `;
                }

                goToUIScreen('screen-confirm');
            }

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
                nodesSum2: 0, timeSum2: 0, calls2: 0,
                depthSum1:0, solutionSum1:0, depthSum2:0, solutionSum2:0
            };

            function getActiveAlgoA() {
                return uiState.mode === 'PvB' ? uiState.algoSingle : uiState.algoBot1;
            }

            function getActiveAlgoB() {
                return uiState.algoBot2;
            }

            function resetSeriesStats() {
                seriesStats = {
                    wins1: 0, wins2: 0, draws: 0,
                    nodesSum1: 0, timeSum1: 0, calls1: 0,
                    nodesSum2: 0, timeSum2: 0, calls2: 0,
                    depthSum1:0, solutionSum1:0, depthSum2:0, solutionSum2:0
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
                document.getElementById('avgDepthA').innerText = seriesStats.calls1 ? (seriesStats.depthSum1/seriesStats.calls1).toFixed(1) : '0';
                document.getElementById('avgSolutionA').innerText = seriesStats.calls1 ? (seriesStats.solutionSum1/seriesStats.calls1).toFixed(1) : '0';

                const avgN2 = seriesStats.calls2 ? (seriesStats.nodesSum2 / seriesStats.calls2).toFixed(1) : "0";
                const avgT2 = seriesStats.calls2 ? (seriesStats.timeSum2 / seriesStats.calls2).toFixed(3) + " ms" : "0 ms";
                document.getElementById('avgNodesB').innerText = avgN2;
                document.getElementById('avgTimeB').innerText = avgT2;
                document.getElementById('avgDepthB').innerText = seriesStats.calls2 ? (seriesStats.depthSum2/seriesStats.calls2).toFixed(1) : '0';
                document.getElementById('avgSolutionB').innerText = seriesStats.calls2 ? (seriesStats.solutionSum2/seriesStats.calls2).toFixed(1) : '0';
            }

            const OVERDRIVE_TICKS = 1200;    // 20 detik
            const SUDDEN_DEATH_TICKS = 2100; // 35 detik

            function getCurrentPhase() {
                if (simTicks >= SUDDEN_DEATH_TICKS) {
                    return { name: "SUDDEN DEATH", maxBombs: 3, fuse: 36 };
                }
                if (simTicks >= OVERDRIVE_TICKS) {
                    return { name: "OVERDRIVE", maxBombs: 2, fuse: 48 };
                }
                return { name: "NORMAL", maxBombs: 1, fuse: 60 };
            }

            function updatePhaseHUD() {
                const phase = getCurrentPhase();
                const depthStr = uiState.maxDepth > 0 ? `${uiState.maxDepth}` : '∞';
                const elapsed = Math.floor(simTicks / 60);
                document.getElementById('phaseInfo').innerHTML =
                    `<span class="status-phase">${phase.name}</span>` +
                    `<span><small>Depth</small><b>${depthStr}</b></span>` +
                    `<span><small>Bom</small><b>${phase.maxBombs}</b></span>` +
                    `<span><small>Jangkauan</small><b>3x3</b></span>` +
                    `<span><small>Waktu</small><b>${elapsed}s</b></span>`;
            }

            function makeBot(id, roleLabel, color, charObj, r, c) {
                const displayBotLabel = id === 1 ? 'Bot 1' : 'Bot 2';
                return {
                    id,
                    roleLabel,
                    name: `${displayBotLabel} (${charObj.name})`,
                    charId: charObj.id,
                    charName: charObj.name,
                    color,
                    r, c,
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
                validateMaps();
                const selectedMap = MAPS[uiState.mapKey] || MAPS.classic;
                grid = JSON.parse(JSON.stringify(selectedMap.grid));
                document.getElementById('mapNameGame').innerText = selectedMap.name;
                document.getElementById('mapNameAnalysis').innerText = selectedMap.name;
                currentGameMode = uiState.mode;

                const char1 = CHARACTERS[uiState.selectedChars[0]] || CHARACTERS[0];
                const char2 = CHARACTERS[uiState.selectedChars[1]] || CHARACTERS[1];
                const algoA = getActiveAlgoA();
                const algoB = getActiveAlgoB();
                const depthDisplay = uiState.maxDepth > 0 ? `Depth ${uiState.maxDepth}` : 'Tak Terbatas';
                const depthShort = uiState.maxDepth > 0 ? `${uiState.maxDepth}` : '∞';

                document.getElementById('summaryMode').innerText = currentGameMode === 'PvB' ? 'Player vs Bot' : 'Bot vs Bot';
                document.getElementById('summaryDepth').innerText = depthDisplay;
                document.getElementById('algoNameA').innerText = algoA;
                document.getElementById('algoNameB').innerText = algoB;
                document.getElementById('limitDepthA').innerText = depthShort;
                document.getElementById('limitDepthB').innerText = depthShort;

                if (currentGameMode === "PvB") {
                    document.getElementById('summaryEntity1Role').innerText = `Player · ${char1.name}`;
                    document.getElementById('summaryEntity1Icon').innerHTML = char1.svg;
                    document.getElementById('summaryEntity1Sub').innerText = 'WASD / Panah + Spasi';

                    document.getElementById('summaryEntity2Role').innerText = `Bot · ${char2.name}`;
                    document.getElementById('summaryEntity2Icon').innerHTML = char2.svg;
                    document.getElementById('summaryEntity2Sub').innerText = ALGO_LABELS[algoA];

                    document.getElementById('bot2StatsBox').style.display = 'none';
                    document.querySelectorAll('.bot-b-column').forEach(el => { el.style.display = 'none'; });
                    document.getElementById('playerStats').style.display = 'block';
                    document.getElementById('playerHudIcon').innerHTML = char1.svg;
                    document.getElementById('playerHealthLabel').innerText = `Nyawa (${char1.name})`;
                    document.getElementById('bot1StatsBox').innerHTML =
                        `<span class="table-head-flex">${char2.svg}<span>Bot (${char2.name})</span></span>`;

                    player = {
                        id: 0,
                        charId: char1.id,
                        charName: char1.name,
                        r: 1, c: 1, prevR: 1, prevC: 1,
                        alive: true,
                        health: 3,
                        maxHealth: 3,
                        iFrames: 0,
                        ammo: 1, maxAmmo: 1,
                        isReloading: false,
                        reloadTimer: 0,
                        reloadMaxTimer: 150
                    };
                    enemies = [ makeBot(1, 'B1', COLORS.botA, char2, 11, 13) ];
                } else {
                    document.getElementById('summaryEntity1Role').innerText = `Bot 1 · ${char1.name}`;
                    document.getElementById('summaryEntity1Icon').innerHTML = char1.svg;
                    document.getElementById('summaryEntity1Sub').innerText = ALGO_LABELS[algoA];

                    document.getElementById('summaryEntity2Role').innerText = `Bot 2 · ${char2.name}`;
                    document.getElementById('summaryEntity2Icon').innerHTML = char2.svg;
                    document.getElementById('summaryEntity2Sub').innerText = ALGO_LABELS[algoB];

                    document.getElementById('bot2StatsBox').style.display = '';
                    document.querySelectorAll('.bot-b-column').forEach(el => { el.style.display = ''; });
                    document.getElementById('playerStats').style.display = 'none';
                    document.getElementById('bot1StatsBox').innerHTML =
                        `<span class="table-head-flex">${char1.svg}<span>Bot 1 (${char1.name})</span></span>`;
                    document.getElementById('bot2StatsBox').innerHTML =
                        `<span class="table-head-flex">${char2.svg}<span>Bot 2 (${char2.name})</span></span>`;

                    player = {
                        id: 0, charId: char1.id, charName: char1.name,
                        r: 1, c: 1, prevR: 1, prevC: 1, alive: false,
                        health: 0, maxHealth: 3, iFrames: 0, ammo: 0, maxAmmo: 1
                    };
                    enemies = [
                        makeBot(1, 'B1', COLORS.botA, char1, 1, 1),
                        makeBot(2, 'B2', COLORS.botB, char2, 11, 13)
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
                render();
            }

            function updateHealthDisplay() {
                document.getElementById('healthVal').innerText =
                    `${player.health} / ${player.maxHealth}${player.health <= 0 ? ' · Mati' : ''}`;
            }

            function updateAmmoDisplay() {
                const ammoEl = document.getElementById('ammoVal');
                const fillEl = document.getElementById('reloadFill');

                if (player.isReloading) {
                    let progress = ((player.reloadMaxTimer - player.reloadTimer) / player.reloadMaxTimer) * 100;
                    fillEl.style.width = `${progress}%`;
                    ammoEl.innerText = `Mengisi ulang...`;
                } else {
                    fillEl.style.width = `100%`;
                    ammoEl.innerText = player.ammo > 0 ? "1 / 1" : "Kosong";
                }
            }

            function damagePlayer() {
                if (player.iFrames <= 0 && player.alive) {
                    player.health--;
                    player.iFrames = 60;
                    updateHealthDisplay();
                    if (player.health <= 0) {
                        player.alive = false;
                        const botName = enemies[0] ? enemies[0].name : 'Bot 1';
                        seriesStats.wins1++;
                        updateSeriesHUD();
                        setGameOver(false, `${botName} Menang!`, COLORS.botA);
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

            // Jangkauan ledakan tetap kotak 3x3 (dr = -1..1, dc = -1..1 => maks 9 ubin)
            function blastTiles(r, c) {
                const tiles = [];
                for (let dr = -1; dr <= 1; dr++) {
                    for (let dc = -1; dc <= 1; dc++) {
                        const nr = r + dr, nc = c + dc;
                        if (nr < 0 || nr >= ROWS || nc < 0 || nc >= COLS) continue;
                        if (grid[nr][nc] === 1 || grid[nr][nc] === 4) continue;
                        tiles.push([nr, nc]);
                    }
                }
                return tiles;
            }

            function getDangerTimes() {
                const sets = bombs.map(b => blastTiles(b.r, b.c));
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
                bombs.push({ r, c, timer: phase.fuse, ownerId: -1 });
                const times = getDangerTimes();
                bombs.pop();
                return getEscapeMove(r, c, times, dirs, others);
            }

            function manhattan(a, b) { return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]); }

            function hasAdjacentWood(r, c) {
                for (let dr = -1; dr <= 1; dr++) {
                    for (let dc = -1; dc <= 1; dc++) {
                        if (dr === 0 && dc === 0) continue;
                        const nr = r + dr, nc = c + dc;
                        if (nr >= 0 && nr < ROWS && nc >= 0 && nc < COLS && grid[nr][nc] === 2) return true;
                    }
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

            function wouldHitEnemy(r, c, hunt) {
                const phase = getCurrentPhase();
                bombs.push({ r, c, timer: phase.fuse, ownerId: -1 });
                const t2 = getDangerTimes();
                bombs.pop();
                return t2.has(`${hunt[0]},${hunt[1]}`);
            }

            function decideAction(e, resItem, hunt, times, blocked) {
                const stay = { nextR: e.r, nextC: e.c, bomb: false, waitingBomb: false };
                const dirs = shuffled(DIRS4);
                const phase = getCurrentPhase();

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

                if (next && grid[next[0]][next[1]] === 2) {
                    const b = tryBomb();
                    if (b) return b;
                    if (ownBombsCount > 0) return { nextR: e.r, nextC: e.c, bomb: false, waitingBomb: true };
                    return stay;
                }

                const bombedRecentlyHere = e.recentBombSpots.some(s => s.r === e.r && s.c === e.c);
                const enemyCornered = walkableNeighborCount(hunt[0], hunt[1]) <= 2;
                const distToEnemy = manhattan([e.r, e.c], hunt);

                // Jarak Manhattan <= 2 mencakup seluruh kotak 3x3 termasuk sudut diagonal
                const directHit = (distToEnemy <= 2) && wouldHitEnemy(e.r, e.c, hunt);
                const pinchTrap = (phase.maxBombs >= 2) && (distToEnemy <= 3) && (ownBombsCount === 1);

                const canOffensiveBomb = (e.bombCooldown <= 0) &&
                                         (!bombedRecentlyHere || hasAdjacentWood(e.r, e.c) || enemyCornered || pinchTrap);

                if (canPlaceMoreBombs && canOffensiveBomb && (directHit || pinchTrap)) {
                    const b = tryBomb();
                    if (b) return b;
                }

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
                const algoA = getActiveAlgoA();
                const algoB = getActiveAlgoB();
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
                        max_depth: uiState.maxDepth,
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
                                document.getElementById('depthA').innerText = resItem.max_depth;
                                document.getElementById('solutionA').innerText = resItem.solution_depth;
                                seriesStats.depthSum1 += resItem.max_depth; seriesStats.solutionSum1 += resItem.solution_depth;
                            } else {
                                document.getElementById('nodesB').innerText = resItem.nodes_explored;
                                document.getElementById('timeB').innerText = resItem.exec_time_ms + ' ms';
                                seriesStats.nodesSum2 += resItem.nodes_explored;
                                seriesStats.timeSum2 += resItem.exec_time_ms;
                                seriesStats.calls2++;
                                document.getElementById('depthB').innerText = resItem.max_depth;
                                document.getElementById('solutionB').innerText = resItem.solution_depth;
                                seriesStats.depthSum2 += resItem.max_depth; seriesStats.solutionSum2 += resItem.solution_depth;
                            }
                            updateSeriesHUD();

                            aiPaths = aiPaths.filter(p => p.ownerId !== enemyObj.id);
                            aiPaths.push({ ownerId: enemyObj.id, path: resItem.full_path, color: enemyObj.color });

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

                bombs.push({
                    id: Date.now(),
                    ownerId: player.id,
                    r: player.r,
                    c: player.c,
                    timer: 110,
                    maxTimer: 110
                });
                grid[player.r][player.c] = 3;

                player.ammo--;
                updateAmmoDisplay();
                player.isReloading = true;
                player.reloadTimer = player.reloadMaxTimer;
            }

            function placeBotBomb(r, c, ownerId) {
                const phase = getCurrentPhase();
                const ownCount = bombs.filter(b => b.ownerId === ownerId).length;
                if (ownCount >= phase.maxBombs) return;
                if (grid[r][c] !== 0 || bombs.some(b => b.r === r && b.c === c)) return;

                bombs.push({
                    id: Date.now() + Math.random(),
                    ownerId: ownerId,
                    r: r,
                    c: c,
                    timer: phase.fuse,
                    maxTimer: phase.fuse
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
                        const botName = enemies[0] ? enemies[0].name : 'Bot 1';
                        seriesStats.wins1++;
                        updateSeriesHUD();
                        setGameOver(false, `${botName} Menang!`, COLORS.botA);
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
                        explodeBomb(bombR, bombC);
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

            // Menggunakan blastTiles(r, c) yang persis kotak 3x3 (9 ubin)
            function explodeBomb(r, c) {
                for (const [nr, nc] of blastTiles(r, c)) {
                    explosions.push({ r: nr, c: nc, timer: 20 });

                    if (player.alive && player.r === nr && player.c === nc) damagePlayer();
                    enemies.forEach(e => { if (e.alive && e.r === nr && e.c === nc) e.alive = false; });

                    if (grid[nr][nc] === 2) {
                        grid[nr][nc] = 0;
                    } else if (grid[nr][nc] === 3) {
                        let chainedBomb = bombs.find(b => b.r === nr && b.c === nc);
                        if (chainedBomb) chainedBomb.timer = 0;
                    }
                }

                checkWinCondition();
            }

            function checkWinCondition() {
                if (gameOver) return;
                const aliveBots = enemies.filter(e => e.alive);

                if (currentGameMode === "PvB") {
                    if (aliveBots.length === 0 && player.alive) {
                        seriesStats.wins2++;
                        updateSeriesHUD();
                        setGameOver(true, `Player (${player.charName}) Menang!`, COLORS.player);
                    }
                } else {
                    if (aliveBots.length === 1) {
                        const winner = aliveBots[0];
                        if (winner.id === 1) seriesStats.wins1++;
                        else seriesStats.wins2++;
                        updateSeriesHUD();
                        setGameOver(true, `${winner.name} Menang!`, winner.color);
                    } else if (aliveBots.length === 0) {
                        seriesStats.draws++;
                        updateSeriesHUD();
                        setGameOver(false, `Seri! Double KO`, COLORS.danger);
                    }
                }
            }

            function setGameOver(isWin, text, badgeColor) {
                gameOver = true;
                const msg = document.getElementById('statusMsg');
                msg.innerText = text;
                msg.style.color = badgeColor || (isWin ? COLORS.botA : COLORS.danger);
            }

            function lerp(start, end, amt) { return (1 - amt) * start + amt * end; }

            /* =========================================================
               CANVAS CHARACTER RENDERER (COSMETIC SVG SPRITE + NAMEPLATE)
            ========================================================= */
            function roundedRectPath(c, x, y, w, h, r) {
                const rad = Math.min(r, w / 2, h / 2);
                c.beginPath();
                c.moveTo(x + rad, y);
                c.arcTo(x + w, y, x + w, y + h, rad);
                c.arcTo(x + w, y + h, x, y + h, rad);
                c.arcTo(x, y + h, x, y, rad);
                c.arcTo(x, y, x + w, y, rad);
                c.closePath();
            }

            function drawCharacterSprite(x, y, charId, charName, roleTag, teamColor, isPlayer) {
                ctx.save();

                // 1. Ground team aura ring
                ctx.fillStyle = isPlayer
                    ? 'rgba(248, 234, 220, 0.25)'
                    : (teamColor === COLORS.botA ? 'rgba(79, 209, 197, 0.28)' : 'rgba(246, 173, 85, 0.28)');
                ctx.beginPath();
                ctx.ellipse(x + CELL / 2, y + CELL - 5, 14, 5, 0, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = teamColor;
                ctx.lineWidth = 2;
                ctx.stroke();

                // 2. Render exact pre-loaded character SVG sprite
                const img = charImages[charId];
                if (img && img.complete && img.naturalWidth > 0) {
                    ctx.drawImage(img, x + 2, y + 1, CELL - 4, CELL - 4);
                } else {
                    ctx.fillStyle = COLORS.player;
                    ctx.beginPath();
                    ctx.arc(x + CELL / 2, y + CELL / 2, 14, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.strokeStyle = COLORS.ink;
                    ctx.lineWidth = 2.5;
                    ctx.stroke();
                }

                // 3. Floating character nameplate badge above sprite
                const labelText = `${roleTag}·${charName}`;
                ctx.font = '700 8.5px "Chakra Petch", sans-serif';
                const textW = ctx.measureText(labelText).width;
                const pillW = textW + 8;
                const pillH = 12;
                const pillX = Math.max(2, Math.min(canvas.width - pillW - 2, x + (CELL - pillW) / 2));
                const pillY = Math.max(2, y - 10);

                roundedRectPath(ctx, pillX, pillY, pillW, pillH, 5);
                ctx.fillStyle = 'rgba(9, 37, 28, 0.9)';
                ctx.fill();
                ctx.strokeStyle = teamColor;
                ctx.lineWidth = 1.2;
                ctx.stroke();

                ctx.fillStyle = teamColor;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(labelText, pillX + pillW / 2, pillY + pillH / 2 + 0.5);

                ctx.restore();
            }

            function drawPlayer(x, y) {
                if (player.iFrames % 10 > 5) return;
                drawCharacterSprite(x, y, player.charId, player.charName, 'P1', COLORS.player, true);
            }

            function drawEnemyBot(x, y, enemyObj) {
                drawCharacterSprite(
                    x, y,
                    enemyObj.charId,
                    enemyObj.charName,
                    enemyObj.roleLabel,
                    enemyObj.color,
                    false
                );
            }

            function drawBomb(x, y, timer) {
                let pulse = (timer < 24 && timer % 6 < 3) ? 2 : 0;
                ctx.fillStyle = pulse ? COLORS.danger : '#051510';
                ctx.beginPath();
                ctx.arc(x + CELL/2, y + CELL/2 + 2, CELL/2 - 6 + pulse, 0, Math.PI*2);
                ctx.fill();
                ctx.strokeStyle = COLORS.line;
                ctx.lineWidth = 2;
                ctx.stroke();

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
                            ctx.strokeStyle = 'rgba(243, 210, 175, 0.35)';
                            ctx.lineWidth = 1.5;
                            ctx.strokeRect(x + 4, y + 4, CELL - 8, CELL - 8);
                        } else if (grid[r][c] === 2) {
                            ctx.fillStyle = COLORS.brick;
                            ctx.fillRect(x, y, CELL, CELL);
                            ctx.strokeStyle = COLORS.ink;
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

                explosions.forEach(ex => {
                    ctx.fillStyle = COLORS.danger;
                    ctx.fillRect(ex.c * CELL, ex.r * CELL, CELL - 1, CELL - 1);
                });

                if (player.alive) {
                    playerPixel.x = lerp(playerPixel.x, player.c * CELL, 0.32);
                    playerPixel.y = lerp(playerPixel.y, player.r * CELL, 0.32);
                    drawPlayer(playerPixel.x, playerPixel.y);
                }

                enemies.forEach((e, idx) => {
                    if (e.alive) {
                        enemyPixels[idx].x = lerp(enemyPixels[idx].x, e.c * CELL, 0.32);
                        enemyPixels[idx].y = lerp(enemyPixels[idx].y, e.r * CELL, 0.32);
                        drawEnemyBot(enemyPixels[idx].x, enemyPixels[idx].y, e);
                    }
                });
            }

            function stepSimulationOnce() {
                if (gameOver) return;
                simTicks++;
                document.getElementById('tickValue').innerText = simTicks;
                if (simTicks % 20 === 0) updatePhaseHUD();
                updateSuddenDeathCollapse();
                updateBombsAndExplosions();
                if (!gameOver && simTicks % 12 === 0) moveEnemiesRealtime();
            }

            let paused = true;
            function gameLoop() {
                if (grid && !paused && !gameOver) {
                    stepSimulationOnce();
                }
                if (grid) render();
                requestAnimationFrame(gameLoop);
            }

            window.addEventListener('keydown', (e) => {
                if (!document.body.classList.contains('playing')) return;
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

            // Inisialisasi UI 3 Layar & Event Listeners Arena
            validateMaps();
            drawMapPreviews();
            renderUISetupScreen();

            // Tombol "OMKE GAS" langsung masuk ke arena permainan
            document.getElementById('omkeGasBtn').addEventListener('click', () => {
                syncSetupState();
                resetSeriesStats();
                initGame();
                paused = false;
                document.getElementById('pauseBtn').innerText = 'Jeda';
                document.body.classList.add('playing');
            });

            document.getElementById('settingsBackBtn').addEventListener('click', () => {
                paused = true;
                document.body.classList.remove('playing');
                renderUISetupScreen();
                goToUIScreen('screen-setup');
            });

            document.getElementById('menuBtn').addEventListener('click', () => {
                paused = true;
                document.body.classList.remove('playing');
                goToUIScreen('screen-menu');
            });

            document.getElementById('pauseBtn').addEventListener('click', e => {
                paused = !paused;
                e.currentTarget.innerText = paused ? 'Lanjut' : 'Jeda';
            });

            document.getElementById('stepBtn').addEventListener('click', () => {
                if (paused) stepSimulationOnce();
            });

            document.getElementById('restartBtn').addEventListener('click', () => {
                resetSeriesStats();
                initGame();
            });

            gameLoop();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(
        content=html_content,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)