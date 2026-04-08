document.addEventListener("DOMContentLoaded", () => {
    const reportListContainer = document.getElementById("report-list");
    const reportBody = document.getElementById("report-body");
    const reportTitle = document.getElementById("report-title");
    const referencePanel = document.getElementById("reference-panel");
    const closePanelBtn = document.getElementById("close-panel");
    const referenceContent = document.getElementById("reference-content");
    const referenceIframe = document.getElementById("reference-iframe");
    const iframeLoader = document.getElementById("iframe-loader");

    const btnGenerate = document.getElementById("btn-generate");
    const btnGenerateText = btnGenerate.querySelector(".btn-text");
    const btnGenerateSpinner = btnGenerate.querySelector(".btn-spinner");
    
    const chatWidget = document.getElementById("chat-widget");
    const chatHeaderToggle = document.getElementById("chat-header-toggle");
    const chatBody = document.getElementById("chat-body");
    const chatInput = document.getElementById("chat-input");
    const chatSend = document.getElementById("chat-send");

    let currentReferences = {};

    // Load initial report list
    fetchReports();

    closePanelBtn.addEventListener("click", () => {
        referencePanel.classList.add("hidden");
        document.querySelectorAll(".interactive-sentence.active").forEach(el => el.classList.remove("active"));
        referenceIframe.src = "";
    });

    async function fetchReports() {
        try {
            const res = await fetch("/api/reports");
            const data = await res.json();
            reportListContainer.innerHTML = "";
            
            if (data.reports.length === 0) {
                reportListContainer.innerHTML = "<p style='padding:1rem;color:var(--text-secondary);'>No reports found.</p>";
                return;
            }

            data.reports.forEach((report, index) => {
                const item = document.createElement("div");
                item.className = "report-item";
                
                // Parse date from filename: 일일보고_20260408.txt
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
                    document.querySelectorAll(".report-item").forEach(el => el.classList.remove("active"));
                    item.classList.add("active");
                    loadReport(report.filename);
                });
                reportListContainer.appendChild(item);

                // Auto-load first report
                if (index === 0) {
                    item.classList.add("active");
                    loadReport(report.filename);
                }
            });
        } catch (err) {
            console.error(err);
            reportListContainer.innerHTML = "<p>Error loading reports.</p>";
        }
    }

    async function loadReport(filename) {
        try {
            reportBody.innerHTML = `<div class="loader-pulse"></div>`;
            reportTitle.textContent = "Loading...";
            
            const res = await fetch(`/api/reports/${filename}`);
            const data = await res.json();
            
            reportTitle.textContent = filename;
            parseAndRenderReport(data.content);
        } catch (err) {
            console.error(err);
            reportBody.innerHTML = `<p>Error loading report content.</p>`;
        }
    }

    function parseAndRenderReport(text) {
        // 1. Extract Reference Table
        currentReferences = {};
        // Find markdown table lines with references like | [1] | Source | Title ...
        const refLines = text.match(/\|\s*\[(\d+)\]\s*\|.*\|/g);
        if (refLines) {
            refLines.forEach(line => {
                // simple split by |
                const cols = line.split("|").map(s => s.trim()).filter(s => s.length > 0);
                if (cols.length >= 4) {
                    const numMatch = cols[0].match(/\[(\d+)\]/);
                    if (numMatch) {
                        const num = numMatch[1];
                        const source = cols[1];
                        const title = cols[2];
                        const time = cols[3];
                        
                        // Look for http in the whole line
                        let urlMatch = line.match(/(https?:\/\/[^\s|]+)/);
                        let url = urlMatch ? urlMatch[1] : "";
                        
                        currentReferences[num] = { num, source, title, time, url };
                    }
                }
            });
        }

        // 2. Format Body Content
        // Remove Reference table from main view to avoid clutter, or keep it. Let's keep it but formatted.
        let htmlBody = text
            .replace(/</g, "&lt;").replace(/>/g, "&gt;") // sanitize basic
            .replace(/^###\s+(.*$)/gm, '<h4>$1</h4>\n\n')
            .replace(/^##\s+(.*$)/gm, '<h3>$1</h3>\n\n')
            .replace(/^#\s+(.*$)/gm, '<h2>$1</h2>\n\n')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/={10,}/g, '<hr>\n\n')
            .replace(/-{10,}/g, '<hr>\n\n');

        // Split by double newline to wrap paragraphs
        let blocks = htmlBody.split(/\n\s*\n/).filter(b => b.trim().length > 0);
        htmlBody = blocks.map(block => {
            if (block.trim().startsWith('<h') || block.trim().startsWith('<hr')) return block;
            if (block.startsWith('|')) {
                // Format table
                const rows = block.split('\n').filter(r => r.trim());
                let tableHtml = '<table style="width:100%; border-collapse:collapse; margin-top:20px; font-size:0.9rem;">';
                rows.forEach((row, rowIndex) => {
                    if (row.includes('---')) return; // skip markdown divider
                    const tag = rowIndex === 0 ? 'th' : 'td';
                    const cells = row.split('|').map(c => c.trim()).filter((_, i, arr) => i > 0 && i < arr.length - 1);
                    tableHtml += '<tr>' + cells.map(c => `<${tag} style="border:1px solid #334155; padding:8px;">${c}</${tag}>`).join('') + '</tr>';
                });
                tableHtml += '</table>';
                return tableHtml;
            }
            // List items
            if (block.startsWith('- ')) {
                 return '<ul>' + block.split('\n').map(l => {
                     let t = l.replace(/^- /, '');
                     t = wrapSentencesWithReferences(t);
                     return `<li style="margin-bottom:10px;">${t}</li>`;
                 }).join('') + '</ul>';
            }
            
            // Text paragraph
            let wrappedContent = wrapSentencesWithReferences(block);
            return `<p>${wrappedContent}</p>`;
        }).join('');

        reportBody.innerHTML = htmlBody;

        // Attach click listeners to interactive sentences
        document.querySelectorAll(".interactive-sentence").forEach(el => {
            el.addEventListener("click", function() {
                // Toggle active state
                const isActive = this.classList.contains("active");
                document.querySelectorAll(".interactive-sentence.active").forEach(activeEl => activeEl.classList.remove("active"));
                
                if (!isActive) {
                    this.classList.add("active");
                    const refNums = this.getAttribute("data-refs").split(",");
                    openReferencePanel(refNums);
                } else {
                    referencePanel.classList.add("hidden");
                }
            });
        });
    }

    function wrapSentencesWithReferences(text) {
        // Regex to find sentences containing references [x]
        // This regex looks for chunks of text optionally ending with [x], and wraps them.
        // It's a heuristic for Korean text usually ending with '다 [1].' or '다. [1]' or '다 [1]'
        
        let result = "";
        let currentIndex = 0;
        
        // Find all [d] occurrences
        const regex = /\[(\d+)\]/g;
        let match;
        
        // We will process the text by finding 'sentences' around the tags.
        // For simplicity: split text into sentences by `. `, end of string, or `\n`
        const sentences = text.split(/(?<=\.\s|\]\.\s|\n)/);
        
        sentences.forEach(sentence => {
            // See if this sentence has any citations
            const citationMatch = sentence.match(/\[(\d+)\]/g);
            if (citationMatch) {
                // Extract numbers
                const nums = citationMatch.map(s => s.replace(/[\[\]]/g, ''));
                
                // Format the citations inside the sentence to look nicer
                let formattedSentence = sentence.replace(/\[\d+\]/g, match => {
                    return `<span class="ref-tag">${match}</span>`;
                });
                
                result += `<span class="interactive-sentence" data-refs="${nums.join(',')}">${formattedSentence}</span>`;
            } else {
                result += sentence;
            }
        });
        
        return result;
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
                
                if (ref.url && !firstUrl) {
                    firstUrl = ref.url;
                }
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
                
                const noUrlMsg = document.createElement("div");
                noUrlMsg.className = "placeholder-text";
                noUrlMsg.style.padding = "2rem";
                noUrlMsg.style.textAlign = "center";
                noUrlMsg.textContent = "No URL provided for this reference.";
                referenceContent.appendChild(noUrlMsg);
            }
        }
    }

    // --- Generate Report Logic ---
    btnGenerate.addEventListener("click", async () => {
        btnGenerate.disabled = true;
        btnGenerateText.style.display = "none";
        btnGenerateSpinner.classList.remove("hidden");
        
        try {
            const res = await fetch("/api/generate", { method: "POST" });
            const data = await res.json();
            if (data.success) {
                await fetchReports();
            } else {
                alert("Generation failed");
            }
        } catch (err) {
            console.error("Generation error:", err);
            alert("Error connecting to server for report generation.");
        } finally {
            btnGenerate.disabled = false;
            btnGenerateText.style.display = "inline-block";
            btnGenerateSpinner.classList.add("hidden");
        }
    });

    // --- Chat Logic ---
    chatHeaderToggle.addEventListener("click", () => {
        chatWidget.classList.toggle("collapsed");
    });
    
    chatSend.addEventListener("click", sendChatMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendChatMessage();
    });

    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        
        appendChatMessage(text, "user");
        chatInput.value = "";
        
        const loadingMsg = appendChatMessage("Thinking...", "ai", true);
        
        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            
            loadingMsg.remove();
            appendChatMessage(data.reply, "ai");
        } catch (err) {
            console.error(err);
            loadingMsg.remove();
            appendChatMessage("Error: Could not connect to the AI engine.", "system");
        }
    }
    
    function appendChatMessage(text, sender, isLoading = false) {
        const div = document.createElement("div");
        div.className = `chat-message ${sender}`;
        
        let formatted = text
            .replace(/</g, "&lt;").replace(/>/g, "&gt;") 
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
        
        if (sender === "ai") {
            formatted = wrapSentencesWithReferences(formatted);
        }
        
        div.innerHTML = formatted;
        
        if (sender === "ai") {
             div.querySelectorAll(".interactive-sentence").forEach(el => {
                el.addEventListener("click", function() {
                    const isActive = this.classList.contains("active");
                    document.querySelectorAll(".interactive-sentence.active").forEach(activeEl => activeEl.classList.remove("active"));
                    
                    if (!isActive) {
                        this.classList.add("active");
                        const refNums = this.getAttribute("data-refs").split(",");
                        // Uses the current report's references if available
                        openReferencePanel(refNums);
                    } else {
                        referencePanel.classList.add("hidden");
                    }
                });
             });
        }
        
        if (isLoading) div.style.opacity = "0.7";
        chatBody.appendChild(div);
        chatBody.scrollTop = chatBody.scrollHeight;
        return div;
    }
});
