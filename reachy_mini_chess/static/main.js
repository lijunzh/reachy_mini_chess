// Digital board: click a piece, then click where it goes.

const GLYPHS = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const FILES = "abcdefgh";
const KID_SLIDE_MS = 250;     // your move: quick, you already know what it was
const ROBOT_SLIDE_MS = 900;   // Reachy's move: slow enough to follow with your eyes

let state = null;
let selected = null;   // square name like "e2"
let busy = false;
let highlight = [];    // squares to mark for a hint or suggestion

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

// Run one user action with the board locked. On failure, reload the server's
// board (it is the truth) so the page cannot drift.
async function act(work, waitingText) {
    if (busy) return;
    busy = true;
    if (waitingText) $("status").textContent = waitingText;
    try {
        await work();
    } catch (e) {
        selected = null;
        try { render(await api("/api/state")); } catch (_) { /* keep the old board */ }
        $("status").textContent = "⚠️ " + e.message;
    } finally {
        busy = false;
    }
}

const post = (path, body, waitingText) => act(async () => render(await api(path, body)), waitingText);

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

// --- turns -------------------------------------------------------------------

async function playKidMove(uci) {
    const s = await api("/api/move", { uci, reply: false });
    await showMove(s, KID_SLIDE_MS);
    if (!s.game_over && !s.kid_to_move) await robotTurn();
}

// The server holds the reply while the robot does its thinking gesture.
async function robotTurn() {
    $("status").textContent = "Reachy is thinking…";
    $("status").classList.add("waiting");
    const s = await api("/api/robot-move", {});
    await showMove(s, ROBOT_SLIDE_MS);
}

// Animate the state's last move on the board as drawn now, then draw the new state.
async function showMove(s, ms) {
    if (s.last_move) await animate(s.last_move, ms);
    render(s);
}

function animate(motion, ms) {
    const cell = (square) => $("board").querySelector(`[data-square="${square}"]`);
    const moving = [];
    for (const [from, to] of motion.slides) {
        const piece = cell(from) && cell(from).querySelector(".piece");
        if (!piece || !cell(to)) continue;
        const a = cell(from).getBoundingClientRect();
        const b = cell(to).getBoundingClientRect();
        moving.push([piece, b.left - a.left, b.top - a.top]);
    }
    const victimCell = motion.captured && cell(motion.captured);
    const victim = victimCell && victimCell.querySelector(".piece");
    if (!moving.length) return Promise.resolve();

    if (victimCell) victimCell.classList.add("taken");
    // Start on the next frame so the pieces slide from where they are now.
    requestAnimationFrame(() => {
        for (const [piece, dx, dy] of moving) {
            piece.classList.add("moving");
            piece.style.transition = `transform ${ms}ms ease-in-out`;
            piece.style.transform = `translate(${dx}px, ${dy}px)`;
        }
        if (victim) {
            // The taken piece shrinks away as the attacker arrives.
            const fade = Math.round(ms * 0.45);
            const wait = ms - fade;
            victim.style.transition = `opacity ${fade}ms ease-in ${wait}ms, transform ${fade}ms ease-in ${wait}ms`;
            victim.classList.add("vanish");
        }
    });
    return sleep(ms + 200);
}

// --- input -------------------------------------------------------------------

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
            drawBoard();
            act(() => playKidMove(move));
            return;
        }
    }
    selected = legalFrom(square).length ? square : null;
    drawBoard();
}

// --- drawing -----------------------------------------------------------------

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

function drawBoard() {
    const board = $("board");
    board.innerHTML = "";
    const pieces = parseFen(state.fen);
    const whiteBottom = state.robot_color === "black";
    const last = state.last_move ? state.last_move.slides[0] : [];
    const taken = state.last_move ? state.last_move.captured : null;
    const targets = selected ? legalFrom(selected).map((m) => m.slice(2, 4)) : [];

    for (let r = 0; r < 8; r++) {
        for (let f = 0; f < 8; f++) {
            const file = whiteBottom ? f : 7 - f;
            const rank = whiteBottom ? 8 - r : r + 1;
            const square = FILES[file] + rank;
            const cell = document.createElement("button");
            cell.className = "sq " + ((file + rank) % 2 ? "dark" : "light");
            cell.dataset.square = square;
            if (last.includes(square)) cell.classList.add("last");
            if (square === taken) cell.classList.add("taken");
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

const PIECE_ORDER = "qrbnp";

function drawCaptures() {
    const kidWhite = state.robot_color === "black";
    const show = (id, kinds, white) => {
        const sorted = [...kinds].sort((a, b) => PIECE_ORDER.indexOf(a) - PIECE_ORDER.indexOf(b));
        $(id).innerHTML = sorted.length
            ? sorted.map((k) => `<span class="piece ${white ? "white" : "black"}">${GLYPHS[k]}\uFE0E</span>`).join("")
            : `<span class="small">nothing yet</span>`;
    };
    show("cap-robot", state.captured_by_robot, kidWhite);   // Reachy took the kid's pieces
    show("cap-kid", state.captured_by_kid, !kidWhite);
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

    const waiting = !s.game_over && !s.kid_to_move;
    let status;
    if (s.game_over) status = "Game over: " + s.result;
    else if (s.kid_to_move) status = (s.in_check ? "Check! " : "") + `Your move (${s.turn})`;
    else status = "Reachy is thinking…";
    $("status").textContent = status;
    $("status").classList.toggle("waiting", waiting);
    drawBoard();
    drawCaptures();
}

// --- buttons -----------------------------------------------------------------

$("elo").addEventListener("input", (e) => { $("elo-label").textContent = e.target.value; });
$("elo").addEventListener("change", (e) => post("/api/elo", { elo: Number(e.target.value) }));
$("new-game").addEventListener("click", () => {
    highlight = [];
    act(async () => {
        const s = await api("/api/new", { elo: Number($("elo").value), robot_color: $("robot-color").value });
        render(s);
        if (!s.game_over && !s.kid_to_move) await robotTurn();
    }, "Setting up…");
});
$("take-back").addEventListener("click", () => { highlight = []; post("/api/take-back", {}); });
$("hint").addEventListener("click", () => post("/api/hint", {}, "Looking for a good move…"));
$("load-fen").addEventListener("click", () => { highlight = []; post("/api/position", { fen: $("fen").value.trim() }); });
$("suggest").addEventListener("click", () => post("/api/recommend", {}, "Reachy is thinking…"));
$("robot-move").addEventListener("click", () => { highlight = []; act(robotTurn); });

api("/api/state").then(render).catch((e) => { $("status").textContent = "⚠️ " + e.message; });
