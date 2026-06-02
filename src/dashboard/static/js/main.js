/* ==========================================================================
   ElectroGadget Hub Autonomous Agent Dashboard Client Engine
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // --- Elements ---
    const navItems = document.querySelectorAll(".nav-item[data-tab]");
    const tabContents = document.querySelectorAll(".tab-content");
    
    const globalStatusDot = document.getElementById("global-status-dot");
    const globalStatusText = document.getElementById("global-status-text");
    const headerProjectName = document.getElementById("header-project-name");

    const statScore = document.getElementById("stat-score");
    const statScoreDelta = document.getElementById("stat-score-delta");
    const statVersion = document.getElementById("stat-version");
    const statOptimizations = document.getElementById("stat-optimizations");
    const statFailures = document.getElementById("stat-failures");
    const statFailuresBreakdown = document.getElementById("stat-failures-breakdown");
    const statMrBadge = document.getElementById("stat-mr-badge");
    const statMrLink = document.getElementById("stat-mr-link");

    const btnTriggerOptimization = document.getElementById("btn-trigger-optimization");
    const btnForceOptimization = document.getElementById("btn-force-optimization");
    const btnRefreshHistory = document.getElementById("btn-refresh-history");

    const progressContainer = document.getElementById("loop-progress-container");
    const progressStepText = document.getElementById("progress-step-text");
    const progressPercentText = document.getElementById("progress-percent-text");
    const progressBarFill = document.getElementById("progress-bar-fill");

    const terminalLogs = document.getElementById("terminal-logs");
    const terminalBody = document.querySelector(".terminal-body");
    const terminalBadgeRunning = document.getElementById("terminal-badge-running");

    const historyTableBody = document.querySelector("#history-table tbody");

    const pId = document.getElementById("prompt-id");
    const pVersion = document.getElementById("prompt-version");
    const pModel = document.getElementById("prompt-model");
    const pTemp = document.getElementById("prompt-temp");
    const pOptCount = document.getElementById("prompt-opt-count");
    const pOptimizedAt = document.getElementById("prompt-optimized-at");
    const pDesc = document.getElementById("prompt-desc");
    const pInstructions = document.getElementById("prompt-instructions");

    // --- Closed-Loop UI Elements ---
    const closedLoopCard = document.getElementById("closed-loop-card");
    const closedLoopStatus = document.getElementById("closed-loop-status");
    const mrDetailIid = document.getElementById("mr-detail-iid");
    const mrDetailState = document.getElementById("mr-detail-state");
    const mrDetailUrl = document.getElementById("mr-detail-url");
    const btnMergeMr = document.getElementById("btn-merge-mr");
    const mergeSpinner = document.getElementById("merge-spinner");
    const upliftBaseline = document.getElementById("uplift-baseline");
    const upliftOptimized = document.getElementById("uplift-optimized");
    const upliftBadgeContainer = document.getElementById("uplift-badge-container");
    const upliftResult = document.getElementById("uplift-result");

    let displayedLogLength = 0;
    let isPollingActive = true;

    // --- Tab Switching Logic ---
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            const targetTab = item.getAttribute("data-tab");
            
            // Check if it's an external link
            if (!targetTab) return;
            
            e.preventDefault();
            
            navItems.forEach(nav => nav.classList.remove("active"));
            item.classList.add("active");
            
            tabContents.forEach(content => {
                content.classList.remove("active");
                if (content.getAttribute("id") === `tab-${targetTab}`) {
                    content.classList.add("active");
                }
            });

            // Update main header title
            const headerTitleH2 = document.querySelector(".header-title h2");
            const headerTitleP = document.querySelector(".header-title p");
            if (targetTab === "dashboard") {
                headerTitleH2.textContent = "Control Center";
                headerTitleP.textContent = "Observe, analyze, and optimize LLM prompts programmatically";
            } else if (targetTab === "prompts") {
                headerTitleH2.textContent = "Prompts Configuration";
                headerTitleP.textContent = "Inspect active prompt instructions, parameters, and metadata";
            }
        });
    });

    // --- Format Date String Helper ---
    function formatDate(dateStr) {
        if (!dateStr || dateStr === "--") return "--";
        try {
            const date = new Date(dateStr);
            return date.toLocaleString();
        } catch (e) {
            return dateStr;
        }
    }

    // --- Status Bar Style Coordinator ---
    function updateStatusIndicator(status) {
        globalStatusDot.className = "pulse-dot";
        
        const isRunning = !["IDLE", "COMPLETED", "FAILED"].includes(status);
        
        btnTriggerOptimization.disabled = isRunning;
        btnForceOptimization.disabled = isRunning;

        if (status === "WAITING_FOR_MERGE") {
            globalStatusDot.classList.add("running");
            globalStatusText.textContent = "Waiting for Merge";
            terminalBadgeRunning.classList.remove("hide");
        } else if (status === "VERIFYING_PRODUCTION_UPLIFT") {
            globalStatusDot.classList.add("running");
            globalStatusText.textContent = "Verifying Uplift";
            terminalBadgeRunning.classList.remove("hide");
        } else if (isRunning) {
            globalStatusDot.classList.add("running");
            globalStatusText.textContent = `Running: ${status}`;
            terminalBadgeRunning.classList.remove("hide");
        } else if (status === "COMPLETED") {
            globalStatusDot.classList.add("completed");
            globalStatusText.textContent = "Agent Idle";
            terminalBadgeRunning.classList.add("hide");
        } else if (status === "FAILED") {
            globalStatusDot.classList.add("failed");
            globalStatusText.textContent = "Loop Failed!";
            terminalBadgeRunning.classList.add("hide");
        } else {
            globalStatusDot.classList.add("idle");
            globalStatusText.textContent = "Agent Idle";
            terminalBadgeRunning.classList.add("hide");
        }
    }

    // --- Progress Bar Style Coordinator ---
    function updateProgressBar(status) {
        const stages = {
            "IDLE": { percent: 0, text: "" },
            "STARTING": { percent: 5, text: "Starting autonomous cycle..." },
            "FETCHING_SPANS": { percent: 15, text: "[1/6] Scraping spans from Phoenix Cloud..." },
            "RUNNING_JUDGES": { percent: 35, text: "[2/6] Auditing correctness with LLM judges..." },
            "DIAGNOSING_FAILURES": { percent: 55, text: "[3/6] Compiling root-cause diagnostics..." },
            "OPTIMIZING_PROMPTS": { percent: 75, text: "[4/6] Generating prompt variants via Gemini..." },
            "SHADOW_EVALUATIONS": { percent: 90, text: "[5/6] Running shadow evaluations..." },
            "OPENING_MERGE_REQUEST": { percent: 95, text: "[6/6] Launching GitLab MR deployment..." },
            "WAITING_FOR_MERGE": { percent: 97, text: "Waiting for Merge Request approval & merge..." },
            "VERIFYING_PRODUCTION_UPLIFT": { percent: 99, text: "Merge approved! Verifying production correctness uplift..." },
            "COMPLETED": { percent: 100, text: "Autonomous loop completed successfully!" },
            "FAILED": { percent: 100, text: "Autonomous loop execution failed!" }
        };

        const stage = stages[status] || { percent: 0, text: "" };
        
        if (status === "IDLE") {
            progressContainer.classList.add("hide");
            progressBarFill.style.width = "0%";
        } else {
            progressContainer.classList.remove("hide");
            progressStepText.textContent = stage.text;
            progressPercentText.textContent = `${stage.percent}%`;
            progressBarFill.style.width = `${stage.percent}%`;

            if (status === "FAILED") {
                progressBarFill.style.background = "linear-gradient(90deg, var(--color-danger), #ff6b6b)";
                progressBarFill.style.boxShadow = "0 0 10px var(--color-danger)";
            } else {
                progressBarFill.style.background = "linear-gradient(90deg, var(--color-primary), var(--color-blue))";
                progressBarFill.style.boxShadow = "0 0 10px var(--color-primary)";
            }
        }
    }

    // --- Colorize Log Line Helper ---
    function colorizeLog(line) {
        const div = document.createElement("div");
        div.className = "terminal-line";
        div.textContent = line;

        if (line.includes("[SYSTEM]")) {
            div.classList.add("system");
        } else if (line.includes("[Step")) {
            div.classList.add("info");
        } else if (line.includes("✅")) {
            div.classList.add("success");
        } else if (line.includes("⚠️")) {
            div.classList.add("warning");
        } else if (line.includes("❌")) {
            div.classList.add("error");
        } else {
            div.classList.add("system");
        }
        return div;
    }

    // --- Stream Terminal Logs ---
    function updateTerminalLogs(logs) {
        if (logs.length === 0) {
            displayedLogLength = 0;
            terminalLogs.innerHTML = `<div class="terminal-line system">[SYSTEM] Console cleared. Standing by...</div>`;
            return;
        }

        if (logs.length !== displayedLogLength) {
            terminalLogs.innerHTML = "";
            logs.forEach(line => {
                terminalLogs.appendChild(colorizeLog(line));
            });
            displayedLogLength = logs.length;
            terminalBody.scrollTop = terminalBody.scrollHeight;
        }
    }

    // --- Render History Matrix Table ---
    function renderHistoryTable(history) {
        if (!history || history.length === 0) {
            historyTableBody.innerHTML = `
                <tr>
                    <td colspan="7" class="empty-state">No execution history available yet. Trigger an agent loop above!</td>
                </tr>`;
            return;
        }

        historyTableBody.innerHTML = "";
        history.forEach(run => {
            const tr = document.createElement("tr");

            // Timestamp
            const tdTime = document.createElement("td");
            tdTime.textContent = formatDate(run.timestamp);
            tr.appendChild(tdTime);

            // Project
            const tdProj = document.createElement("td");
            tdProj.textContent = run.project;
            tr.appendChild(tdProj);

            // Status Badge
            const tdStatus = document.createElement("td");
            const badge = document.createElement("span");
            if (run.status === "SUCCESS") {
                badge.className = "badge badge-success";
                badge.innerHTML = `<i class="fa-solid fa-circle-check"></i> Success`;
            } else {
                badge.className = "badge badge-failed";
                badge.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> Failed`;
            }
            tdStatus.appendChild(badge);
            tr.appendChild(tdStatus);

            // Baseline Accuracy
            const tdBase = document.createElement("td");
            tdBase.textContent = `${(run.initial_score * 100).toFixed(1)}%`;
            tr.appendChild(tdBase);

            // Optimized Accuracy
            const tdFinal = document.createElement("td");
            const finalScore = run.final_score * 100;
            const diff = finalScore - (run.initial_score * 100);
            
            if (diff > 0 && run.status === "SUCCESS") {
                tdFinal.innerHTML = `${finalScore.toFixed(1)}% <span class="score-increase">(+${diff.toFixed(1)}%)</span>`;
            } else if (diff < 0 && run.status === "SUCCESS") {
                tdFinal.innerHTML = `${finalScore.toFixed(1)}% <span class="score-decrease">(${diff.toFixed(1)}%)</span>`;
            } else {
                tdFinal.textContent = `${finalScore.toFixed(1)}%`;
            }
            tr.appendChild(tdFinal);

            // Strategy
            const tdStrategy = document.createElement("td");
            tdStrategy.textContent = run.winner_strategy || "baseline";
            tr.appendChild(tdStrategy);

            // Merge Request URL
            const tdMR = document.createElement("td");
            if (run.mr_url && run.mr_url !== "N/A") {
                const link = document.createElement("a");
                link.href = run.mr_url;
                link.target = "_blank";
                link.className = "mr-link";
                link.innerHTML = `<i class="fa-brands fa-gitlab"></i> View MR #${run.mr_url.split("/").pop()} <i class="fa-solid fa-up-right-from-square"></i>`;
                tdMR.appendChild(link);
            } else {
                tdMR.innerHTML = `<span class="badge badge-secondary">None</span>`;
            }
            tr.appendChild(tdMR);

            historyTableBody.appendChild(tr);
        });
    }

    // --- Render Prompts Config Panel ---
    function renderPromptsConfig(activePrompt) {
        if (!activePrompt || Object.keys(activePrompt).length === 0) {
            pInstructions.textContent = "No prompt instructions configuration loaded.";
            return;
        }

        pId.textContent = activePrompt.id || "customer_support";
        pVersion.textContent = `v${activePrompt.version || "1.0.0"}`;
        pModel.textContent = activePrompt.model || "gemini-2.5-flash";
        pTemp.textContent = activePrompt.parameters?.temperature ?? "0.3";
        
        const metadata = activePrompt.metadata || {};
        pOptCount.textContent = metadata.optimization_count ?? 0;
        pOptimizedAt.textContent = formatDate(metadata.optimized_at || metadata.created_at);
        pDesc.textContent = activePrompt.description || "ElectroGadget Hub customer support system prompt";

        // Display raw instructions
        pInstructions.textContent = activePrompt.system_instruction || "No instruction set.";
    }

    // --- Main Poll Status API ---
    async function fetchStatus() {
        if (!isPollingActive) return;

        try {
            const response = await fetch("/api/status");
            if (!response.ok) throw new Error("Network status response was not OK.");
            
            const data = await response.json();
            
            // 1. Sidebar status Text and Dot
            updateStatusIndicator(data.status);

            // 2. Progress Bar
            updateProgressBar(data.status);

            // 3. Live terminal console logs
            updateTerminalLogs(data.logs);

            // 4. Update Prompts configurations in real-time
            renderPromptsConfig(data.active_prompt);

            // 5. Update Overview Stat Cards
            if (data.active_prompt) {
                statVersion.textContent = `v${data.active_prompt.version}`;
                statOptimizations.textContent = `${data.active_prompt.metadata?.optimization_count || 0} Programmatic optimizations`;
            }

            const lastRun = data.last_run || {};
            
            // Correctness Card
            if (last_run_exists(lastRun)) {
                statScore.textContent = `${(lastRun.final_score * 100).toFixed(1)}%`;
                const initial = lastRun.initial_score * 100;
                const final = lastRun.final_score * 100;
                const diff = final - initial;
                if (diff > 0) {
                    statScoreDelta.innerHTML = `<span class="score-increase"><i class="fa-solid fa-arrow-trend-up"></i> +${diff.toFixed(1)}%</span> from baseline`;
                } else {
                    statScoreDelta.textContent = "Baseline correctness rate";
                }
            } else if (data.active_prompt) {
                // Default if no runs are recorded yet
                statScore.textContent = "90.0%"; // Baseline OTel seed accuracy
                statScoreDelta.textContent = "Initial simulation correctness";
            }

            // Failures Card
            if (last_run_exists(lastRun)) {
                statFailures.textContent = lastRun.failures_found ?? 0;
                const clusters = lastRun.diagnosed_clusters || [];
                if (clusters.length > 0) {
                    statFailuresBreakdown.textContent = `${clusters.length} failure clusters diagnosed`;
                } else {
                    statFailuresBreakdown.textContent = "System is performing within limits";
                }
            } else {
                statFailures.textContent = "1";
                statFailuresBreakdown.textContent = "Product recommendation limit truncations";
            }

            // GitLab MR Card
            if (lastRun.mr_url && lastRun.mr_url !== "N/A") {
                statMrBadge.textContent = `MR #${lastRun.mr_url.split("/").pop()}`;
                statMrLink.innerHTML = `<a href="${lastRun.mr_url}" target="_blank" class="mr-link">Inspect Merge Request <i class="fa-solid fa-arrow-up-right-from-square"></i></a>`;
            } else {
                statMrBadge.textContent = "Up to Date";
                statMrLink.textContent = "GitOps prompts configuration is active";
            }

            // --- Update Closed-Loop Verification Panel ---
            const activeMr = data.active_mr || {};
            
            if ((data.status === "WAITING_FOR_MERGE" || data.status === "VERIFYING_PRODUCTION_UPLIFT" || (lastRun && lastRun.status === "SUCCESS" && lastRun.mr_url && lastRun.mr_url !== "N/A")) && activeMr && activeMr.iid) {
                closedLoopCard.classList.remove("hide");
                
                if (data.status === "WAITING_FOR_MERGE") {
                    closedLoopStatus.textContent = "WAITING FOR MERGE";
                    closedLoopStatus.style.background = "rgba(168, 85, 247, 0.15)";
                    closedLoopStatus.style.color = "hsl(270, 95%, 75%)";
                    closedLoopStatus.style.borderColor = "rgba(168, 85, 247, 0.25)";
                    
                    mrDetailState.textContent = "Open (Waiting)";
                    mrDetailState.className = "detail-value text-gold";
                    btnMergeMr.disabled = false;
                    mergeSpinner.classList.add("hide");
                } else if (data.status === "VERIFYING_PRODUCTION_UPLIFT") {
                    closedLoopStatus.textContent = "VERIFYING UPLIFT";
                    closedLoopStatus.style.background = "rgba(234, 179, 8, 0.15)";
                    closedLoopStatus.style.color = "var(--color-gold)";
                    closedLoopStatus.style.borderColor = "rgba(234, 179, 8, 0.25)";
                    
                    mrDetailState.textContent = "Merged (Verifying)";
                    mrDetailState.className = "detail-value text-green";
                    btnMergeMr.disabled = true;
                    mergeSpinner.classList.remove("hide");
                } else {
                    closedLoopStatus.textContent = "UPLIFT VERIFIED";
                    closedLoopStatus.style.background = "rgba(0, 201, 87, 0.15)";
                    closedLoopStatus.style.color = "var(--color-emerald)";
                    closedLoopStatus.style.borderColor = "rgba(0, 201, 87, 0.25)";
                    
                    mrDetailState.textContent = "Merged (Complete)";
                    mrDetailState.className = "detail-value text-green";
                    btnMergeMr.disabled = true;
                    mergeSpinner.classList.add("hide");
                }
                
                mrDetailIid.textContent = `!${activeMr.iid}`;
                mrDetailUrl.href = activeMr.url;
                
                // Update uplift metrics
                if (lastRun && lastRun.mr_url && lastRun.mr_url !== "N/A") {
                    upliftBaseline.textContent = `${(lastRun.initial_score * 100).toFixed(1)}%`;
                    
                    if (lastRun.final_production_score) {
                        upliftOptimized.textContent = `${(lastRun.final_production_score * 100).toFixed(1)}%`;
                        const uplift = (lastRun.uplift || 0) * 100;
                        upliftResult.textContent = `Uplift: ${uplift >= 0 ? "+" : ""}${uplift.toFixed(1)}%`;
                        upliftBadgeContainer.classList.remove("hide");
                    } else {
                        upliftOptimized.textContent = "--%";
                        upliftBadgeContainer.classList.add("hide");
                    }
                } else {
                    upliftBaseline.textContent = "--%";
                    upliftOptimized.textContent = "--%";
                    upliftBadgeContainer.classList.add("hide");
                }
            } else if (lastRun && lastRun.mr_url && lastRun.mr_url !== "N/A" && lastRun.final_production_score) {
                // If the loop finished and we have a verified run in history, show the completed uplift metrics
                closedLoopCard.classList.remove("hide");
                closedLoopStatus.textContent = "UPLIFT VERIFIED";
                closedLoopStatus.style.background = "rgba(0, 201, 87, 0.15)";
                closedLoopStatus.style.color = "var(--color-emerald)";
                closedLoopStatus.style.borderColor = "rgba(0, 201, 87, 0.25)";
                
                mrDetailIid.textContent = `!${lastRun.mr_url.split("/").pop()}`;
                mrDetailUrl.href = lastRun.mr_url;
                mrDetailState.textContent = "Merged (Complete)";
                mrDetailState.className = "detail-value text-green";
                btnMergeMr.disabled = true;
                mergeSpinner.classList.add("hide");
                
                upliftBaseline.textContent = `${(lastRun.initial_score * 100).toFixed(1)}%`;
                upliftOptimized.textContent = `${(lastRun.final_production_score * 100).toFixed(1)}%`;
                const uplift = (lastRun.uplift || 0) * 100;
                upliftResult.textContent = `Uplift: ${uplift >= 0 ? "+" : ""}${uplift.toFixed(1)}%`;
                upliftBadgeContainer.classList.remove("hide");
            } else {
                closedLoopCard.classList.add("hide");
            }

            // 6. History Table
            renderHistoryTable(data.history);

        } catch (error) {
            console.error("Error polling orchestrator status:", error);
        }
    }

    function last_run_exists(lastRun) {
        return lastRun && Object.keys(lastRun).length > 0;
    }

    // --- Trigger Loop API Call Helper ---
    async function triggerAgentLoop(force = false) {
        // Optimistic disable buttons to prevent double-clicks
        btnTriggerOptimization.disabled = true;
        btnForceOptimization.disabled = true;

        try {
            const response = await fetch("/api/trigger", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ force_optimize: force })
            });

            if (!response.ok) throw new Error("Trigger request failed.");
            const data = await response.json();
            
            if (data.success) {
                // Fetch status immediately to transition status UI
                await fetchStatus();
            } else {
                alert(`⚠️ Trigger failed: ${data.message}`);
                btnTriggerOptimization.disabled = false;
                btnForceOptimization.disabled = false;
            }
        } catch (e) {
            console.error("Error triggering loop:", e);
            alert("❌ An error occurred while connecting to the agent loop API.");
            btnTriggerOptimization.disabled = false;
            btnForceOptimization.disabled = false;
        }
    }

    // --- Manual MR Merge Call ---
    async function mergeMR() {
        btnMergeMr.disabled = true;
        mergeSpinner.classList.remove("hide");
        
        try {
            const response = await fetch("/api/merge_mr", {
                method: "POST",
                headers: { "Content-Type": "application/json" }
            });
            if (!response.ok) throw new Error("Merge request failed.");
            
            const data = await response.json();
            if (data.success) {
                // Instantly query status to update UI
                await fetchStatus();
            } else {
                alert(`⚠️ Merge failed: ${data.message}`);
                btnMergeMr.disabled = false;
                mergeSpinner.classList.add("hide");
            }
        } catch (e) {
            console.error("Error merging MR:", e);
            alert("❌ An error occurred while programmatically merging the MR.");
            btnMergeMr.disabled = false;
            mergeSpinner.classList.add("hide");
        }
    }

    // --- Event Listeners ---
    btnTriggerOptimization.addEventListener("click", () => triggerAgentLoop(false));
    btnForceOptimization.addEventListener("click", () => triggerAgentLoop(true));
    btnMergeMr.addEventListener("click", mergeMR);
    btnRefreshHistory.addEventListener("click", () => {
        fetchStatus();
    });

    // --- Initialize & Begin Polling ---
    fetchStatus();
    const statusPoller = setInterval(fetchStatus, 2000);

    // Clean up interval on page unload
    window.addEventListener("beforeunload", () => {
        isPollingActive = false;
        clearInterval(statusPoller);
    });
});
