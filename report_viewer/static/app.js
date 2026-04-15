document.addEventListener("DOMContentLoaded", () => {

    // ─── DOM refs ────────────────────────────────────────────────────
    const reportBody       = document.getElementById("report-body");
    const reportTitle      = document.getElementById("report-title");
    const referencePanel   = document.getElementById("reference-panel");
    const closePanelBtn    = document.getElementById("close-panel");
    const referenceContent = document.getElementById("reference-content");
    const referenceIframe  = document.getElementById("reference-iframe");
    const iframeLoader     = document.getElementById("iframe-loader");

    const btnGenerate        = document.getElementById("btn-generate");
    const btnGenerateText    = btnGenerate.querySelector(".btn-text");
    const btnGenerateSpinner = btnGenerate.querySelector(".btn-spinner");
    const genProgress        = document.getElementById("generation-progress");
    const termLogs           = document.getElementById("terminal-logs");
    const progressBarFill    = document.getElementById("progress-bar-fill");

    const btnNewChat       = document.getElementById("btn-new-chat");
    const chatView         = document.getElementById("chat-view");
    const chatMessages     = document.getElementById("chat-messages");
    const chatInputMain    = document.getElementById("chat-input-main");
    const chatSendMain     = document.getElementById("chat-send-main");
    const chatSendText     = document.getElementById("chat-send-text");
    const chatSendSpinner  = document.getElementById("chat-send-spinner");

    const sectionReports  = document.getElementById("section-reports");
    const sectionChats    = document.getElementById("section-chats");
    const toggleReports   = document.getElementById("toggle-reports");
    const toggleChats     = document.getElementById("toggle-chats");
    const arrowReports    = document.getElementById("arrow-reports");
    const arrowChats      = document.getElementById("arrow-chats");

    // ─── State ───────────────────────────────────────────────────────
    let currentReferences = {};
    let currentChatId     = null;
    let currentMode       = "report"; // "report" | "chat"

    // ─── Init ────────────────────────────────────────────────────────
    fetchReports();
    fetchChats();
    setupTreeToggles();

    // ─── View switchers ──────────────────────────────────────────────
    function showReportView() {
        currentMode = "report";
        reportBody.classList.remove("hidden");
        chatView.classList.add("hidden");
        genProgress.classList.add("hidden");
    }

    function showChatView() {
        currentMode = "chat";
        reportBody.classList.add("hidden");
        chatView.classList.remove("hidden");
        genProgress.classList.add("hidden");
    }

    // ─── Tree Sidebar Toggles ────────────────────────────────────────
    function setupTreeToggles() {
        toggleReports.addEventListener("click", () => {
            const collapsed = sectionReports.classList.toggle("collapsed");
            arrowReports.classList.toggle("collapsed", collapsed);
        });
        toggleChats.addEventListener("click", () => {
            const collapsed = sectionChats.classList.toggle("collapsed");
            arrowChats.classList.toggle("collapsed", collapsed);
        });
    }

    function selectItem(el) {
        document.querySelectorAll(".report-item.active").forEach(e => e.classList.remove("active"));
        el.classList.add("active");
    }

    // ─── Reference Panel ─────────────────────────────────────────────
    closePanelBtn.addEventListener("click", () => {
        referencePanel.classList.add("hidden");
        document.querySelectorAll(".interactive-sentence.active").forEach(e => e.classList.remove("active"));
        referenceIframe.src = "";
    });

    // ─── Reports ─────────────────────────────────────────────────────
    async function fetchReports() {
        try {
            const res  = await fetch("/api/reports");
            const data = await res.json();
            sectionReports.innerHTML = "";

            if (data.reports.length === 0) {
                sectionReports.innerHTML = "<p class='sidebar-empty'>생성된 보고서가 없습니다.</p>";
                return;
            }

            data.reports.forEach((report, index) => {
                const item = document.createElement("div");
                item.className = "report-item";

                let dateStr = "Unknown Date";
                const match = report.filename.match(/_(\d{8})/);
                if (match) {
                    const d = match[1];
                    dateStr = `${d.substring(0,4)}.${d.substring(4,6)}.${d.substring(6,8)}`;
                }

                item.innerHTML = `
                    <div class="report-item-title">${dateStr} Briefing</div>
                    <div class="report-item-date">${report.filename}</div>
                `;
                item.addEventListener("click", () => {
                    selectItem(item);
                    loadReport(report.filename);
                });
                sectionReports.appendChild(item);

                if (index === 0) {
                    item.classList.add("active");
                    loadReport(report.filename);
                }
            });
        } catch (err) {
            console.error(err);
            sectionReports.innerHTML = "<p class='sidebar-empty'>보고서 로드 실패.</p>";
        }
    }

    async function loadReport(filename) {
        showReportView();
        reportBody.innerHTML = `<div class="loader-pulse"></div>`;
        reportTitle.textContent = "Loading...";
        try {
            const res  = await fetch(`/api/reports/${filename}`);
            const data = await res.json();
            reportTitle.textContent = filename;
            parseAndRenderReport(data.content);
        } catch (err) {
            console.error(err);
            reportBody.innerHTML = `<p>Error loading report content.</p>`;
        }
    }

    function parseAndRenderReport(text) {
        currentReferences = {};
        const refLines = text.match(/\|\s*\[(\d+)\]\s*\|.*\|/g);
        if (refLines) {
            refLines.forEach(line => {
                const cols = line.split("|").map(s => s.trim()).filter(s => s.length > 0);
                if (cols.length >= 4) {
                    const numMatch = cols[0].match(/\[(\d+)\]/);
                    if (numMatch) {
                        const num = numMatch[1];
                        const urlMatch = line.match(/(https?:\/\/[^\s|]+)/);
                        currentReferences[num] = {
                            num, source: cols[1], title: cols[2], time: cols[3],
                            url: urlMatch ? urlMatch[1] : ""
                        };
                    }
                }
            });
        }

        let htmlBody = text
            .replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/^###\s+(.*$)/gm, '<h4>$1</h4>\n\n')
            .replace(/^##\s+(.*$)/gm, '<h3>$1</h3>\n\n')
            .replace(/^#\s+(.*$)/gm, '<h2>$1</h2>\n\n')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/={10,}/g, '<hr>\n\n')
            .replace(/-{10,}/g, '<hr>\n\n');

        const blocks = htmlBody.split(/\n\s*\n/).filter(b => b.trim().length > 0);
        htmlBody = blocks.map(block => {
            if (block.trim().startsWith('<h') || block.trim().startsWith('<hr')) return block;
            if (block.startsWith('|')) {
                const rows = block.split('\n').filter(r => r.trim());
                let tableHtml = '<table style="width:100%;border-collapse:collapse;margin-top:20px;font-size:0.9rem;">';
                rows.forEach((row, ri) => {
                    if (row.includes('---')) return;
                    const tag = ri === 0 ? 'th' : 'td';
                    const cells = row.split('|').map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length - 1);
                    tableHtml += '<tr>' + cells.map(c => `<${tag} style="border:1px solid #334155;padding:8px;">${c}</${tag}>`).join('') + '</tr>';
                });
                return tableHtml + '</table>';
            }
            if (block.startsWith('- ')) {
                return '<ul>' + block.split('\n').map(l => {
                    const t = wrapSentencesWithReferences(l.replace(/^- /, ''));
                    return `<li style="margin-bottom:10px;">${t}</li>`;
                }).join('') + '</ul>';
            }
            return `<p>${wrapSentencesWithReferences(block)}</p>`;
        }).join('');

        reportBody.innerHTML = htmlBody;
        attachSentenceListeners(reportBody);
    }

    function wrapSentencesWithReferences(text) {
        let result = "";
        const sentences = text.split(/(?<=\.\s|\]\.\s|\n)/);
        sentences.forEach(sentence => {
            const citationMatch = sentence.match(/\[(\d+)\]/g);
            if (citationMatch) {
                const nums = citationMatch.map(s => s.replace(/[\[\]]/g, ''));
                let formatted = sentence.replace(/\[\d+\]/g, m => `<span class="ref-tag">${m}</span>`);
                result += `<span class="interactive-sentence" data-refs="${nums.join(',')}">${formatted}</span>`;
            } else {
                result += sentence;
            }
        });
        return result;
    }

    function attachSentenceListeners(container) {
        container.querySelectorAll(".interactive-sentence").forEach(el => {
            el.addEventListener("click", function () {
                const isActive = this.classList.contains("active");
                document.querySelectorAll(".interactive-sentence.active").forEach(e => e.classList.remove("active"));
                if (!isActive) {
                    this.classList.add("active");
                    openReferencePanel(this.getAttribute("data-refs").split(","));
                } else {
                    referencePanel.classList.add("hidden");
                }
            });
        });
    }

    function openReferencePanel(refNums) {
        referenceContent.innerHTML = "";
        let firstUrl = "";
        refNums.forEach(num => {
            const ref = currentReferences[num.trim()];
            if (ref) {
                const card = document.createElement("div");
                card.className = "ref-card";
                card.innerHTML = `
                    <div class="source">[${ref.num}] ${ref.source}</div>
                    <h4>${ref.title}</h4>
                    <div class="time">수집: ${ref.time}</div>
                    ${ref.url ? `<a href="${ref.url}" target="_blank" class="ref-link-btn">Open in New Tab</a>` : ''}
                `;
                referenceContent.appendChild(card);
                if (ref.url && !firstUrl) firstUrl = ref.url;
            }
        });
        if (refNums.length > 0) {
            referencePanel.classList.remove("hidden");
            if (firstUrl) {
                referenceIframe.style.display = "block";
                iframeLoader.classList.remove("hidden");
                referenceIframe.onload = () => iframeLoader.classList.add("hidden");
                referenceIframe.src = firstUrl;
            } else {
                referenceIframe.style.display = "none";
                referenceIframe.src = "";
            }
        }
    }

    // ─── Generate Report (Streaming) ─────────────────────────────────
    btnGenerate.addEventListener("click", async () => {
        btnGenerate.disabled = true;
        btnGenerateText.style.display = "none";
        btnGenerateSpinner.classList.remove("hidden");

        showReportView();
        reportBody.classList.add("hidden");
        reportTitle.textContent = "Live Analysis in Progress...";
        genProgress.classList.remove("hidden");
        termLogs.innerHTML = "";
        progressBarFill.style.width = "0%";

        const streamOutput = document.createElement("pre");
        streamOutput.style.cssText = "white-space:pre-wrap;margin:0;font-family:monospace;line-height:1.5;";
        termLogs.appendChild(streamOutput);

        try {
            const res = await fetch("/api/generate_stream", { method: "POST" });
            progressBarFill.style.width = "30%";
            const reader  = res.body.getReader();
            const decoder = new TextDecoder("utf-8");
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                streamOutput.textContent += decoder.decode(value, { stream: true });
                termLogs.scrollTop = termLogs.scrollHeight;
                const w = parseFloat(progressBarFill.style.width) || 30;
                if (w < 95) progressBarFill.style.width = (w + 0.5) + "%";
            }
            progressBarFill.style.width = "100%";
            streamOutput.textContent += "\n[✔] DAILY BRIEFING GENERATED SUCCESSFULLY.";
            await new Promise(r => setTimeout(r, 800));
            await fetchReports();
        } catch (err) {
            console.error(err);
            streamOutput.textContent += "\n[X] SYSTEM ERROR: CONNECTION SEVERED.";
            progressBarFill.style.background = "red";
        } finally {
            btnGenerate.disabled = false;
            btnGenerateText.style.display = "inline-block";
            btnGenerateSpinner.classList.add("hidden");
            setTimeout(() => {
                genProgress.classList.add("hidden");
                reportBody.classList.remove("hidden");
            }, 400);
        }
    });

    // ─── Chat Sessions ────────────────────────────────────────────────
    async function fetchChats() {
        try {
            const res  = await fetch("/api/chats");
            const data = await res.json();
            sectionChats.innerHTML = "";
            if (data.sessions.length === 0) {
                sectionChats.innerHTML = "<p class='sidebar-empty'>채팅 이력이 없습니다.</p>";
                return;
            }
            data.sessions.forEach(s => sectionChats.appendChild(buildChatItem(s)));
        } catch (err) {
            console.error(err);
        }
    }

    function buildChatItem(session) {
        const item = document.createElement("div");
        item.className = "report-item";
        item.dataset.chatId = session.id;
        const date = (session.created_at || "").substring(0, 10);
        item.innerHTML = `
            <div class="report-item-title">${escHtml(session.title)}</div>
            <div class="report-item-date">${date}</div>
        `;
        item.addEventListener("click", () => {
            selectItem(item);
            loadChat(session.id);
        });
        return item;
    }

    async function loadChat(sessionId) {
        showChatView();
        currentChatId = sessionId;
        chatMessages.innerHTML = `<div class="loader-pulse"></div>`;
        reportTitle.textContent = "Loading...";
        try {
            const res     = await fetch(`/api/chats/${sessionId}`);
            const session = await res.json();
            reportTitle.textContent = session.title;
            chatMessages.innerHTML = "";
            session.display_messages.forEach(msg => appendChatMsg(msg.role, msg.content));
        } catch (err) {
            console.error(err);
        }
    }

    // + New Chat button
    btnNewChat.addEventListener("click", async () => {
        try {
            const res     = await fetch("/api/chats", { method: "POST" });
            const session = await res.json();
            currentChatId = session.id;

            // Remove placeholder if exists
            const placeholder = sectionChats.querySelector(".sidebar-empty");
            if (placeholder) placeholder.remove();

            const item = buildChatItem(session);
            sectionChats.insertBefore(item, sectionChats.firstChild);
            selectItem(item);

            // Expand chats section
            sectionChats.classList.remove("collapsed");
            arrowChats.classList.remove("collapsed");

            reportTitle.textContent = "새 채팅";
            chatMessages.innerHTML = "";
            appendChatMsg("system-msg", "새로운 분석 세션이 시작되었습니다.<br><span style='font-size:0.82rem;opacity:0.7;'>내부 DB + 실시간 웹 검색이 자동으로 수행됩니다.</span>");
            showChatView();
            chatInputMain.focus();
        } catch (err) {
            console.error(err);
            alert("채팅 세션 생성에 실패했습니다.");
        }
    });

    // Send message
    chatSendMain.addEventListener("click", sendMessage);
    chatInputMain.addEventListener("keydown", e => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });

    async function sendMessage() {
        if (!currentChatId) return;
        const text = chatInputMain.value.trim();
        if (!text) return;

        chatInputMain.value = "";
        chatSendMain.disabled = true;
        chatSendText.style.display = "none";
        chatSendSpinner.classList.remove("hidden");

        appendChatMsg("user", escHtml(text));
        const thinkingEl = appendChatMsg("assistant thinking", "🧠 분석 중...");

        try {
            const res = await fetch(`/api/chats/${currentChatId}/message`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text })
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Server error");
            }
            const data = await res.json();
            thinkingEl.remove();
            appendChatMsg("assistant", data.reply);

            // Update title
            if (data.title && data.title !== "새 채팅") {
                reportTitle.textContent = data.title;
                const sidebarItem = sectionChats.querySelector(`[data-chat-id="${currentChatId}"] .report-item-title`);
                if (sidebarItem) sidebarItem.textContent = data.title;
            }
        } catch (err) {
            thinkingEl.remove();
            appendChatMsg("assistant", `[오류] ${escHtml(err.message)}`);
        } finally {
            chatSendMain.disabled = false;
            chatSendText.style.display = "inline";
            chatSendSpinner.classList.add("hidden");
        }
    }

    function appendChatMsg(role, content) {
        const div = document.createElement("div");
        div.className = `chat-msg ${role}`;
        const safeContent = (content == null) ? "[응답 없음]" : String(content);
        if (role === "assistant" || role.startsWith("assistant")) {
            let formatted = safeContent
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/\n/g, '<br>');
            formatted = wrapSentencesWithReferences(formatted);
            div.innerHTML = formatted;
            attachSentenceListeners(div);
        } else {
            div.innerHTML = safeContent;
        }
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return div;
    }

    function escHtml(str) {
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ─── Schedule Modal ───────────────────────────────────────────────
    const scheduleModal    = document.getElementById("schedule-modal");
    const btnSettings      = document.getElementById("btn-settings");
    const btnScheduleCancel = document.getElementById("btn-schedule-cancel");
    const btnScheduleSave  = document.getElementById("btn-schedule-save");
    const timeInput        = document.getElementById("schedule-time");

    async function loadSchedule() {
        try {
            const res = await fetch("/api/schedule");
            if (res.ok) {
                const data = await res.json();
                timeInput.value = data.time || "09:00";
            }
        } catch (e) { console.error(e); }
    }

    if (btnSettings) {
        btnSettings.addEventListener("click", () => {
            scheduleModal.classList.remove("hidden");
            loadSchedule();
        });
        btnScheduleCancel.addEventListener("click", () => scheduleModal.classList.add("hidden"));
        btnScheduleSave.addEventListener("click", async () => {
            const timeVal = timeInput.value;
            if (!timeVal) return;
            btnScheduleSave.textContent = "Saving...";
            try {
                const res = await fetch("/api/schedule", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ time: timeVal })
                });
                if (res.ok) {
                    alert(`스케줄이 매일 ${timeVal}로 저장되었습니다!`);
                    scheduleModal.classList.add("hidden");
                } else {
                    alert("설정 저장에 실패했습니다.");
                }
            } catch (e) {
                alert("서버와 통신할 수 없습니다.");
            } finally {
                btnScheduleSave.textContent = "Save Schedule";
            }
        });
    }
});
