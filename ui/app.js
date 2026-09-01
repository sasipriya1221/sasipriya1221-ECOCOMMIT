const modeBanner = document.querySelector("#mode-banner");
const commitReady = document.querySelector("#commit-ready");
const providerStatus = document.querySelector("#provider-status");
const integrationStatus = document.querySelector("#integration-status");
const realMoneyStatus = document.querySelector("#real-money-status");
const lastUpdated = document.querySelector("#last-updated");
const simulationForm = document.querySelector("#simulation-form");
const simulationScenario = document.querySelector("#simulation-scenario");
const simulationResult = document.querySelector("#simulation-result");
const workflowOutcome = document.querySelector("#workflow-outcome");
const requestedExposure = document.querySelector("#requested-exposure");
const authorizedExposure = document.querySelector("#authorized-exposure");
const capturedExposure = document.querySelector("#captured-exposure");
const finalState = document.querySelector("#final-state");
const stateTrace = document.querySelector("#state-trace");
const workflowAlert = document.querySelector("#workflow-alert");

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

function clearGateCards(message) {
  for (const checkpoint of ["A", "B", "C", "D", "E"]) {
    const card = document.querySelector(`[data-checkpoint="${checkpoint}"]`);
    card.dataset.state = "UNAVAILABLE";
    card.dataset.accepted = "false";
    card.querySelector("strong").textContent = "UNAVAILABLE";
    card.querySelector("small").textContent = message;
  }
}

function renderStatus(status) {
  setMode(status.mode);
  commitReady.textContent = status.irreversible_commit_ready ? "READY (TEST MODE ONLY)" : "BLOCKED";
  providerStatus.textContent = status.provider?.status || "NOT REPORTED";
  integrationStatus.textContent = status.final_integration_verified ? "VERIFIED" : "NOT VERIFIED";
  realMoneyStatus.textContent = "DISABLED (OUT OF SCOPE)";

  for (const checkpoint of ["A", "B", "C", "D", "E"]) {
    const card = document.querySelector(`[data-checkpoint="${checkpoint}"]`);
    const report = status.checkpoint_gates?.[checkpoint];
    if (!report) {
      card.dataset.state = "UNAVAILABLE";
      card.dataset.accepted = "false";
      card.querySelector("strong").textContent = "UNAVAILABLE";
      card.querySelector("small").textContent = "No authoritative status supplied";
      continue;
    }
    card.dataset.state = report.state;
    card.dataset.accepted = String(report.accepted === true);
    card.querySelector("strong").textContent = report.state;
    card.querySelector("small").textContent = report.evidence || "No passing evidence recorded";
  }
  lastUpdated.textContent = `Status received ${new Date().toLocaleTimeString()}`;
}

function renderStatusUnavailable() {
  setMode(undefined);
  commitReady.textContent = "BLOCKED — STATUS UNAVAILABLE";
  providerStatus.textContent = "UNAVAILABLE";
  integrationStatus.textContent = "NOT VERIFIED";
  realMoneyStatus.textContent = "DISABLED (OUT OF SCOPE)";
  clearGateCards("Status API unavailable; no acceptance inferred");
  lastUpdated.textContent = "Status API unavailable; no acceptance inferred";
}

function formatMinor(value, currency) {
  if (!Number.isInteger(value)) return "—";
  return `${currency || ""} ${(value / 100).toFixed(2)}`.trim();
}

function renderWorkflow(workflow, correlationId) {
  const economic = workflow.economic_state || {};
  workflowOutcome.textContent = workflow.outcome || "UNKNOWN OUTCOME";
  workflowOutcome.dataset.outcome = workflow.outcome || "UNKNOWN";
  requestedExposure.textContent = formatMinor(economic.requested_minor, economic.currency);
  authorizedExposure.textContent = formatMinor(economic.authorized_irreversible_minor, economic.currency);
  capturedExposure.textContent = formatMinor(economic.captured_minor, economic.currency);
  finalState.textContent = workflow.final_commitment_stage || "UNKNOWN";

  stateTrace.replaceChildren();
  for (const item of workflow.state_trace || []) {
    const row = document.createElement("li");
    const stage = document.createElement("strong");
    const detail = document.createElement("span");
    stage.textContent = item.stage || "UNKNOWN";
    detail.textContent = item.detail || "No detail supplied";
    row.dataset.reversible = String(item.reversible === true);
    row.append(stage, detail);
    stateTrace.append(row);
  }

  const needsAttention = workflow.outcome !== "SIMULATED_CAPTURED";
  workflowAlert.hidden = !needsAttention;
  workflowAlert.textContent = needsAttention
    ? `${workflow.outcome}: ${(workflow.a_to_b?.blockers || []).join(", ") || workflow.failure_code || "workflow stopped safely"}. Correlation ${correlationId}.`
    : "";
}

function safeSimulationError(error) {
  const message = error instanceof SyntaxError
    ? "Service returned an unreadable response"
    : (error?.message || "Service request failed");
  return message.toLowerCase().includes("correlation")
    ? message
    : `${message} (correlation unavailable)`;
}

async function loadStatus() {
  try {
    const response = await fetch("/v1/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`Status API returned ${response.status}`);
    renderStatus(await response.json());
  } catch (error) {
    renderStatusUnavailable();
  }
}

simulationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = simulationForm.querySelector("button");
  button.disabled = true;
  simulationResult.textContent = "Running synthetic workflow…";
  workflowAlert.hidden = true;
  try {
    const response = await fetch("/v1/commit/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario: simulationScenario.value }),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(`${result.reason || "SIMULATION_REJECTED"} (correlation ${result.correlation_id || "unavailable"})`);
    }
    renderWorkflow(result.workflow, result.correlation_id);
    simulationResult.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    const safeError = safeSimulationError(error);
    workflowOutcome.textContent = "SIMULATION NOT COMPLETED";
    workflowOutcome.dataset.outcome = "ERROR";
    finalState.textContent = "BLOCKED";
    workflowAlert.hidden = false;
    workflowAlert.textContent = `Simulation stopped safely: ${safeError}`;
    simulationResult.textContent = `Simulation not completed: ${safeError}`;
  } finally {
    button.disabled = false;
  }
});

loadStatus();
