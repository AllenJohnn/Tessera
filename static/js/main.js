document.addEventListener('DOMContentLoaded', () => {
    const clipboardInput = document.getElementById('clipboard-input');
    const syncTextBtn = document.getElementById('sync-text-btn');
    const dropZone = document.getElementById('drop-zone');
    const fileElement = document.getElementById('file-element');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const progressPercent = document.getElementById('progress-percent');
    const statusText = document.getElementById('status-text');
    
    const filesList = document.getElementById('files-list');
    const refreshFilesBtn = document.getElementById('refresh-files-btn');
    const clearFilesBtn = document.getElementById('clear-files-btn');
    const peersGrid = document.getElementById('peers-grid');
    const textStreamContainer = document.getElementById('text-stream-container');

    // Element bindings mapping to header station identification labels
    const displayNameField = document.getElementById('display-name');
    const editNameBtn = document.getElementById('edit-name-btn');

    // NEW ELEMENT BINDINGS: Multi-device functional interactive nodes
    const clearTextsBtn = document.getElementById('clear-texts-btn');
    const resetInputBtn = document.getElementById('reset-input-btn');

    let selectedPeerIp = null;
    let lastSeenTimestamp = 0; 
    
    // Read locally configured custom callsign if it exists in browser memory cache
    let sessionCallsign = localStorage.getItem('tessera_callsign') || "";

    function showToast(message, isError = false) {
        const toast = document.getElementById('toast');
        toast.textContent = message.toUpperCase();
        toast.style.borderColor = isError ? '#551111' : '#2c2c2c';
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
        
        setTimeout(() => {
            toast.style.transform = 'translateY(20px)';
            toast.style.opacity = '0';
        }, 3000);
    }

    // Ping background server registry
    async function broadcastMobilePresence() {
        try {
            const response = await fetch('/api/ping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "hostname": sessionCallsign })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (!sessionCallsign && data.assigned_name) {
                    sessionCallsign = data.assigned_name;
                    localStorage.setItem('tessera_callsign', sessionCallsign);
                }
                
                if (displayNameField) {
                    displayNameField.textContent = sessionCallsign;
                }
            }
        } catch (err) {
            console.error("Presence beacon dropped");
        }
    }

    // Pull network map from endpoint cache
    async function queryLiveNetworkPeers() {
        try {
            const response = await fetch('/api/peers');
            if (!response.ok) return;
            const peers = await response.json();
            const peerEntries = Object.entries(peers);
            
            if (peerEntries.length === 0) {
                peersGrid.innerHTML = `
                    <div class="col-span-2 border border-[#1c1c1c] p-4 text-center bg-[#070707] w-full">
                        <p class="text-[10px] text-neutral-600 italic mono uppercase tracking-wider">NO DEVICES DETECTED</p>
                    </div>`;
                selectedPeerIp = null;
                return;
            }

            peersGrid.innerHTML = peerEntries.map(([ip, data]) => {
                const isSelected = selectedPeerIp === ip;
                
                // FIXED: Check heartbeats dynamically to render green pulse dots for active sessions
                const isLiveNow = (Date.now() / 1000) - data.last_seen < 12;
                const indicatorDot = isLiveNow 
                    ? `<div class="h-2 w-2 rounded-full bg-emerald-500 animate-pulse shrink-0 ml-3"></div>`
                    : `<div class="h-2 w-2 rounded-full bg-amber-600 shrink-0 ml-3"></div>`;

                return `
                    <div data-ip="${ip}" class="peer-card border ${isSelected ? 'border-white bg-neutral-900/40' : 'border-[#1c1c1c] bg-[#070707]'} p-3.5 cursor-pointer hover:border-neutral-500 transition duration-100 flex items-center justify-between">
                        <div class="truncate">
                            <p class="text-xs font-semibold tracking-tight truncate ${isSelected ? 'text-white' : 'text-neutral-400'}">${data.hostname}</p>
                            <p class="text-[10px] text-neutral-600 mono mt-1">${ip} // ${data.type.toUpperCase()}</p>
                        </div>
                        <div class="flex items-center gap-2">
                            <div class="h-2 w-2 rounded-none border ${isSelected ? 'bg-white border-white' : 'border-neutral-800'} shrink-0"></div>
                            ${indicatorDot}
                        </div>
                    </div>
                `;
            }).join('');

            document.querySelectorAll('.peer-card').forEach(card => {
                card.addEventListener('click', () => {
                    const targetIp = card.getAttribute('data-ip');
                    selectedPeerIp = (selectedPeerIp === targetIp) ? null : targetIp;
                    queryLiveNetworkPeers();
                    showToast(selectedPeerIp ? `route locked: ${selectedPeerIp}` : 'route: local storage');
                });
            });
        } catch (err) {
            console.error(err);
        }
    }

    // Pull direct local workspace storage indices
    async function loadAvailableFiles() {
        try {
            const response = await fetch('/api/files');
            if (!response.ok) return;
            const files = await response.json();
            
            if (files.length === 0) {
                filesList.innerHTML = `<p class="text-[10px] text-neutral-600 italic py-3 uppercase tracking-wider">HISTORY EMPTY</p>`;
                return;
            }

            filesList.innerHTML = files.map(file => `
                <div class="flex items-center justify-between bg-[#070707] p-3 border border-[#1c1c1c] hover:border-neutral-800 transition duration-100">
                    <div class="truncate max-w-[72%]">
                        <a href="/storage/${encodeURIComponent(file.name)}" class="text-neutral-300 text-xs truncate font-medium hover:text-white block" download>${file.name}</a>
                        <p class="text-[10px] text-neutral-600 mono mt-1">${file.size}</p>
                    </div>
                    <a href="/storage/${encodeURIComponent(file.name)}" class="text-[9px] font-bold tracking-widest px-2.5 py-1.5 border border-neutral-800 text-neutral-400 hover:border-white hover:text-white transition duration-100 uppercase" download>GET</a>
                </div>
            `).join('');
        } catch (err) {
            console.error(err);
        }
    }

    // Polls the web backend cache for new text payloads
    async function checkIncomingTextStreams() {
        if (!textStreamContainer) return;
        try {
            const response = await fetch('/api/clipboard/get');
            if (!response.ok) return;
            const data = await response.json();

            if (data && data.content && data.timestamp > lastSeenTimestamp) {
                lastSeenTimestamp = data.timestamp;

                const emptyMsg = textStreamContainer.querySelector('.empty-stream-msg');
                if (emptyMsg) emptyMsg.remove();

                const textRow = document.createElement('div');
                textRow.className = "flex items-center justify-between bg-[#070707] p-3 border border-[#1c1c1c] hover:border-neutral-800 transition duration-100 animate-fade-in";
                
                const displayText = data.content.length > 40 ? data.content.substring(0, 40) + "..." : data.content;
                const senderTag = data.sender ? data.sender.toUpperCase() : "UNKNOWN";

                textRow.innerHTML = `
                    <div class="truncate max-w-[72%]">
                        <p class="text-neutral-300 text-xs font-medium break-all select-all">${displayText}</p>
                        <p class="text-[9px] text-neutral-500 mono mt-1 uppercase tracking-wide">RECEIVED FROM // ${senderTag}</p>
                    </div>
                    <button type="button" class="copy-stream-btn text-[9px] font-bold tracking-widest px-2.5 py-1.5 border border-neutral-800 text-neutral-400 hover:border-white hover:text-white hover:bg-white hover:text-black transition duration-100 uppercase cursor-pointer" data-raw="${encodeURIComponent(data.content)}">COPY</button>
                `;

                textRow.querySelector('.copy-stream-btn').addEventListener('click', function() {
                    const rawContent = decodeURIComponent(this.getAttribute('data-raw'));
                    navigator.clipboard.writeText(rawContent).then(() => {
                        this.innerText = "COPIED!";
                        setTimeout(() => this.innerText = "COPY", 1500);
                    }).catch(() => showToast('browser copy blocked', true));
                });

                textStreamContainer.insertBefore(textRow, textStreamContainer.firstChild);
                showToast(`text message streaming from ${senderTag}`);
            }
        } catch (err) {
            console.error("Text stream verification exception dropping:", err);
        }
    }

    // FIXED: Connected inline callsign editing logic prompt controller tracking block
    if (editNameBtn) {
        editNameBtn.addEventListener('click', () => {
            const currentName = sessionCallsign || "ASSIGNING...";
            const inputPrompt = prompt("ENTER NEW STATION CALLSIGN:", currentName);
            
            if (inputPrompt !== null) {
                const sanitizedInput = inputPrompt.trim().replace(/[^a-zA-Z0-9-_ ]/g, "").toUpperCase();
                if (!sanitizedInput) {
                    showToast('Invalid station identifier matching strings', true);
                    return;
                }
                
                sessionCallsign = sanitizedInput;
                localStorage.setItem('tessera_callsign', sessionCallsign);
                if (displayNameField) displayNameField.textContent = sessionCallsign;
                
                showToast(`callsign assigned: ${sessionCallsign}`);
                broadcastMobilePresence(); 
            }
        });
    }

    // FIXED: Clear operation implementation for dynamic text rows
    if (clearTextsBtn) {
        clearTextsBtn.addEventListener('click', () => {
            if (textStreamContainer) {
                textStreamContainer.innerHTML = `<p class="text-[10px] text-neutral-600 italic py-1 mono empty-stream-msg">No incoming text logs tracked...</p>`;
                showToast('text feed cleared');
            }
        });
    }

    // FIXED: One-click fast reset clear utility macro macro tracking hook inside input elements
    if (resetInputBtn) {
        resetInputBtn.addEventListener('click', () => {
            if (clipboardInput) {
                clipboardInput.value = '';
                showToast('input buffer cleared');
            }
        });
    }

    clearFilesBtn.addEventListener('click', async () => {
        if (!confirm("CONFIRM COMMAND: PURGE ALL FILES INSIDE REPOSITORY HISTORIES?")) return;
        try {
            const response = await fetch('/api/clear_files', { method: 'POST' });
            if (response.ok) {
                showToast('storage wiped clean');
                loadAvailableFiles();
            } else {
                showToast('clear execution failed', true);
            }
        } catch (err) {
            showToast('communication exception', true);
        }
    });

    refreshFilesBtn.addEventListener('click', loadAvailableFiles);

    syncTextBtn.addEventListener('click', async (e) => {
        e.preventDefault(); 
        const content = clipboardInput.value.trim();
        if (!content) return showToast('Buffer input empty.', true);

        try {
            const response = await fetch('/api/clipboard', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            });
            if (response.ok) {
                showToast('clipboard updated');
                clipboardInput.value = '';
                await checkIncomingTextStreams();
            } else {
                showToast('sync channel fault', true);
            }
        } catch (err) {
            showToast('communication error', true);
        }
    });

    dropZone.addEventListener('click', () => fileElement.click());
    fileElement.addEventListener('change', () => {
        if (fileElement.files.length > 0) {
            handleFileUpload(fileElement.files[0]);
        }
    });

    function handleFileUpload(file) {
        if (selectedPeerIp) {
            progressContainer.classList.remove('hidden');
            statusText.textContent = `SENDING DATA CHUNKS OVER RAW SOCKETS...`;
            progressBar.style.width = '100%';
            progressPercent.textContent = 'SOCKET';

            fetch('/api/send_peer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ "target_ip": selectedPeerIp, "file_path": file.name })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    showToast('socket operation successful');
                    statusText.textContent = "COMPLETE";
                } else {
                    showToast('socket stream aborted', true);
                }
                setTimeout(() => progressContainer.classList.add('hidden'), 2000);
                loadAvailableFiles();
            });
            fileElement.value = '';
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        progressContainer.classList.remove('hidden');
        statusText.textContent = "UPLOADING FILE BLOCKS TO SYSTEM DISK...";
        progressBar.style.width = '0%';
        progressPercent.textContent = '0%';

        const clientRequest = new XMLHttpRequest();
        clientRequest.open('POST', '/api/upload', true);

        clientRequest.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressPercent.textContent = `${percent}%`;
            }
        });

        clientRequest.onload = () => {
            if (clientRequest.status === 200) {
                showToast('transfer complete');
                statusText.textContent = "COMPLETE";
                loadAvailableFiles();
            } else {
                showToast('pipeline channel crash', true);
            }
            setTimeout(() => progressContainer.classList.add('hidden'), 2000);
            fileElement.value = ''; 
        };
        clientRequest.send(formData);
    }

    async function initTessera() {
        await broadcastMobilePresence(); 
        await queryLiveNetworkPeers();   
        await loadAvailableFiles();      
        await checkIncomingTextStreams(); 
        
        setInterval(broadcastMobilePresence, 4000);
        setInterval(queryLiveNetworkPeers, 4000);
        setInterval(checkIncomingTextStreams, 2000); 
    }

    initTessera();
});