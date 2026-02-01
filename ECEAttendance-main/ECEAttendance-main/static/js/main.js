const socket = io({ transports: ['websocket'] });

let currentEventId = localStorage.getItem('selectedEventId') || null;
let currentBranchFilter = 'ALL';
let html5QrcodeScanner;
let pendingRollNumber = null;

// Initial Load
document.addEventListener("DOMContentLoaded", () => {
    loadEvents();
    initScanner();
});

// Socket IO Listeners
socket.on('update_counts', (data) => {
    // Only update if the event ID matches the currently selected one
    if (data.event_id === currentEventId) {
        updateStats(data);
    }
});

function loadEvents() {
    fetch('/api/events')
        .then(res => res.json())
        .then(events => {
            const select = document.getElementById('eventSelect');
            const uploadSelect = document.getElementById('uploadEventSelect');
            const deleteSelect = document.getElementById('deleteEventSelect');

            // Clear current options except first
            select.innerHTML = '<option value="">Select Event</option>';
            uploadSelect.innerHTML = '<option value="">-- Select Event for Upload --</option>';
            if (deleteSelect) deleteSelect.innerHTML = '<option value="">-- Select Event to Remove --</option>';

            events.forEach(event => {
                const opt = document.createElement('option');
                opt.value = event._id;
                opt.innerText = event.name;
                select.appendChild(opt);

                const opt2 = opt.cloneNode(true);
                uploadSelect.appendChild(opt2);

                if (deleteSelect) {
                    const opt3 = opt.cloneNode(true);
                    deleteSelect.appendChild(opt3);
                }
            });

            // Restore selection if exists
            if (currentEventId) {
                select.value = currentEventId;
                handleEventChange();
            }
        })
        .catch(err => console.error('Error loading events:', err));
}

function handleRemoveEventButtonClick() {
    const select = document.getElementById('deleteEventSelect');
    const confirmInput = document.getElementById('deleteEventConfirmName');

    if (!select.value) {
        alert("Please select an event to remove.");
        return;
    }

    const eventId = select.value;
    const eventName = select.options[select.selectedIndex].text;
    const userInput = confirmInput.value.trim();

    if (userInput !== eventName) {
        alert(`Name mismatch! Please type "${eventName}" exactly to confirm deletion.`);
        return;
    }

    deleteEvent(eventId, eventName);
    confirmInput.value = ''; // Reset after call
}

function deleteEvent(eventId, eventName) {
    if (!confirm(`FINAL WARNING: This will PERMANENTLY DELETE the event "${eventName}" and ALL associated data. Proceed?`)) {
        return;
    }

    fetch(`/api/events/${eventId}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                alert(data.message);
                if (currentEventId === eventId) {
                    currentEventId = null;
                    localStorage.removeItem('selectedEventId');
                    resetStats();
                }
                loadEvents();
            } else {
                alert("Error: " + data.error);
            }
        })
        .catch(err => console.error(err));
}

function handleEventChange() {
    const select = document.getElementById('eventSelect');
    currentEventId = select.value;
    localStorage.setItem('selectedEventId', currentEventId);

    if (currentEventId) {
        refreshStats();
        updateDownloadLinks();
        // If attendees list modal is open, refresh it
        if (document.getElementById('viewListModal').style.display === 'block') {
            filterList(currentBranchFilter);
        }
    } else {
        resetStats();
    }
}

function refreshStats() {
    if (!currentEventId) return;
    fetch(`/api/stats?event_id=${currentEventId}`)
        .then(response => response.json())
        .then(updateStats)
        .catch(err => console.error(err));
}

function updateStats(data) {
    if (!data) return;
    document.getElementById('totalCount').innerText = data.total;
    if (data.total_students !== undefined) {
        document.getElementById('totalStudents').innerText = data.total_students;
    }

    const grid = document.getElementById('branchGrid');
    grid.innerHTML = '';

    for (const [branch, count] of Object.entries(data.branch_counts)) {
        const item = document.createElement('div');
        item.className = 'branch-item';
        item.innerHTML = `
            <span class="branch-name">${branch}</span>
            <span class="branch-count">${count}</span>
        `;
        grid.appendChild(item);
    }
}

function resetStats() {
    document.getElementById('totalCount').innerText = '0';
    document.getElementById('totalStudents').innerText = '0';
    document.getElementById('branchGrid').innerHTML = '';
    // Disable branch PDF buttons
    document.querySelectorAll('.branch-pdf-btn').forEach(btn => {
        btn.href = '#';
        btn.style.opacity = '0.5';
        btn.style.pointerEvents = 'none';
    });
    document.getElementById('downloadExcelLink').href = '#';
}

function updateDownloadLinks() {
    if (!currentEventId) return;

    // Update Excel link
    document.getElementById('downloadExcelLink').href = `/download_full_excel/${currentEventId}`;

    // Update PDF buttons
    document.querySelectorAll('.branch-pdf-btn').forEach(btn => {
        const branch = btn.getAttribute('data-branch');
        btn.href = `/download_pdf/${currentEventId}/${branch}`;
        btn.style.opacity = '1';
        btn.style.pointerEvents = 'auto';
    });
}

// Event Creation
function createNewEvent() {
    const nameInput = document.getElementById('newEventName');
    const name = nameInput.value.strip ? nameInput.value.strip() : nameInput.value.trim();

    if (!name) {
        alert("Please enter an event name.");
        return;
    }

    fetch('/api/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                nameInput.value = '';
                loadEvents();
                alert("Event created successfully!");
            } else {
                alert("Error: " + data.error);
            }
        })
        .catch(err => console.error(err));
}

// Excel Upload
function handleExcelUpload() {
    const eventId = document.getElementById('uploadEventSelect').value;
    const fileInput = document.getElementById('excelFileInput');
    const statusDiv = document.getElementById('uploadStatus');

    if (!eventId) {
        alert("Please select an event for the upload.");
        return;
    }

    if (fileInput.files.length === 0) {
        alert("Please select an Excel file.");
        return;
    }

    const formData = new FormData();
    formData.append('event_id', eventId);
    formData.append('file', fileInput.files[0]);

    statusDiv.innerText = "Uploading and processing...";
    statusDiv.style.color = "blue";

    fetch('/api/upload_students', {
        method: 'POST',
        body: formData
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                statusDiv.innerText = `Successfully registered ${data.count} students!`;
                statusDiv.style.color = "green";
                fileInput.value = '';
                if (eventId === currentEventId) refreshStats();
            } else {
                statusDiv.innerText = "Error: " + data.error;
                statusDiv.style.color = "red";
            }
        })
        .catch(err => {
            statusDiv.innerText = "Network Error during upload.";
            statusDiv.style.color = "red";
            console.error(err);
        });
}

// Scanner Functions
function initScanner() {
    html5QrcodeScanner = new Html5QrcodeScanner(
        "reader",
        { fps: 10, qrbox: { width: 250, height: 250 } },
        /* verbose= */ false);
    html5QrcodeScanner.render(onScanSuccess, onScanFailure);
}

function onScanSuccess(decodedText) {
    markAttendance(decodedText);
}

function onScanFailure(error) {
    // ignore
}

function handleManualEntry() {
    const input = document.getElementById('manualRollInput');
    const roll = input.value;
    if (roll) {
        markAttendance(roll);
        input.value = '';
    }
}

function markAttendance(rollNumber) {
    if (!currentEventId) {
        alert("Please select an event first!");
        return;
    }

    const resultDiv = document.getElementById('scanResult');
    resultDiv.innerHTML = 'Processing...';
    resultDiv.className = 'scan-result';

    fetch('/api/mark_attendance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roll_number: rollNumber, event_id: currentEventId })
    })
        .then(response => response.json().then(data => ({ status: response.status, body: data })))
        .then(({ status, body }) => {
            if (status === 200) {
                resultDiv.innerText = `Success: ${body.name} (${body.branch})`;
                resultDiv.className = 'scan-result success';
            } else if (status === 409) {
                resultDiv.innerText = `Duplicate: Already marked for this event.`;
                resultDiv.className = 'scan-result warning';
            } else if (status === 404) {
                resultDiv.innerText = `Student not found in this event.`;
                resultDiv.className = 'scan-result error';
                openAddStudentModal(body.roll_number);
            } else {
                resultDiv.innerText = `Error: ${body.error || 'Unknown error'}`;
                resultDiv.className = 'scan-result error';
            }
        })
        .catch(err => {
            resultDiv.innerText = `Network Error`;
            resultDiv.className = 'scan-result error';
            console.error(err);
        });
}

// Modal Functions
function openModal(modalId) {
    document.getElementById(modalId).style.display = "block";
    if (html5QrcodeScanner) html5QrcodeScanner.pause();

    // If it's the view list modal, load data
    if (modalId === 'viewListModal') {
        filterList('ALL');
    }

    // If it's the manage events modal, refresh the events list
    if (modalId === 'manageEventsModal' && currentUser === 'ECEADMIN') {
        loadEvents();
        loadAdmins();
    }
}

function loadAdmins() {
    fetch('/api/admins')
        .then(res => res.json())
        .then(admins => {
            const modalList = document.getElementById('modalAdminList');
            if (modalList) {
                modalList.innerHTML = '';
                admins.forEach(admin => {
                    const item = document.createElement('div');
                    item.style = "display: flex; justify-content: space-between; align-items: center; padding: 8px; border-bottom: 1px solid #eee;";

                    let deleteBtn = '';
                    if (admin.username !== 'ECEADMIN') {
                        deleteBtn = `
                            <button onclick="deleteAdmin('${admin._id}', '${admin.username}')" 
                                    style="background: #e67c73; color: white; border: none; padding: 2px 6px; border-radius: 4px; cursor: pointer; font-size: 0.75rem;">
                                Delete
                            </button>
                        `;
                    } else {
                        deleteBtn = `<span style="font-size: 0.75rem; color: #5f6368; font-style: italic;">System Account</span>`;
                    }

                    item.innerHTML = `
                        <span>${admin.username}</span>
                        ${deleteBtn}
                    `;
                    modalList.appendChild(item);
                });
            }
        })
        .catch(err => console.error('Error loading admins:', err));
}

function createNewAdmin() {
    const user = document.getElementById('newAdminUser').value;
    const pass = document.getElementById('newAdminPass').value;
    if (!user || !pass) {
        alert("Enter both username and password");
        return;
    }
    fetch('/api/admins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass })
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                document.getElementById('newAdminUser').value = '';
                document.getElementById('newAdminPass').value = '';
                loadAdmins();
            } else {
                alert("Error: " + data.error);
            }
        })
        .catch(err => console.error(err));
}

function deleteAdmin(id, username) {
    if (username === 'ECEADMIN') {
        alert("ECEADMIN is a system account and cannot be deleted.");
        return;
    }
    if (!confirm(`Delete admin account for "${username}"?`)) return;
    fetch(`/api/admins/${id}`, { method: 'DELETE' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                loadAdmins();
            } else {
                alert("Error: " + data.error);
            }
        })
        .catch(err => console.error(err));
}

function closeModal(modalId) {
    if (modalId) {
        document.getElementById(modalId).style.display = 'none';
        if (modalId === 'addStudentModal') pendingRollNumber = null;
    } else {
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
        pendingRollNumber = null;
    }
    if (html5QrcodeScanner) {
        try { html5QrcodeScanner.resume(); } catch (e) { }
    }
}

function openAddStudentModal(rollNumber) {
    pendingRollNumber = rollNumber;
    document.getElementById('modalRollNumber').innerText = rollNumber;
    document.getElementById('newStudentName').value = '';
    openModal("addStudentModal");
}

function submitNewStudent() {
    const name = document.getElementById('newStudentName').value;
    if (!name || !pendingRollNumber || !currentEventId) return;

    fetch('/api/add_student', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roll_number: pendingRollNumber, name: name, event_id: currentEventId })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                const resultDiv = document.getElementById('scanResult');
                resultDiv.innerText = `Added & Marked: ${name}`;
                resultDiv.className = 'scan-result success';
                closeModal('addStudentModal');
            } else {
                alert("Error adding student: " + (data.error || 'Unknown'));
            }
        })
        .catch(err => console.error(err));
}

// Attendees List functions
function openViewListModal() {
    if (!currentEventId) {
        alert("Please select an event first.");
        return;
    }
    openModal('viewListModal');
}

function filterList(branch) {
    if (!currentEventId) return;
    currentBranchFilter = branch;

    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.innerText === branch) btn.classList.add('active');
        else btn.classList.remove('active');
    });

    const downloadBtn = document.getElementById('downloadCurrentPdf');
    if (branch === 'ALL') {
        downloadBtn.style.display = 'none';
    } else {
        downloadBtn.style.display = 'inline-block';
        downloadBtn.href = `/download_pdf/${currentEventId}/${branch}`;
        downloadBtn.innerText = `Download ${branch} PDF`;
    }

    fetch(`/api/attendees?event_id=${currentEventId}&branch=${branch}`)
        .then(res => res.json())
        .then(renderTable)
        .catch(err => console.error(err));
}

function renderTable(data) {
    const tbody = document.getElementById('attendeesTableBody');
    tbody.innerHTML = '';

    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 1rem;">No attendees found.</td></tr>';
        return;
    }

    data.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.s_no}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.rollResult}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.name}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">${row.branch}</td>
            <td style="padding: 0.5rem; border-bottom: 1px solid #dadce0;">
                <button onclick="deleteFromList('${row.rollResult}')" style="background-color: #d93025; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 0.8rem;">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function deleteFromList(rollNumber) {
    if (!confirm(`Are you sure you want to PERMANENTLY DELETE ${rollNumber}?`) || !currentEventId) return;

    fetch('/api/delete_student', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roll_number: rollNumber, event_id: currentEventId })
    })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'SUCCESS') {
                alert(data.message);
                filterList(currentBranchFilter);
            } else {
                alert("Delete Failed: " + data.message);
            }
        })
        .catch(err => console.error(err));
}
