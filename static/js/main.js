document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    
    const historyList = document.getElementById('history-list');
    const refreshHistoryBtn = document.getElementById('refresh-history-btn');
    const nodeIpDisplay = document.getElementById('node-ip');
    
    // NEW PEERS DECK INTERACTION HOOK
    const peersGrid = document.getElementById('peers-grid');

    let selectedPeerIp = null; // Track selected socket target location

    if (nodeIpDisplay) {
        nodeIpDisplay.textContent = window.location.hostname;
    }

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message;
        if (isError) {
            toast.className = `fixed bottom-6 z-50 text-rose-200 font-medium text-sm px-5 py-3.5 rounded-xl shadow-2xl transition-all duration-300 bg-rose-950/80 border border-rose-800/60`;
        } else {
            toast.className = `fixed bottom-6 z-50 text-emerald-200 font-medium text-sm px-5 py-3.5 rounded-xl shadow-2xl transition-all duration-300 bg-emerald-950/80 border border-emerald-800/60`;
        }
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
        setTimeout(() => {
            toast.style.transform = 'translateY(20px)';
            toast.style.opacity = '0';
        }, 3500);
    }

    // NEW INTERACTION CORE: Dynamic network neighbor polling and DOM node injection
    async function queryLiveNetworkPeers() {
        try {
            const response = await fetch('/api/peers');
            if (!response.ok) return;
            const peers = await response.json();
            
            const peerEntries = Object.entries(peers);
            if (peerEntries.length === 0) {
                peersGrid.innerHTML = `
                    <div class="col-span-2 border border-slate-800/60 p-4 rounded-xl bg-slate-950/40 text-center">
                        <p class="text-xs text-slate-500 italic">No other desktop nodes active on LAN. Open Tessera on a second PC to watch auto-discovery execute.</p>
                    </div>`;
                selectedPeerIp = null;
                return;
            }

            peersGrid.innerHTML = peerEntries.map(([ip, data]) => {
                const isSelected = selectedPeerIp === ip;
                return `
                    <div data-ip="${ip}" class="peer-card border ${isSelected ? 'border-emerald-500 bg-emerald-950/10' : 'border-slate-800 bg-slate-950/60'} p-3.5 rounded-xl cursor-pointer hover:border-slate-700 transition duration-150 flex items-center justify-between group">
                        <div class="truncate pr-2">
                            <p class="text-xs font-semibold ${isSelected ? 'text-emerald-400' : 'text-slate-200'} group-hover:text-blue-400 transition-colors truncate code-font">${data.hostname}</p>
                            <p class="text-[10px] text-slate-500 code-font mt-0.5">${ip}</p>
                        </div>
                        <div class="h-4 w-4 rounded-full border ${isSelected ? 'border-emerald-500 bg-emerald-500' : 'border-slate-700'} flex items-center justify-center shrink-0">
                            ${isSelected ? '<span class="block h-1.5 w-1.5 rounded-full bg-slate-950"></span>' : ''}
                        </div>
                    </div>
                `;
            }).join('');

            // Bind click transaction event listeners to the generated peer elements
            document.querySelectorAll('.peer-card').forEach(card => {
                card.addEventListener('click', () => {
                    const targetIp = card.getAttribute('data-ip');
                    if (selectedPeerIp === targetIp) {
                        selectedPeerIp = null; // Uncheck option toggle
                    } else {
                        selectedPeerIp = targetIp;
                    }
                    queryLiveNetworkPeers(); // Instantly update active check styles
                    showToast(selectedPeerIp ? `Target streaming route locked: ${selectedPeerIp}` : 'Routing fallback changed to Local Drop Zone folder.');
                });
            });

        } catch (err) {
            console.error("Discovery polling process encountered an index link error:", err);
        }
    }

    async function loadTransferHistory() {
        try {
            const response = await fetch('/api/history');
            if (!response.ok) return;
            const history = await response.json();
            
            if (history.length === 0) {
                historyList.innerHTML = `
                    <div class="flex flex-col items-center justify-center text-center py-12 h-full">
                        <p class="text-xs text-slate-600 italic">No historical transactions committed.</p>
                    </div>`;
                return;
            }

            historyList.innerHTML = history.map(item => `
                <div class="flex items-center justify-between bg-slate-950/80 p-3.5 rounded-xl border border-slate-900 shadow-sm">
                    <div class="truncate max-w-[70%] space-y-0.5">
                        <p class="text-slate-200 font-semibold text-xs truncate code-font tracking-tight">${item.filename}</p>
                        <p class="text-[10px] text-slate-500 code-font">${item.peer_ip}</p>
                    </div>
                    <span class="text-[9px] uppercase font-bold tracking-wider px-2 py-1 rounded-md ${
                        item.status === 'completed' ? 'bg-emerald-500/5 text-emerald-400 border border-emerald-500/10' : 'bg-amber-500/5 text-amber-400 border border-amber-500/10'
                    }">${item.status}</span>
                </div>
            `).join('');
        } catch (err) {
            console.error('Failed to parse database records:', err);
        }
    }

    refreshHistoryBtn.addEventListener('click', loadTransferHistory);

    syncTextBtn.addEventListener('click', async () => {
        const content = clipboardInput.value.trim();
        if (!content) return showToast('Please enter a content string block first.', true);

        try {
            const response = await fetch('/api/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            const data = await response.json();
            if (response.ok) {
                showToast(data.message);
                clipboardInput.value = '';
            } else {
                showToast(data.error || 'Interface Sync Execution Failed', true);
            }
        } catch (err) {
            showToast('Unable to synchronize with the desktop core daemon', true);
        }
    });

    dropZone.addEventListener('click', () => fileElement.click());
    fileElement.addEventListener('change', () => {
        if (fileElement.files.length > 0) {
            handleFileUpload(fileElement.files[0]);
        }
    });

    // RE-ENGINEERED UPLOAD INTERFACE: Intelligently branches between simple HTTP drops and remote socket routing!
    function handleFileUpload(file) {
        // SCENARIO B: A peer card is checked! Forward this file directly to the selected remote computer via TCP Sockets
        if (selectedPeerIp) {
            progressContainer.classList.remove('hidden');
            statusText.textContent = `Pushing chunk data to ${selectedPeerIp}...`;
            progressBar.style.width = '50%'; // Simulated visual trigger block for socket background worker
            progressPercent.textContent = 'RAW ROUTE';

            fetch('/api/send_peer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    "target_ip": selectedPeerIp,
                    "file_path": file.name // Note: In an integrated desktop dashboard utility app context, file paths are parsed cleanly from system app wrappers
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    showToast(`Successfully opened TCP pipeline tunnel! File streamed to peer node.`);
                    statusText.textContent = "Streamed!";
                    progressBar.style.width = '100%';
                } else {
                    showToast(data.error || 'Socket transfer failed', true);
                    statusText.textContent = "Faulted.";
                }
                setTimeout(() => progressContainer.classList.add('hidden'), 2500);
                loadTransferHistory();
            })
            .catch(() => {
                showToast('Socket routing instruction dropped by local area interface execution parameters', true);
                progressContainer.classList.add('hidden');
            });

            fileElement.value = '';
            return;
        }

        // SCENARIO A: Default fallback behavior. Standard chunked file collection drop from mobile browsers to local storage folder
        const formData = new FormData();
        formData.append('file', file);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "Streaming packets to local repository...";
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload', true);

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressPercent.textContent = `${percent}%`;
            }
        });

        xhr.onload = () => {
            if (xhr.status === 200) {
                const res = JSON.parse(xhr.responseText);
                showToast(res.message || 'Data drop finalized!');
                statusText.textContent = "Complete!";
                loadTransferHistory();
            } else {
                showToast('Local drop pipeline failure.', true);
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };
        xhr.send(formData);
    }

    // App Initialization Routine
    loadTransferHistory();
    queryLiveNetworkPeers();
    
    // Poll the local subnet device cache every 4 seconds to maintain structural live status accuracy
    setInterval(queryLiveNetworkPeers, 4000);
});