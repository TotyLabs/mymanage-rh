import { getMe, apiFetch, showToast, getApiBase } from '../common.js';

export async function render(container) {
    const me = await getMe();
    const user = me?.user || me;

    container.innerHTML = `
        <div class="container py-32">
            <div class="header-section mb-32">
                <h1 class="h2">Notificaciones</h1>
                <p class="text-slate-500">Gestioná la comunicación con tus empleados de forma centralizada.</p>
            </div>

            <div class="grid grid-cols-12 gap-32">
                <!-- Enviar Notificación -->
                <div class="col-span-12 lg:col-span-4">
                    <div class="card p-24">
                        <h3 class="h4 mb-16">Enviar Nueva Notificación</h3>
                        <form id="form-send-notif">
                            <div class="form-group mb-16">
                                <label class="label mb-8">Seleccionar Empleados</label>
                                <button type="button" class="btn btn-secondary btn-block" id="btn-open-emp-modal">Seleccionar Empleados (0)</button>
                                <input type="hidden" id="recipient-ids">
                            </div>
                            <div class="form-group mb-16">
                                <label class="label mb-8">Mensaje</label>
                                <textarea id="notif-message" class="input" rows="4" placeholder="Escribí tu mensaje acá..." required></textarea>
                            </div>
                            <div class="form-group mb-24">
                                <label class="label mb-8">Adjuntar Archivo (opcional)</label>
                                <input type="file" id="notif-file" class="input">
                            </div>
                            <button type="submit" class="btn btn-primary btn-block" id="btn-submit">
                                Enviar Notificación
                            </button>
                        </form>
                    </div>
                </div>

                <!-- Lista de Notificaciones -->
                <div class="col-span-12 lg:col-span-8">
                    <div class="card">
                        <div class="card-header p-24 flex items-center border-b">
                            <h3 class="h4">Bandeja de Entrada</h3>
                            <div style="flex: 1;"></div>
                            <button class="btn btn-secondary btn-sm" id="btn-refresh">Actualizar</button>
                        </div>
                        <div id="notifications-list" class="divide-y" style="height: 500px; overflow-y: scroll; background: #fafafa;">
                            <div class="p-48 text-center text-slate-400">
                                <div class="spinner mb-16"></div>
                                Cargando notificaciones...
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modal Seleccionar Empleados -->
        <div id="modalSelectEmps" class="modal hidden">
            <div class="modal-content" style="max-width: 500px;">
                <div class="modal-header">
                    <h3 class="h4">Seleccionar Destinatarios</h3>
                    <button class="btn-close" id="btn-close-emp-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <input type="text" id="search-emps" class="input mb-16" placeholder="Buscar por nombre o DNI...">
                    <div id="emps-checklist" class="border rounded p-16" style="max-height: 300px; overflow-y: auto;">
                        <div class="text-center text-slate-400">Cargando empleados...</div>
                    </div>
                </div>
                <div class="modal-footer flex justify-between">
                    <div>
                        <button type="button" class="btn btn-ghost btn-sm" id="btn-sel-all">Todos</button>
                        <button type="button" class="btn btn-ghost btn-sm" id="btn-sel-none">Ninguno</button>
                    </div>
                    <button type="button" class="btn btn-primary" id="btn-accept-emps">Aceptar</button>
                </div>
            </div>
        </div>
    `;

    // Initialize logic directly in render
    loadEmployees();
    loadNotifications();

    container.querySelector('#btn-refresh').onclick = loadNotifications;

    const modalSelectEmps = container.querySelector('#modalSelectEmps');
    
    container.querySelector('#btn-open-emp-modal').onclick = () => {
        modalSelectEmps.classList.remove('hidden');
        renderEmployeesChecklist(container.querySelector('#search-emps').value);
    };
    
    container.querySelector('#btn-close-emp-modal').onclick = () => modalSelectEmps.classList.add('hidden');
    container.querySelector('#btn-accept-emps').onclick = () => modalSelectEmps.classList.add('hidden');
    
    container.querySelector('#search-emps').addEventListener('input', (e) => {
        renderEmployeesChecklist(e.target.value);
    });

    container.querySelector('#btn-sel-all').onclick = () => {
        allEmployees.forEach(emp => selectedEmployees.add(emp.user_id || emp.id));
        renderEmployeesChecklist(container.querySelector('#search-emps').value);
        updateSelectionBtn();
    };

    container.querySelector('#btn-sel-none').onclick = () => {
        selectedEmployees.clear();
        renderEmployeesChecklist(container.querySelector('#search-emps').value);
        updateSelectionBtn();
    };

    container.querySelector('#form-send-notif').onsubmit = async (e) => {
        e.preventDefault();
        const btn = container.querySelector('#btn-submit');
        const message = container.querySelector('#notif-message').value;
        const recipientIds = container.querySelector('#recipient-ids').value;
        const fileInput = container.querySelector('#notif-file');

        if (!recipientIds) return showToast('Seleccioná al menos un empleado', 'error');

        btn.disabled = true;
        btn.textContent = 'Enviando...';

        try {
            const formData = new FormData();
            formData.append('message', message);
            formData.append('recipient_ids', recipientIds);
            if (fileInput.files[0]) {
                formData.append('file', fileInput.files[0]);
            }

            const res = await fetch('/api/notifications', {
                method: 'POST',
                headers: { 
                    'Authorization': `Bearer ${localStorage.getItem('token')}`,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            });

            const data = await res.json();
            if (data.status === 'ok') {
                showToast('Notificación enviada con éxito');
                container.querySelector('#form-send-notif').reset();
                selectedEmployees.clear();
                updateSelectionBtn();
                loadNotifications();
            } else {
                showToast(data.detail || 'Error al enviar', 'error');
            }
        } catch (error) {
            console.error(error);
            showToast('Error de conexión', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Enviar Notificación';
        }
    };
}

let allEmployees = [];
let selectedEmployees = new Set();

async function loadEmployees() {
    try {
        const data = await apiFetch('/api/employees');
        const list = document.getElementById('emps-checklist');
        if (!list) return;
        
        allEmployees = data.employees.filter(emp => !emp.is_deleted);
        renderEmployeesChecklist();
    } catch (e) {
        console.error(e);
    }
}

function renderEmployeesChecklist(filterText = '') {
    const list = document.getElementById('emps-checklist');
    if (!list) return;
    
    list.innerHTML = '';
    const term = filterText.toLowerCase();
    const filtered = allEmployees.filter(emp => 
        emp.first_name.toLowerCase().includes(term) || 
        emp.last_name.toLowerCase().includes(term) || 
        (emp.dni && emp.dni.includes(term))
    );
    
    if (filtered.length === 0) {
        list.innerHTML = '<div class="text-center text-slate-400">No hay resultados.</div>';
        return;
    }
    
    filtered.forEach(emp => {
        const val = emp.user_id || emp.id;
        const div = document.createElement('div');
        div.className = 'flex items-center mb-8';
        const checked = selectedEmployees.has(val) ? 'checked' : '';
        div.innerHTML = `
            <input type="checkbox" id="emp-${val}" value="${val}" class="mr-8 emp-checkbox" ${checked}>
            <label for="emp-${val}" class="cursor-pointer select-none">
                ${emp.first_name} ${emp.last_name} (${emp.dni}) ${emp.has_account ? '' : '<span class="text-xs text-slate-400">(Sin cuenta)</span>'}
            </label>
        `;
        list.appendChild(div);
    });
    
    list.querySelectorAll('.emp-checkbox').forEach(cb => {
        cb.addEventListener('change', (e) => {
            if (e.target.checked) selectedEmployees.add(e.target.value);
            else selectedEmployees.delete(e.target.value);
            updateSelectionBtn();
        });
    });
}

function updateSelectionBtn() {
    const btn = document.getElementById('btn-open-emp-modal');
    const input = document.getElementById('recipient-ids');
    if (btn && input) {
        btn.textContent = `Seleccionar Empleados (${selectedEmployees.size})`;
        input.value = Array.from(selectedEmployees).join(',');
    }
}

async function loadNotifications() {
    const list = document.getElementById('notifications-list');
    if (!list) return;

    try {
        const data = await apiFetch('/api/notifications');
        if (data.notifications.length === 0) {
            list.innerHTML = '<div class="p-48 text-center text-slate-400">No hay notificaciones registradas.</div>';
            return;
        }

        list.innerHTML = '';
        data.notifications.forEach(n => {
            const item = document.createElement('div');
            item.className = `notification-item ${n.is_read ? '' : 'unread'}`;
            
            const date = new Date(n.created_at).toLocaleString();
            const directionLabel = n.direction === 'inbound' ? 
                `<span class="badge badge-info mr-8">RECIBIDO</span> De: <strong>${n.sender_name}</strong>` : 
                `<span class="badge badge-success mr-8">ENVIADO</span> Para: <strong>${n.recipient_name}</strong>`;

            item.innerHTML = `
                <div class="flex-1" onclick="markAsRead('${n.id}')">
                    <div class="flex items-center mb-4">
                        ${n.is_read ? '' : '<span class="unread-dot"></span>'}
                        ${directionLabel}
                    </div>
                    <div class="text-slate-700 mb-8">${n.message}</div>
                    <div class="notification-meta">
                        ${date} 
                        ${n.has_file ? `| <a href="/api/notifications/${n.id}/file" target="_blank" class="text-brand-600 font-medium">📎 Ver adjunto</a>` : ''}
                    </div>
                </div>
                <div class="notification-actions">
                    <button class="btn-delete-notif" onclick="deleteNotif('${n.id}')" title="Eliminar">
                        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"></path></svg>
                    </button>
                </div>
            `;
            list.appendChild(item);
        });
    } catch (e) {
        list.innerHTML = '<div class="p-48 text-center text-error">Error al cargar notificaciones.</div>';
    }
}

window.deleteNotif = async (id) => {
    if (!confirm('¿Seguro que querés eliminar esta notificación?')) return;
    try {
        await apiFetch(`/api/notifications/${id}`, { method: 'DELETE' });
        
        // Refresh UI
        try {
            await loadNotifications();
            if (window.updateNotificationBadges) {
                await updateNotificationBadges();
            }
        } catch (secondaryError) {
            console.warn('UI Refresh warning:', secondaryError);
        }
        
        showToast('Notificación eliminada', 'success');
    } catch (e) {
        console.error('Delete error:', e);
        showToast('Error al eliminar', 'error');
    }
};

window.markAsRead = async (id) => {
    try {
        await apiFetch(`/api/notifications/${id}/read`, { method: 'POST' });
        
        try {
            await loadNotifications();
            if (window.updateNotificationBadges) {
                await updateNotificationBadges();
            }
        } catch (secondaryError) {
            console.warn('UI Refresh warning:', secondaryError);
        }
    } catch (e) {
        console.error('Mark as read error:', e);
    }
};
