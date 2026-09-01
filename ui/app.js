const modeBanner = document.querySelector("#mode-banner");
const commitReady = document.querySelector("#commit-ready");
const providerStatus = document.querySelector("#provider-status");
const integrationStatus = document.querySelector("#integration-status");
const lastUpdated = document.querySelector("#last-updated");
const simulationForm = document.querySelector("#simulation-form");
const simulationPayload = document.querySelector("#simulation-payload");
const simulationResult = document.querySelector("#simulation-result");

function setMode(mode) {
  if (mode === "SIMULATED") {
    document.body.dataset.mode = "simulation";
    modeBanner.textContent = "SIMULATION MODE — NO PROVIDER CALLS · NO MONEY MOVEMENT";
    return;
  }
  if (mode === "REAL_PROVIDER_TEST") {
    document.body.dataset.mode = "real-test";
    modeBanner.textContent = "REAL INTEGRATION TEST MODE — RAZORPAY TEST MODE ONLY · NO REAL MONEY";
    return;
  }
  document.body.dataset.mode = "unverified";
  modeBanner.textContent = "MODE UNVERIFIED — EXECUTION DISABLED";
}

function renderStatus(status) {
  setMode(status.mode);
  commitReady.textContent = status.irreversible_commit_ready ? "READY (TEST MODE ONLY)" : "BLOCKED";
  providerStatus.textContent = status.provider?.status || "NOT REPORTED";
  integrationStatus.textContent = status.final_integration_verified ? "VERIFIED" : "NOT VERIFIED";

  for (const checkpoint of ["A", "B", "C", "D", "E"]) {
    const card = document.querySelector(`[data-checkpoint="${checkpoint}"]`);
    const report = status.checkpoint_gates?.[checkpoint];
    if (!report) continue;
    card.dataset.state = report.state;
    card.dataset.accepted = String(report.accepted === true);
    card.querySelector("strong").textContent = report.state;
    card.querySelector("small").textContent = report.evidence || "No passing evidence recorded";
  }
  lastUpdated.textContent = `Status received ${new Date().toLocaleTimeString()}`;
}

async function loadStatus() {
  try {
    const response = await fetch("/v1/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`Status API returned ${response.status}`);
    renderStatus(await response.json());
  } catch (error) {
    setMode(undefined);
    commitReady.textContent = "BLOCKED — STATUS UNAVAILABLE";
    providerStatus.textContent = "UNAVAILABLE";
    integrationStatus.textContent = "NOT VERIFIED";
    lastUpdated.textContent = "Status API unavailable; no acceptance inferred";
  }
}

simulationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = simulationForm.querySelector("button");
  button.disabled = true;
  simulationResult.textContent = "Submitting to simulation-only endpoint…";
  try {
    const parsed = JSON.parse(simulationPayload.value);
    const response = await fetch("/v1/commit/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed),
    });
    const result = await response.json();
    simulationResult.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    simulationResult.textContent = `Simulation not run: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

loadStatus();
