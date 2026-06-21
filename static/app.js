// Check authentication on load
const token = localStorage.getItem("admin_token");
if (!token) {
    window.location.href = "/login";
}

// Config
const AUTO_REFRESH_INTERVAL = 5000; // 5 seconds
const API_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`
};

// Global variables
let salesChart = null;

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
    // Setup Logout
    document.getElementById("logoutBtn").addEventListener("click", () => {
        localStorage.removeItem("admin_token");
        window.location.href = "/login";
    });

    // Initial Fetch
    fetchDashboardData();

    // Start Polling Loop
    setInterval(fetchDashboardData, AUTO_REFRESH_INTERVAL);

    // Register Service Worker
    registerServiceWorker();
});

async function fetchDashboardData() {
    try {
        await Promise.all([
            loadStats(),
            loadOrders()
        ]);
    } catch (err) {
        console.error("Error fetching dashboard data:", err);
        // If unauthorized, redirect to login
        if (err.status === 401) {
            localStorage.removeItem("admin_token");
            window.location.href = "/login";
        }
    }
}

async function loadStats() {
    const response = await fetch("/api/stats", { headers: API_HEADERS });
    if (!response.ok) {
        if (response.status === 401) throw { status: 401 };
        throw new Error("Failed to load stats");
    }
    const data = await response.json();

    // Update Card Values
    document.getElementById("totalCustomers").textContent = data.total_customers.toLocaleString();
    document.getElementById("totalOrders").textContent = data.total_orders.toLocaleString();
    document.getElementById("totalRevenue").textContent = `${Math.round(data.total_revenue).toLocaleString().replace(/,/g, ' ')} so'm`;

    // Render Chart
    renderChart(data.chart_data);
}

function renderChart(chartData) {
    const ctx = document.getElementById('salesChart').getContext('2d');
    
    const labels = chartData.map(d => d.date);
    const revenues = chartData.map(d => d.revenue);
    const ordersCount = chartData.map(d => d.orders);

    if (salesChart) {
        // Update existing chart data
        salesChart.data.labels = labels;
        salesChart.data.datasets[0].data = revenues;
        salesChart.data.datasets[1].data = ordersCount;
        salesChart.update();
        return;
    }

    salesChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Savdo summasi (so'm)",
                    data: revenues,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    yAxisID: 'y_revenue',
                    tension: 0.3,
                    fill: true,
                    borderWidth: 3
                },
                {
                    label: "Buyurtmalar soni",
                    data: ordersCount,
                    borderColor: '#8b5cf6',
                    backgroundColor: 'transparent',
                    yAxisID: 'y_orders',
                    tension: 0.1,
                    borderWidth: 2,
                    borderDash: [5, 5]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#9ca3af', font: { family: 'Inter' } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af' }
                },
                y_revenue: {
                    type: 'linear',
                    position: 'left',
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { 
                        color: '#3b82f6',
                        callback: function(value) {
                            return value >= 1000 ? (value/1000) + 'k' : value;
                        }
                    }
                },
                y_orders: {
                    type: 'linear',
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#8b5cf6', stepSize: 1 }
                }
            }
        }
    });
}

async function loadOrders() {
    const response = await fetch("/api/orders", { headers: API_HEADERS });
    if (!response.ok) {
        if (response.status === 401) throw { status: 401 };
        throw new Error("Failed to load orders");
    }
    const orders = await response.json();
    const container = document.getElementById("ordersList");

    if (orders.length === 0) {
        container.innerHTML = `
            <div class="empty-state glass">
                <div class="empty-icon">📦</div>
                <p>Hozircha hech qanday buyurtma mavjud emas.</p>
            </div>
        `;
        return;
    }

    let html = "";
    orders.forEach(order => {
        const statusMap = {
            "pending": { text: "⏳ Kutilmoqda", class: "badge-pending" },
            "confirmed": { text: "✅ Tasdiqlangan", class: "badge-confirmed" },
            "completed": { text: "🚚 Yetkazilgan", class: "badge-completed" },
            "cancelled": { text: "❌ Bekor qilingan", class: "badge-cancelled" }
        };

        const statusInfo = statusMap[order.status] || { text: order.status, class: "" };
        
        // Google Maps auto-routing link using courier current position to target coordinates
        const mapsLink = `https://www.google.com/maps/dir/?api=1&destination=${order.latitude},${order.longitude}`;
        
        // Build items list html
        let itemsHtml = "";
        order.items.forEach(item => {
            const qtyUnit = item.product_name === "Malako" ? "dona" : "kg";
            itemsHtml += `
                <li>
                    <span>🥛 ${item.product_name}</span>
                    <strong>${item.quantity} ${qtyUnit} x ${item.price.toLocaleString()} so'm</strong>
                </li>
            `;
        });

        // Determine action buttons
        let actionsHtml = "";
        
        // "Yetib bordim" (Courier arrived) notification button, only for active/confirmed orders
        if (order.status === "confirmed") {
            actionsHtml += `<button class="action-btn btn-arrived" onclick="notifyArrived(${order.order_id})">🔔 Yetib bordim</button>`;
        }
        
        if (order.status === "pending") {
            actionsHtml += `<button class="action-btn btn-confirm" onclick="updateStatus(${order.order_id}, 'confirmed')">✅ Tasdiqlash</button>`;
        }
        
        if (order.status === "confirmed") {
            actionsHtml += `<button class="action-btn btn-complete" onclick="updateStatus(${order.order_id}, 'completed')">🚚 Yetkazildi</button>`;
        }
        
        if (order.status !== "completed" && order.status !== "cancelled") {
            actionsHtml += `<button class="action-btn btn-cancel" onclick="updateStatus(${order.order_id}, 'cancelled')">❌ Bekor qilish</button>`;
        }

        html += `
            <div class="order-card glass status-${order.status}">
                <div class="order-header">
                    <div class="order-title">
                        <h3>Buyurtma #${order.order_id}</h3>
                        <span class="order-date">${order.created_at}</span>
                    </div>
                    <span class="badge ${statusInfo.class}">${statusInfo.text}</span>
                </div>
                
                <div class="order-body">
                    <div class="info-group">
                        <div class="info-item" style="margin-bottom: 12px;">
                            <strong>Mijoz</strong>
                            ${order.full_name}
                        </div>
                        <div class="info-item" style="margin-bottom: 12px;">
                            <strong>Telefon raqami</strong>
                            <a href="tel:${order.phone_number}" style="color: var(--text-primary); text-decoration: none;">📞 ${order.phone_number}</a>
                        </div>
                        <div class="info-item">
                            <strong>Yetkazish manzili</strong>
                            <a href="${mapsLink}" target="_blank" class="route-link">🗺️ Google Maps (Marshrut)</a>
                        </div>
                    </div>
                    
                    <div class="info-group">
                        <div class="info-item" style="margin-bottom: 12px;">
                            <strong>Yetkazish vaqti</strong>
                            📅 ${order.delivery_date} | ⏰ ${order.delivery_time_start} - ${order.delivery_time_end}
                        </div>
                        <div class="info-item">
                            <strong>Buyurtma tarkibi</strong>
                            <div class="order-items-list">
                                <ul>${itemsHtml}</ul>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="order-footer">
                    <div class="total-price-label">Jami: ${Math.round(order.total_price).toLocaleString().replace(/,/g, ' ')} so'm</div>
                    <div class="order-actions">${actionsHtml}</div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

async function updateStatus(orderId, status) {
    if (!confirm(`Haqiqatan ham ushbu buyurtma holatini o'zgartirmoqchisiz?`)) return;

    try {
        const response = await fetch(`/api/orders/${orderId}/status`, {
            method: "POST",
            headers: API_HEADERS,
            body: JSON.stringify({ status })
        });
        if (response.ok) {
            fetchDashboardData();
        } else {
            alert("Xatolik yuz berdi. Holatni yangilab bo'lmadi.");
        }
    } catch (err) {
        console.error("Error updating order status:", err);
        alert("Server bilan bog'lanishda xatolik!");
    }
}

async function notifyArrived(orderId) {
    try {
        const response = await fetch(`/api/orders/${orderId}/arrived`, {
            method: "POST",
            headers: API_HEADERS
        });
        if (response.ok) {
            alert("Mijozga kuryer yetib kelgani haqida Telegram bildirishnomasi jo'natildi!");
        } else {
            alert("Xatolik yuz berdi. Xabarni yuborib bo'lmadi.");
        }
    } catch (err) {
        console.error("Error sending arrived notification:", err);
        alert("Server bilan bog'lanishda xatolik!");
    }
}

// Register PWA Service Worker
function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(reg => console.log('Service Worker registered successfully.', reg.scope))
                .catch(err => console.log('Service Worker registration failed: ', err));
        });
    }
}
