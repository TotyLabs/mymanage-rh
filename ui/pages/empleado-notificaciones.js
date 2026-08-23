import { getMe, apiFetch, showToast } from '../common.js';

export async function render(container) {
    container.innerHTML = `
        <div class="container py-32">
            <div class="header-section mb-32">
                <h1 class="h2">Centro de Notificaciones</h1>
                <p class="text-slate-500">Comunicación directa con la empresa.</p>
            </div>

            <div class="grid grid-cols-12 gap-32">
                <!-- Enviar Notificación a la Empresa -->
                <div class="col-span-12 lg:col-span-4">
                    <div class="card p-24">
                        <h3 class="h4 mb-16">Enviar Mensaje a la Empresa</h3>
                        <form id="form-send-notif">
                            <div class="form-group mb-16">
                                <label class="label mb-8">Mensaje</label>
                                <textarea id="notif-message" class="input" rows="5" placeholder="Escribí tu consulta o mensaje acá..." required></textarea>
                            </div>
                            <div class="form-group mb-24">
                                <label class="label mb-8">Adjuntar Archivo (opcional)</label>
                                <input type="file" id="notif-file" class="input">
                                <p class="text-slate-400 text-xs mt-4">Podés adjuntar fotos o documentos relevantes.</p>
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
                            <h3 class="h4">Mis Mensajes</h3>
                            <div style="flex: 1;"></div>
                            <button class="btn btn-secondary btn-sm" id="btn-refresh">Actualizar</button>
                        </div>
                        <div id="notifications-list" class="divide-y" style="height: 500px; overflow-y: scroll; background: #fafafa;">
                            <div class="p-48 text-center text-slate-400">
                                <div class="spinner mb-16"></div>
                                Cargando tus mensajes...
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Init logic
    loadNotifications();

    container.querySelector('#btn-refresh').onclick = loadNotifications;

    container.querySelector('#form-send-notif').onsubmit = async (e) => {
        e.preventDefault();
        const btn = container.querySelector('#btn-submit');
        const message = container.querySelector('#notif-message').value;
        const fileInput = container.querySelector('#notif-file');

        btn.disabled = true;
        btn.textContent = 'Enviando...';

        try {
            const formData = new FormData();
            formData.append('message', message);
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
                showToast('Mensaje enviado con éxito');
                container.querySelector('#form-send-notif').reset();
                loadNotifications();
            } else {
                showToast(data.detail || 'Error al enviar', 'error');
            }
        } catch (error) {
            showToast('Error de conexión', 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = 'Enviar Notificación';
        }
    };
}

async function loadNotifications() {
    const list = document.getElementById('notifications-list');
    if (!list) return;

    try {
        const data = await apiFetch('/api/notifications');
        if (data.notifications.length === 0) {
            list.innerHTML = '<div class="p-48 text-center text-slate-400">Todavía no tenés mensajes.</div>';
            return;
        }

        list.innerHTML = '';
        data.notifications.forEach(n => {
            const item = document.createElement('div');
            item.className = `notification-item ${n.is_read ? '' : 'unread'}`;
            
            const date = new Date(n.created_at).toLocaleString();
            const directionLabel = n.direction === 'inbound' ? 
                `<span class="badge badge-info mr-8">RECIBIDO</span> De: <strong>RRHH / Empresa</strong>` : 
                `<span class="badge badge-success mr-8">ENVIADO</span> Para: <strong>Empresa</strong>`;

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
        list.innerHTML = '<div class="p-48 text-center text-error">Error al cargar mensajes.</div>';
    }
}

window.deleteNotif = async (id) => {
    if (!confirm('¿Seguro que querés eliminar este mensaje?')) return;
    try {
        await apiFetch(`/api/notifications/${id}`, { method: 'DELETE' });
        loadNotifications();
        if (window.updateNotificationBadges) window.updateNotificationBadges();
    } catch (e) {
        showToast('Error al eliminar', 'error');
    }
};

window.markAsRead = async (id) => {
    try {
        await apiFetch(`/api/notifications/${id}/read`, { method: 'POST' });
        loadNotifications();
        if (window.updateNotificationBadges) window.updateNotificationBadges();
    } catch (e) {}
};
