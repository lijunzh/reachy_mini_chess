// Digital board: click a piece, then click where it goes.

const GLYPHS = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const FILES = "abcdefgh";

let state = null;
let selected = null;   // square name like "e2"
let busy = false;
let highlight = [];    // squares to mark for a hint or suggestion

const $ = (id) => document.getElementById(id);

async function api(path, body) {
    const resp = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || resp.statusText);
    return data;
}

async function act(path, body, waitingText) {
    if (busy) return;
    busy = true;
    if (waitingText) $("status").textContent = waitingText;
    try {
        render(await api(path, body));
    } catch (e) {
        // The server's board is the truth. Reload it so the page cannot drift.
        selected = null;
        try { render(await api("/api/state")); } catch (_) { /* keep the old board */ }
        $("status").textContent = "⚠️ " + e.message;
    } finally {
        busy = false;
    }
}

// Pick up board changes made elsewhere: an app restart, another tab, and later the camera.
async function resync() {
    if (busy) return;
    try {
        const s = await api("/api/state");
        if (!busy && state && (s.fen !== state.fen || s.history.length !== state.history.length)) {
            selected = null;
            highlight = [];
            render(s);
        }
    } catch (_) { /* app stopped; try again next tick */ }
}
setInterval(resync, 2000);

function parseFen(fen) {
    const pieces = {};
    fen.split(" ")[0].split("/").forEach((row, i) => {
        let file = 0;
        for (const ch of row) {
            if (/\d/.test(ch)) { file += Number(ch); continue; }
            pieces[FILES[file] + (8 - i)] = ch;
            file += 1;
        }
    });
    return pieces;
}

function legalFrom(square) {
    return state.legal.filter((m) => m.startsWith(square));
}

const PROMOTIONS = [["q", "Queen"], ["r", "Rook"], ["b", "Bishop"], ["n", "Knight"]];

// Ask what the pawn becomes. Resolves to the full move, or null if cancelled.
function choosePromotion(moves) {
    return new Promise((resolve) => {
        const overlay = $("promo");
        const choices = $("promo-choices");
        const onKey = (e) => { if (e.key === "Escape") close(null); };
        const close = (move) => {
            overlay.hidden = true;
            document.removeEventListener("keydown", onKey);
            resolve(move);
        };
        choices.innerHTML = "";
        for (const [letter, name] of PROMOTIONS) {
            const move = moves.find((m) => m.endsWith(letter));
            if (!move) continue;
            const button = document.createElement("button");
            button.className = "promo-choice";
            button.innerHTML = `<span class="piece ${state.turn}">${GLYPHS[letter]}︎</span><span>${name}</span>`;
            button.addEventListener("click", () => close(move));
            choices.appendChild(button);
        }
        overlay.onclick = (e) => { if (e.target === overlay) close(null); };
        document.addEventListener("keydown", onKey);
        overlay.hidden = false;
        choices.querySelector("button").focus();
    });
}

async function onSquareClick(square) {
    if (busy || !state || !state.kid_to_move || state.game_over) return;
    if (selected) {
        const moves = legalFrom(selected).filter((m) => m.slice(2, 4) === square);
        if (moves.length) {
            // Several moves to one square only happens on promotion.
            const move = moves.length > 1 ? await choosePromotion(moves) : moves[0];
            if (!move) return;  // cancelled: keep the pawn selected
            selected = null;
            highlight = [];
            act("/api/move", { uci: move }, "Reachy is thinking…");
            return;
        }
    }
    selected = legalFrom(square).length ? square : null;
    drawBoard();
}

function drawBoard() {
    const board = $("board");
    board.innerHTML = "";
    const pieces = parseFen(state.fen);
    const whiteBottom = state.robot_color === "black";
    const last = state.last_robot_move ? state.last_robot_move.uci : "";
    const targets = selected ? legalFrom(selected).map((m) => m.slice(2, 4)) : [];

    for (let r = 0; r < 8; r++) {
        for (let f = 0; f < 8; f++) {
            const file = whiteBottom ? f : 7 - f;
            const rank = whiteBottom ? 8 - r : r + 1;
            const square = FILES[file] + rank;
            const cell = document.createElement("button");
            cell.className = "sq " + ((file + rank) % 2 ? "dark" : "light");
            if (last.slice(0, 2) === square || last.slice(2, 4) === square) cell.classList.add("last");
            if (highlight.includes(square)) cell.classList.add("hint");
            if (square === selected) cell.classList.add("selected");
            if (targets.includes(square)) cell.classList.add("target");

            const piece = pieces[square];
            if (piece) {
                const span = document.createElement("span");
                span.className = "piece " + (piece === piece.toUpperCase() ? "white" : "black");
                span.textContent = GLYPHS[piece.toLowerCase()] + "︎";
                cell.appendChild(span);
            }
            if (f === 0) cell.dataset.rank = rank;
            if (r === 7) cell.dataset.file = FILES[file];
            cell.setAttribute("aria-label", square + (piece ? " " + piece : ""));
            cell.addEventListener("click", () => onSquareClick(square));
            board.appendChild(cell);
        }
    }
}

function pawns(cp) {
    if (Math.abs(cp) >= 90000) return cp > 0 ? "mate" : "gets mated";
    return (cp > 0 ? "+" : "") + (cp / 100).toFixed(2);
}

function drawThinking(rec, title) {
    if (!rec) return;
    const L = rec.level;
    const rows = rec.candidates.map((c, i) =>
        `<tr class="${i + 1 === rec.rank ? "chosen" : ""}"><td>${i + 1}</td><td>${c.san}</td><td>${pawns(c.score_cp)}</td></tr>`
    ).join("");
    $("thinking").innerHTML = `
        <p><strong>${title}:</strong> ${rec.san} — choice #${rec.rank} of ${rec.candidates.length}
        ${rec.blunder ? "<span class='tag'>oops on purpose</span>" : ""}</p>
        <p class="small">${rec.kind === "hint"
            ? `Full strength: looks ${L.depth} turns ahead.`
            : `Playing like ${L.elo} Elo: looks ${L.depth} turns ahead, compares ${L.multipv} moves,
               sloppiness ${Math.round(L.temperature_cp)}, blunder chance ${Math.round(L.blunder_rate * 100)}%.`}
        Engine: ${rec.analyzer}.</p>
        <table><tr><th>#</th><th>Move</th><th>Score for mover</th></tr>${rows}</table>`;
}

function render(s) {
    state = s;
    $("elo").value = s.elo;
    $("elo-label").textContent = s.elo;
    $("robot-color").value = s.robot_color;
    $("message").textContent = s.message || "…";
    $("fen").value = s.fen;

    const rec = s.recommendation;
    if (rec) {
        highlight = [rec.uci.slice(0, 2), rec.uci.slice(2, 4)];
        $("message").textContent = (rec.kind === "hint" ? "Hint: " : "I'd suggest: ") + rec.words;
        drawThinking(rec, rec.kind === "hint" ? "Hint" : "Suggestion");
    } else if (s.last_robot_move) {
        drawThinking(s.last_robot_move, "Reachy played");
    }

    $("history").innerHTML = "";
    for (let i = 0; i < s.history.length; i += 2) {
        const li = document.createElement("li");
        li.textContent = s.history[i] + (s.history[i + 1] ? "   " + s.history[i + 1] : "");
        $("history").appendChild(li);
    }

    let status;
    if (s.game_over) status = "Game over: " + s.result;
    else if (s.kid_to_move) status = (s.in_check ? "Check! " : "") + `Your move (${s.turn})`;
    else status = "Reachy's move";
    $("status").textContent = status;
    drawBoard();
}

$("elo").addEventListener("input", (e) => { $("elo-label").textContent = e.target.value; });
$("elo").addEventListener("change", (e) => act("/api/elo", { elo: Number(e.target.value) }));
$("new-game").addEventListener("click", () => {
    highlight = [];
    act("/api/new", { elo: Number($("elo").value), robot_color: $("robot-color").value }, "Setting up…");
});
$("take-back").addEventListener("click", () => { highlight = []; act("/api/take-back", {}); });
$("hint").addEventListener("click", () => act("/api/hint", {}, "Looking for a good move…"));
$("load-fen").addEventListener("click", () => { highlight = []; act("/api/position", { fen: $("fen").value.trim() }); });
$("suggest").addEventListener("click", () => act("/api/recommend", {}, "Reachy is thinking…"));
$("robot-move").addEventListener("click", () => { highlight = []; act("/api/robot-move", {}, "Reachy is thinking…"); });

api("/api/state").then(render).catch((e) => { $("status").textContent = "⚠️ " + e.message; });
