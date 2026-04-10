const API_BASE_URL = '/api';

let currentUser = null;
let currentRole = null;

// Auth
async function login(username) {
    try {
        const response = await fetch(`${API_BASE_URL}/login?username=${username}`, { method: 'POST' });
        if (!response.ok) throw new Error("Login failed");
        
        const data = await response.json();
        currentUser = data.user_id;
        currentRole = data.role;

        document.getElementById('login-section').classList.remove('active');
        
        if (currentRole === 'worker') {
            document.getElementById('worker-dashboard').classList.add('active');
            document.getElementById('worker-name-display').innerText = `Welcome, ${data.name}`;
            await fetchNotifications();
        } else if (currentRole === 'admin') {
            document.getElementById('admin-dashboard').classList.add('active');
            await fetchAdminInsights();
            await fetchNotifications();
        }
    } catch (err) {
        console.error(err);
        alert("Failed to login. Is backend running?");
    }
}

function logout() {
    currentUser = null;
    currentRole = null;
    document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));
    document.getElementById('login-section').classList.add('active');
    closeNotifications();
}

// Worker Actions
function startShift() {
    const btn = document.getElementById('start-shift-btn');
    btn.innerHTML = '<i class="fa-solid fa-stop"></i> End Delivery Shift';
    btn.classList.replace('primary-btn', 'warning-btn');
    btn.onclick = endShift;
    
    document.getElementById('file-claim-btn').disabled = false;
    document.getElementById('file-claim-btn').classList.remove('disabled');
}

function endShift() {
    const btn = document.getElementById('start-shift-btn');
    btn.innerHTML = '<i class="fa-solid fa-play"></i> Start Delivery Shift';
    btn.classList.replace('warning-btn', 'primary-btn');
    btn.onclick = startShift;
    
    document.getElementById('file-claim-btn').disabled = true;
    document.getElementById('file-claim-btn').classList.add('disabled');
}

// Modals
function openClaimModal() {
    resetModal();
    document.getElementById('claim-modal').classList.add('active');
}

function closeModal() {
    document.getElementById('claim-modal').classList.remove('active');
}

function openPayoutModal() {
    document.getElementById('payout-modal').classList.add('active');
}

function closePayoutModal() {
    document.getElementById('payout-modal').classList.remove('active');
    closeModal();
}

function resetModal() {
    ['step-gps', 'step-weather', 'step-delivery'].forEach(id => {
        const el = document.getElementById(id);
        el.classList.remove('active', 'completed');
    });
    document.getElementById('claim-result').classList.add('hidden');
    document.getElementById('trigger-ai-btn').disabled = false;
    document.getElementById('trigger-ai-btn').innerText = 'Run AI Check';
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function runAI() {
    document.getElementById('trigger-ai-btn').disabled = true;
    const steps = ['step-gps', 'step-weather', 'step-delivery'];
    
    // Simulate UI Animation Steps
    for (const stepId of steps) {
        const el = document.getElementById(stepId);
        el.classList.add('active');
        await sleep(1000); // Wait 1s
        el.classList.replace('active', 'completed');
    }

    document.getElementById('trigger-ai-btn').innerText = 'Processing...';

    // Actually ping backend
    try {
        const reqBody = {
            user_id: currentUser,
            gps_check: true,
            weather_check: true,
            delivery_check: false // Simulate an issue for demo
        };

        const res = await fetch(`${API_BASE_URL}/simulate_claim_checks`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(reqBody)
        });

        const result = await res.json();
        showResult(result);
        
        // Fetch new notifications & add to history
        await fetchNotifications();
        addHistoryItem(result);

    } catch (err) {
        console.error(err);
        alert("Failed to reach AI engine.");
    }
}

function showResult(data) {
    document.getElementById('claim-result').classList.remove('hidden');
    
    const riskPercentage = Math.round(data.risk_score * 100);
    document.getElementById('risk-percentage').innerText = `${riskPercentage}%`;
    
    // Update circle color
    let color = 'var(--success)';
    if (data.final_decision === 'warning') color = 'var(--warning)';
    if (data.final_decision === 'rejected') color = 'var(--danger)';
    document.querySelector('.risk-circle').style.borderColor = color;

    const decisionText = document.getElementById('decision-text');
    decisionText.innerText = data.final_decision.toUpperCase();
    decisionText.className = `decision-display ${data.final_decision}`;

    if (data.payout) {
        document.getElementById('trigger-ai-btn').innerText = 'Releasing Payout...';
        setTimeout(() => {
            openPayoutModal();
            // Optional: generate random amount
            const amountEl = document.querySelector('.payout-modal .amount');
            amountEl.innerText = `₹${(Math.random() * 500 + 400).toFixed(2)}`;
        }, 1500);
    } else {
        document.getElementById('trigger-ai-btn').innerText = 'Close';
        document.getElementById('trigger-ai-btn').disabled = false;
        document.getElementById('trigger-ai-btn').onclick = closeModal;
    }
}

function addHistoryItem(result) {
    const list = document.getElementById('worker-history');
    if (list.querySelector('.empty-state')) {
        list.innerHTML = '';
    }
    const html = `
        <div class="notif-item type-${result.final_decision}">
            <span class="notif-time">Just now</span>
            Claim filed. AI Decision: <b>${result.final_decision.toUpperCase()}</b>
        </div>
    `;
    list.insertAdjacentHTML('afterbegin', html);
}

// Notifications
function toggleNotifications() {
    document.getElementById('notification-sidebar').classList.toggle('open');
}
function closeNotifications() {
    document.getElementById('notification-sidebar').classList.remove('open');
}

async function fetchNotifications() {
    if (!currentUser) return;
    try {
        const res = await fetch(`${API_BASE_URL}/notifications/${currentUser}`);
        const data = await res.json();
        
        // Update badge
        const badgeId = currentRole === 'admin' ? 'admin-notif-badge' : 'worker-notif-badge';
        document.getElementById(badgeId).innerText = data.length;

        // Render Sidebar
        const list = document.getElementById('notification-list');
        if (data.length === 0) {
            list.innerHTML = '<div class="empty-state" style="text-align: center; color: var(--text-muted); padding: 20px;">No notifications</div>';
            return;
        }

        list.innerHTML = '';
        data.forEach(n => {
            const date = new Date(n.timestamp).toLocaleTimeString();
            const el = `
                <div class="notif-item type-${n.type}">
                    <span class="notif-time">${date}</span>
                    ${n.message}
                </div>
            `;
            list.insertAdjacentHTML('beforeend', el);
        });

    } catch (e) {
        console.error("Failed to fetch notifications");
    }
}

// Admin
async function fetchAdminInsights() {
    try {
        const res = await fetch(`${API_BASE_URL}/admin/insights`);
        const data = await res.json();
        
        document.getElementById('admin-total-claims').innerText = data.total_claims;
        document.getElementById('admin-approved-claims').innerText = data.approved_claims;
        document.getElementById('admin-warning-claims').innerText = data.warning_claims;
        document.getElementById('admin-rejected-claims').innerText = data.rejected_claims;
        
        const avgPerc = Math.round(data.average_risk_score * 100);
        document.getElementById('admin-avg-risk').innerText = `${avgPerc}%`;
        document.getElementById('admin-avg-risk-bar').style.width = `${avgPerc}%`;

    } catch (e) {
        console.error("Failed to load insights", e);
    }
}
