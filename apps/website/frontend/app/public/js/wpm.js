const wordBank = [
  "arcade", "neon", "combo", "rapid", "focus", "velocity", "signal", "matrix", "pixel", "boost",
  "alpha", "gamma", "reactor", "quantum", "syntax", "rhythm", "memory", "vector", "hyper", "turbo",
  "fusion", "laser", "portal", "cipher", "streak", "phantom", "blaze", "rally", "horizon", "zenith"
];

const LEADERBOARD_KEY = "arcadeLeaderboard";
const LEADERBOARD_API_PATH = "/api/leaderboard";
const LEADERBOARD_FALLBACK_ORIGIN = "https://www.yapvibes.com";
const SESSION_PLAYER_NAME_KEY = "arcadeSessionPlayerName";
const LEADERBOARD_LIMIT = 20;
const EASTER_EGG_SEQUENCE = "yapvibes";
const EASTER_EGG_TARGET = "/";
const EASTER_EGG_IDLE_RESET_MS = 1500;
const EASTER_EGG_LOCKOUT_MS = 500;

const elements = {
  sentenceDisplay: document.getElementById("sentence-display"),
  sessionPlayerNameInput: document.getElementById("session-player-name"),
  typingInput: document.getElementById("typing-input"),
  wpmResult: document.getElementById("wpm-result"),
  accuracyResult: document.getElementById("accuracy-result"),
  timeResult: document.getElementById("time-result"),
  sessionRounds: document.getElementById("session-rounds"),
  sessionTotalScore: document.getElementById("session-total-score"),
  sessionAvgWpm: document.getElementById("session-avg-wpm"),
  sessionAvgAccuracy: document.getElementById("session-avg-accuracy"),
  sessionBestWpm: document.getElementById("session-best-wpm"),
  sessionBestAccuracy: document.getElementById("session-best-accuracy"),
  roundHistoryList: document.getElementById("round-history-list"),
  resultsSection: document.getElementById("results"),
  scoreDisplay: document.getElementById("score-display"),
  latestScore: document.getElementById("latest-score"),
  playingAs: document.getElementById("playing-as"),
  leaderboardNameSection: document.getElementById("leaderboard-name-section"),
  leaderboardList: document.getElementById("leaderboard-list"),
  submitScoreBtn: document.getElementById("submit-score-btn"),
  nextRoundBtn: document.getElementById("next-round-btn"),
  resetLeaderboardBtn: document.getElementById("reset-leaderboard-btn")
};

let currentSentence = "";
let startTime = null;
let isRunning = false;
let isComplete = false;
let currentScore = 0;
let lastRoundWpm = 0;
let lastRoundAccuracy = 0;
let hasSubmittedScore = false;
let sentenceCharSpans = [];
let autoNextRoundTimer = null;
let promptQueue = [];
let cheatDetected = false;
let currentCharIndex = 0;
let totalKeypresses = 0;
let correctKeypresses = 0;

const PROMPT_QUEUE_SIZE = 8;

const sessionStats = {
  rounds: 0,
  totalScore: 0,
  totalWpm: 0,
  totalAccuracy: 0,
  bestWpm: 0,
  bestAccuracy: 0
};

const roundHistory = [];
const ROUND_HISTORY_LIMIT = 33;

function renderRoundHistoryCapacity(activeCount = 0) {
  const capacityEl = document.getElementById("round-history-capacity");
  if (!capacityEl) return;

  const fillRatio = ROUND_HISTORY_LIMIT > 0 ? activeCount / ROUND_HISTORY_LIMIT : 0;
  capacityEl.classList.remove("warn", "danger");
  if (fillRatio >= 0.9) {
    capacityEl.classList.add("danger");
  } else if (fillRatio >= 0.7) {
    capacityEl.classList.add("warn");
  }

  capacityEl.textContent = `${activeCount}/${ROUND_HISTORY_LIMIT}`;
}

function renderSessionStats() {
  if (!elements.sessionRounds) return;
  elements.sessionRounds.textContent = String(sessionStats.rounds);
  elements.sessionTotalScore.textContent = sessionStats.totalScore.toFixed(2);
  elements.sessionAvgWpm.textContent = (sessionStats.rounds ? sessionStats.totalWpm / sessionStats.rounds : 0).toFixed(2);
  elements.sessionAvgAccuracy.textContent = `${(sessionStats.rounds ? sessionStats.totalAccuracy / sessionStats.rounds : 0).toFixed(2)}%`;
  elements.sessionBestWpm.textContent = sessionStats.bestWpm.toFixed(2);
  elements.sessionBestAccuracy.textContent = `${sessionStats.bestAccuracy.toFixed(2)}%`;
}

function renderRoundHistory() {
  if (!elements.roundHistoryList) return;

  elements.roundHistoryList.innerHTML = "";

  renderRoundHistoryCapacity(roundHistory.length);

  if (roundHistory.length === 0) {
    const placeholder = document.createElement("li");
    placeholder.textContent = "---";
    elements.roundHistoryList.appendChild(placeholder);
    return;
  }

  roundHistory.forEach((entry) => {
    const li = document.createElement("li");
    li.textContent = `#${entry.round} | WPM ${entry.wpm.toFixed(2)} | ACC ${entry.accuracy.toFixed(2)}% | SCORE ${entry.score.toFixed(2)} | TIME ${entry.time.toFixed(2)}s`;
    elements.roundHistoryList.appendChild(li);
  });
}

function setSubmitState(canSubmit, message = "") {
  if (elements.submitScoreBtn) {
    elements.submitScoreBtn.disabled = !canSubmit;
  }

  let hint = document.getElementById("submit-hint");
  if (!hint) {
    hint = document.createElement("p");
    hint.id = "submit-hint";
    elements.resultsSection.appendChild(hint);
  }
  hint.textContent = message;
}

function markCheatDetected(reason = "Paste or multi-character insert detected.") {
  if (cheatDetected) return;

  cheatDetected = true;
  isRunning = false;
  currentScore = 0;
  lastRoundWpm = 0;
  lastRoundAccuracy = 0;

  elements.typingInput.disabled = true;
  setSubmitState(false, `${reason} Round invalid — press Next Round.`);

  if (elements.nextRoundBtn) {
    elements.nextRoundBtn.disabled = false;
  }
}

function handleInputManipulationAttempt(event) {
  event.preventDefault();
  if (!isComplete) {
    markCheatDetected(`${event.type.toUpperCase()} is disabled.`);
  }
}

function handlePromptCopyAttempt(event) {
  event.preventDefault();
}

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function shuffleArray(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function generateWordPrompt() {
  const count = randomInt(12, 18);

  const usedIndexes = new Set();
  const selected = [];
  while (selected.length < count && usedIndexes.size < wordBank.length) {
    const idx = Math.floor(Math.random() * wordBank.length);
    if (usedIndexes.has(idx)) continue;
    usedIndexes.add(idx);
    selected.push(wordBank[idx]);
  }

  return selected.join(" ");
}

function generateLetterPrompt() {
  const letters = "abcdefghijklmnopqrstuvwxyz";
  const groups = randomInt(8, 12);
  const groupLength = randomInt(3, 5);
  const chunks = [];

  for (let i = 0; i < groups; i += 1) {
    let chunk = "";
    for (let j = 0; j < groupLength; j += 1) {
      chunk += letters[Math.floor(Math.random() * letters.length)];
    }
    chunks.push(chunk);
  }

  return chunks.join(" ");
}

function getNextPrompt() {
  if (promptQueue.length === 0) {
    refillPromptQueue();
  }

  const next = promptQueue.shift();
  refillPromptQueue();
  return next;
}

function buildPrompt() {
  return Math.random() < 0.75 ? generateWordPrompt() : generateLetterPrompt();
}

function refillPromptQueue() {
  while (promptQueue.length < PROMPT_QUEUE_SIZE) {
    promptQueue.push(buildPrompt());
  }
}

function loadScores() {
  const raw = localStorage.getItem(LEADERBOARD_KEY);
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveScores(scores) {
  localStorage.setItem(LEADERBOARD_KEY, JSON.stringify(scores));
}

async function fetchScoresFromApi() {
  const endpoints = [
    LEADERBOARD_API_PATH,
    `${LEADERBOARD_FALLBACK_ORIGIN}${LEADERBOARD_API_PATH}`
  ];

  let lastError = null;

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { method: "GET" });
      if (!response.ok) throw new Error(`Failed to load global leaderboard (${response.status})`);
      const payload = await response.json();
      return Array.isArray(payload) ? normalizeAndRankScores(payload) : [];
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Failed to load global leaderboard");
}

async function submitScoreToApi(name, score, wpm, accuracy) {
  const endpoints = [
    LEADERBOARD_API_PATH,
    `${LEADERBOARD_FALLBACK_ORIGIN}${LEADERBOARD_API_PATH}`
  ];

  let lastError = null;

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, score, wpm, accuracy })
      });

      if (!response.ok) throw new Error(`Failed to submit score (${response.status})`);
      const payload = await response.json();
      return Array.isArray(payload) ? normalizeAndRankScores(payload) : [];
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Failed to submit score");
}

async function resetScoresInApi() {
  const endpoints = [
    LEADERBOARD_API_PATH,
    `${LEADERBOARD_FALLBACK_ORIGIN}${LEADERBOARD_API_PATH}`
  ];

  let lastError = null;

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { method: "DELETE" });
      if (!response.ok) throw new Error(`Failed to reset leaderboard (${response.status})`);
      return;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Failed to reset leaderboard");
}

function normalizeAndRankScores(scores) {
  const toFiniteNumber = (value, fallback = 0) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  };

  return scores
    .filter((entry) => entry && typeof entry.name === "string" && Number.isFinite(Number(entry.score)))
    .map((entry) => {
      const rounds = Math.max(1, Math.floor(toFiniteNumber(entry.rounds, 1)));
      const avgWpm = Math.max(0, toFiniteNumber(entry.avgWpm ?? entry.avg_wpm, 0));
      const avgAccuracy = Math.min(100, Math.max(0, toFiniteNumber(entry.avgAccuracy ?? entry.avg_accuracy, 0)));
      const totalWpm = Math.max(0, toFiniteNumber(entry.totalWpm, avgWpm * rounds));
      const totalAccuracy = Math.max(0, toFiniteNumber(entry.totalAccuracy, avgAccuracy * rounds));

      return {
        name: entry.name.trim() || "Anonymous",
        score: toFiniteNumber(entry.score, 0),
        rounds,
        totalWpm,
        totalAccuracy,
        avgWpm: totalWpm / rounds,
        avgAccuracy: Math.min(100, totalAccuracy / rounds)
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, LEADERBOARD_LIMIT);
}

function renderLeaderboard(scores) {
  elements.leaderboardList.innerHTML = "";

  const rankedScores = normalizeAndRankScores(scores);

  if (rankedScores.length === 0) {
    for (let i = 0; i < LEADERBOARD_LIMIT; i += 1) {
      const li = document.createElement("li");
      li.textContent = "---";
      elements.leaderboardList.appendChild(li);
    }
    return;
  }

  rankedScores.forEach((entry) => {
    const safeAvgWpm = Number.isFinite(entry.avgWpm) ? Math.max(0, entry.avgWpm) : 0;
    const safeAvgAccuracy = Number.isFinite(entry.avgAccuracy) ? Math.min(100, Math.max(0, entry.avgAccuracy)) : 0;
    const safeRounds = Number.isFinite(entry.rounds) ? Math.max(1, Math.floor(entry.rounds)) : 1;

    const li = document.createElement("li");
    li.textContent = `${entry.name} - ${entry.score.toFixed(2)} | Avg WPM ${safeAvgWpm.toFixed(2)} | Avg Acc ${safeAvgAccuracy.toFixed(2)}% | Rounds ${safeRounds}`;
    elements.leaderboardList.appendChild(li);
  });

  for (let i = rankedScores.length; i < LEADERBOARD_LIMIT; i += 1) {
    const li = document.createElement("li");
    li.textContent = "---";
    elements.leaderboardList.appendChild(li);
  }
}

function addScore(name, score, wpm, accuracy) {
  const leaderboardName = name.trim() || "Anonymous";
  const numericScore = Number.isFinite(Number(score)) ? Number(score) : 0;
  const numericWpm = Number.isFinite(Number(wpm)) ? Math.max(0, Number(wpm)) : 0;
  const numericAccuracy = Number.isFinite(Number(accuracy)) ? Math.min(100, Math.max(0, Number(accuracy))) : 0;

  const existingScores = loadScores();
  const existingEntry = existingScores.find((entry) => entry.name === leaderboardName);
  if (existingEntry) {
    const existingScore = Number.isFinite(Number(existingEntry.score)) ? Number(existingEntry.score) : 0;
    const existingRounds = Math.max(1, Math.floor(Number(existingEntry.rounds) || 1));
    const existingAvgWpm = Number.isFinite(Number(existingEntry.avgWpm)) ? Number(existingEntry.avgWpm) : 0;
    const existingAvgAccuracy = Number.isFinite(Number(existingEntry.avgAccuracy)) ? Number(existingEntry.avgAccuracy) : 0;
    const existingTotalWpm = Number.isFinite(Number(existingEntry.totalWpm)) ? Number(existingEntry.totalWpm) : existingAvgWpm * existingRounds;
    const existingTotalAccuracy = Number.isFinite(Number(existingEntry.totalAccuracy)) ? Number(existingEntry.totalAccuracy) : existingAvgAccuracy * existingRounds;

    existingEntry.score = existingScore + numericScore;
    existingEntry.rounds = existingRounds + 1;
    existingEntry.totalWpm = existingTotalWpm + numericWpm;
    existingEntry.totalAccuracy = existingTotalAccuracy + numericAccuracy;
    existingEntry.avgWpm = existingEntry.totalWpm / existingEntry.rounds;
    existingEntry.avgAccuracy = existingEntry.totalAccuracy / existingEntry.rounds;
  } else {
    existingScores.push({
      name: leaderboardName,
      score: numericScore,
      rounds: 1,
      totalWpm: numericWpm,
      totalAccuracy: numericAccuracy,
      avgWpm: numericWpm,
      avgAccuracy: numericAccuracy
    });
  }

  const rankedScores = normalizeAndRankScores(existingScores);
  saveScores(rankedScores);

  return rankedScores;
}

async function handleSubmitScore() {
  if (!isComplete || hasSubmittedScore || !Number.isFinite(currentScore) || currentScore <= 0) {
    setSubmitState(false, "Complete the prompt exactly to enable score submission.");
    return;
  }

  if (autoNextRoundTimer) {
    clearTimeout(autoNextRoundTimer);
    autoNextRoundTimer = null;
  }

  const playerName = getSubmissionName();

  try {
    const rankedScores = await submitScoreToApi(playerName, currentScore, lastRoundWpm, lastRoundAccuracy);
    saveScores(rankedScores);
    renderLeaderboard(rankedScores);
  } catch (error) {
    console.error("Global leaderboard submit failed; using local fallback.", error);
    const rankedScores = addScore(playerName, currentScore, lastRoundWpm, lastRoundAccuracy);
    renderLeaderboard(rankedScores);
  }

  hasSubmittedScore = true;
  setSubmitState(false, "Score submitted. Starting next round...");
  startNewRound();
}

async function handleNextRound() {
  if (isComplete && !hasSubmittedScore && Number.isFinite(currentScore) && currentScore > 0) {
    await handleSubmitScore();
    return;
  }

  startNewRound();
}

async function resetLeaderboard() {
  const shouldReset = window.confirm("Are you sure you want to reset the arcade leaderboard?");
  if (!shouldReset) return;

  try {
    await resetScoresInApi();
    localStorage.removeItem(LEADERBOARD_KEY);
    renderLeaderboard([]);
  } catch (error) {
    console.error("Global leaderboard reset failed; preserving current leaderboard.", error);
    setSubmitState(false, "Reset not authorized.");

    try {
      const globalScores = await fetchScoresFromApi();
      saveScores(globalScores);
      renderLeaderboard(globalScores);
    } catch {
      // Keep current view if refresh also fails.
    }
  }
}

function hidePostCompletionUi() {
  // Keep the most recent score visible between rounds for momentum.
  elements.leaderboardNameSection.classList.add("hidden");
}

function resetInputState() {
  elements.typingInput.value = "";
  elements.typingInput.disabled = !getSessionPlayerName();
  elements.typingInput.focus();
}

function resetRoundState() {
  startTime = null;
  isRunning = false;
  isComplete = false;
  currentScore = 0;
  lastRoundWpm = 0;
  lastRoundAccuracy = 0;
  hasSubmittedScore = false;
  cheatDetected = false;
  currentCharIndex = 0;
  totalKeypresses = 0;
  correctKeypresses = 0;

  if (autoNextRoundTimer) {
    clearTimeout(autoNextRoundTimer);
    autoNextRoundTimer = null;
  }
}

function startNewRound() {
  resetRoundState();
  hidePostCompletionUi();
  resetInputState();
  renderSentence();
  setSubmitState(false, "New round live. Finish the prompt, then submit to climb the leaderboard.");
}

function createSentenceSpans(sentence) {
  const fragment = document.createDocumentFragment();
  sentenceCharSpans = [];

  for (let i = 0; i < sentence.length; i += 1) {
    const span = document.createElement("span");
    span.textContent = sentence[i];
    sentenceCharSpans.push(span);
    fragment.appendChild(span);
  }

  elements.sentenceDisplay.innerHTML = "";
  elements.sentenceDisplay.appendChild(fragment);
}

function updateTypingFeedback(typedText) {
  for (let i = 0; i < sentenceCharSpans.length; i += 1) {
    const span = sentenceCharSpans[i];
    const expectedChar = currentSentence[i];
    const typedChar = typedText[i];

    span.classList.remove("correct", "incorrect");

    if (typedChar === undefined) continue;

    if (typedChar === expectedChar) {
      span.classList.add("correct");
    } else {
      span.classList.add("incorrect");
    }
  }
}

function renderSentence() {
  currentSentence = getNextPrompt();
  createSentenceSpans(currentSentence);
}

function getSubmissionName() {
  const sessionName = getSessionPlayerName();
  if (sessionName) return sessionName;

  return "Anonymous";
}

function setSessionPlayerName(name) {
  const safeName = (name || "").trim().slice(0, 20);
  if (!safeName) {
    sessionStorage.removeItem(SESSION_PLAYER_NAME_KEY);
    return;
  }
  sessionStorage.setItem(SESSION_PLAYER_NAME_KEY, safeName);
}

function getSessionPlayerName() {
  return (sessionStorage.getItem(SESSION_PLAYER_NAME_KEY) || "").trim();
}

function applySessionPlayerName(name) {
  if (!name) return;

  if (elements.sessionPlayerNameInput) {
    elements.sessionPlayerNameInput.value = name;
  }
  if (elements.playingAs) {
    elements.playingAs.textContent = `Playing as: ${name}`;
  }
  elements.typingInput.disabled = false;
}

function syncNameInputs(sourceInput, targetInput) {
  if (!sourceInput || !targetInput) return;
  targetInput.value = sourceInput.value;
}

function handleNameInputKeydown(event) {
  if (event.key !== "Enter") return;

  event.preventDefault();

  if (isComplete) {
    handleSubmitScore();
  }
}

function handleGlobalRetryShortcut(event) {
  if (!isComplete) return;

  if (event.key === "Escape") {
    event.preventDefault();
    startNewRound();
  }
}

function handleEasterEggShortcut(event) {
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.key.length !== 1) return;

  const now = Date.now();
  if (now < handleEasterEggShortcut.lockoutUntil) return;

  const typed = event.key.toLowerCase();
  if (!/[a-z]/.test(typed)) return;

  const nextSequence = `${handleEasterEggShortcut.buffer}${typed}`.slice(-EASTER_EGG_SEQUENCE.length);
  handleEasterEggShortcut.buffer = nextSequence;

  if (handleEasterEggShortcut.idleTimer) {
    clearTimeout(handleEasterEggShortcut.idleTimer);
  }
  handleEasterEggShortcut.idleTimer = setTimeout(() => {
    handleEasterEggShortcut.buffer = "";
    handleEasterEggShortcut.idleTimer = null;
  }, EASTER_EGG_IDLE_RESET_MS);

  if (nextSequence === EASTER_EGG_SEQUENCE) {
    handleEasterEggShortcut.lockoutUntil = now + EASTER_EGG_LOCKOUT_MS;
    handleEasterEggShortcut.buffer = "";
    if (handleEasterEggShortcut.idleTimer) {
      clearTimeout(handleEasterEggShortcut.idleTimer);
      handleEasterEggShortcut.idleTimer = null;
    }
    window.location.href = EASTER_EGG_TARGET;
  }
}

handleEasterEggShortcut.buffer = "";
handleEasterEggShortcut.idleTimer = null;
handleEasterEggShortcut.lockoutUntil = 0;

function getElapsedSeconds(startTimestamp) {
  return (Date.now() - startTimestamp) / 1000;
}

function calculateAccuracy(correctCount, totalCount) {
  if (totalCount <= 0) return 0;
  return (correctCount / totalCount) * 100;
}

function calculateWpm(originalText, elapsedSeconds) {
  if (elapsedSeconds <= 0) return 0;

  const wordsTyped = originalText.length / 5;
  const minutes = elapsedSeconds / 60;
  return wordsTyped / minutes;
}

function calculateScore(wpm, accuracy) {
  return wpm * (accuracy / 100) * 10;
}

function ensureSummaryRow() {
  let summaryRow = document.getElementById("result-summary");

  if (!summaryRow) {
    summaryRow = document.createElement("p");
    summaryRow.id = "result-summary";
    elements.resultsSection.appendChild(summaryRow);
  }

  return summaryRow;
}

function revealPostCompletionUi(score) {
  elements.latestScore.textContent = score.toFixed(2);
  elements.scoreDisplay.classList.remove("hidden");
  elements.leaderboardNameSection.classList.remove("hidden");
  if (elements.nextRoundBtn) {
    elements.nextRoundBtn.disabled = false;
  }
}

function completeRun() {
  if (isComplete) return;

  isComplete = true;
  isRunning = false;

  const elapsedSeconds = getElapsedSeconds(startTime);
  const wpm = calculateWpm(currentSentence, elapsedSeconds);
  const accuracy = calculateAccuracy(correctKeypresses, totalKeypresses);
  const score = calculateScore(wpm, accuracy);

  currentScore = score;
  lastRoundWpm = wpm;
  lastRoundAccuracy = accuracy;

  sessionStats.rounds += 1;
  sessionStats.totalScore += score;
  sessionStats.totalWpm += wpm;
  sessionStats.totalAccuracy += accuracy;
  sessionStats.bestWpm = Math.max(sessionStats.bestWpm, wpm);
  sessionStats.bestAccuracy = Math.max(sessionStats.bestAccuracy, accuracy);
  renderSessionStats();

  roundHistory.unshift({
    round: sessionStats.rounds,
    wpm,
    accuracy,
    score,
    time: elapsedSeconds
  });
  if (roundHistory.length > ROUND_HISTORY_LIMIT) {
    roundHistory.pop();
  }
  renderRoundHistory();

  elements.wpmResult.textContent = wpm.toFixed(2);
  elements.accuracyResult.textContent = `${accuracy.toFixed(2)}%`;
  elements.timeResult.textContent = `${elapsedSeconds.toFixed(2)}s`;

  const summaryRow = ensureSummaryRow();
  summaryRow.textContent = `WPM: ${wpm.toFixed(2)} | Accuracy: ${accuracy.toFixed(2)}% | Score: ${score.toFixed(2)}`;

  elements.typingInput.disabled = true;
  revealPostCompletionUi(score);
  setSubmitState(true, "Run complete! Enter your name and submit your score.");
}

function handleTypingInput(event) {
  if (isComplete || cheatDetected) return;

  const expectedValue = currentSentence.slice(0, currentCharIndex);
  if (event.target.value !== expectedValue) {
    markCheatDetected("Input injection detected.");
  }
}

function isTypingCharacterKey(event) {
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
}

function handleTypingKeydown(event) {
  if (isComplete || cheatDetected) {
    event.preventDefault();
    return;
  }

  if (event.key === "Backspace" || event.key === "Delete") {
    event.preventDefault();
    return;
  }

  if (!isTypingCharacterKey(event)) {
    return;
  }

  event.preventDefault();

  if (!isRunning) {
    isRunning = true;
    startTime = Date.now();
  }

  totalKeypresses += 1;

  const expectedChar = currentSentence[currentCharIndex];
  const typedChar = event.key;

  if (typedChar === expectedChar) {
    correctKeypresses += 1;
    currentCharIndex += 1;
    elements.typingInput.value = currentSentence.slice(0, currentCharIndex);
    updateTypingFeedback(currentSentence.slice(0, currentCharIndex));
  } else {
    elements.typingInput.value = currentSentence.slice(0, currentCharIndex);
    updateTypingFeedback(currentSentence.slice(0, currentCharIndex) + typedChar);
  }

  if (currentCharIndex >= currentSentence.length) {
    completeRun();
  }
}

async function initializeTypingGame() {
  const savedScores = loadScores();
  renderLeaderboard(savedScores);

  try {
    const globalScores = await fetchScoresFromApi();
    saveScores(globalScores);
    renderLeaderboard(globalScores);
  } catch (error) {
    console.error("Global leaderboard fetch failed; using local fallback.", error);
    // Keep local fallback when API is unavailable.
  }

  renderSentence();

  const existingSessionName = getSessionPlayerName();
  if (existingSessionName) {
    applySessionPlayerName(existingSessionName);
  } else {
    elements.typingInput.disabled = true;
  }

  elements.typingInput.addEventListener("input", handleTypingInput);
  elements.typingInput.addEventListener("keydown", handleTypingKeydown);
  elements.typingInput.addEventListener("paste", handleInputManipulationAttempt);
  elements.typingInput.addEventListener("drop", handleInputManipulationAttempt);
  elements.typingInput.addEventListener("cut", handleInputManipulationAttempt);

  if (elements.sentenceDisplay) {
    elements.sentenceDisplay.addEventListener("copy", handlePromptCopyAttempt);
    elements.sentenceDisplay.addEventListener("cut", handlePromptCopyAttempt);
  }

  elements.submitScoreBtn.addEventListener("click", handleSubmitScore);
  elements.nextRoundBtn.addEventListener("click", handleNextRound);
  elements.resetLeaderboardBtn.addEventListener("click", resetLeaderboard);

  if (elements.sessionPlayerNameInput) {
    elements.sessionPlayerNameInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const name = elements.sessionPlayerNameInput.value.trim();
      if (!name) return;
      setSessionPlayerName(name);
      applySessionPlayerName(name);
      elements.typingInput.focus();
    });
  }

  document.addEventListener("keydown", handleGlobalRetryShortcut);
  document.addEventListener("keydown", handleEasterEggShortcut);
  setSubmitState(false, "Complete the prompt exactly to enable score submission.");

  if (elements.playingAs && !existingSessionName) {
    elements.playingAs.textContent = "Playing as: --- (set Arcade Tag above)";
  }

  renderSessionStats();
  renderRoundHistory();
}

initializeTypingGame();