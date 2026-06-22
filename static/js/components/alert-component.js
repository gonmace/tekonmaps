/**
 * Alert Component - Reutilizable para múltiples aplicaciones
 * Componente para mostrar alertas usando DaisyUI
 */

class Alert {
    constructor() {
        this.alertContainer = null;
        this.initialized = false;
        this.pendingAlerts = [];
        this.confirmCallbacks = {};
    }

    init() {
        // Verificar que el DOM esté listo
        if (!document.body) {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.init());
                return;
            }
        }

        // Crear contenedor de alertas si no existe (toast DaisyUI top-end)
        if (!document.getElementById('alerts-container')) {
            this.alertContainer = document.createElement('div');
            this.alertContainer.id = 'alerts-container';
            this.alertContainer.className = 'toast toast-top toast-end z-[9999]';
            document.body.appendChild(this.alertContainer);
        } else {
            this.alertContainer = document.getElementById('alerts-container');
        }

        this.initialized = true;
        console.log('Alert component initialized');

        // Procesar alertas pendientes
        this.pendingAlerts.forEach(alert => {
            this.show(alert.message, alert.type, alert.options);
        });
        this.pendingAlerts = [];
    }

    _getEffectiveContainer() {
        const openDialog = document.querySelector('dialog[open]');
        if (openDialog) {
            let container = openDialog.querySelector('#alerts-container-modal');
            if (!container) {
                container = document.createElement('div');
                container.id = 'alerts-container-modal';
                container.className = 'toast toast-top toast-end z-[9999]';
                openDialog.appendChild(container);
            }
            return container;
        }
        return this.alertContainer;
    }

    /**
     * Muestra una alerta
     * @param {string} message - Mensaje a mostrar
     * @param {string} type - Tipo de alerta: 'success', 'error', 'warning', 'info'
     * @param {object} options - Opciones adicionales
     */
    show(message, type = 'info', options = {}) {
        // Si no está inicializado, guardar la alerta para procesarla después
        if (!this.initialized) {
            this.pendingAlerts.push({ message, type, options });
            this.init();
            return `pending-${Date.now()}`;
        }

        const {
            autoHide = 0,
            id = `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            dismissible = true,
            icon = this.getDefaultIcon(type)
        } = options;

        console.log('Creating alert:', { id, type, message, dismissible });

        // Mapeo a clases DaisyUI alert-* (estilizadas con Cupertino en styles.css)
        const validTypes = ['success', 'error', 'warning', 'info'];
        const alertType = validTypes.includes(type) ? type : 'info';

        // Crear elemento de alerta
        const alertElement = document.createElement('div');
        alertElement.id = id;
        alertElement.className = `alert alert-${alertType}`;

        // Contenido de la alerta
        alertElement.innerHTML = `
            ${icon ? `<i class="${icon} text-base"></i>` : ''}
            <span class="flex-1 text-sm font-medium">${message}</span>
            ${dismissible ? `
                <button type="button" class="alert-close-btn text-base-content/50 hover:text-base-content transition-colors ml-2" data-alert-id="${id}">
                    <i class="fa-solid fa-xmark text-xs"></i>
                </button>
            ` : ''}
        `;

        // Agregar event listener para el botón de cerrar
        if (dismissible) {
            const closeBtn = alertElement.querySelector('.alert-close-btn');
            if (closeBtn) {
                console.log('Adding close button listener for alert:', id);
                closeBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    console.log('Close button clicked for alert:', id);
                    this.hide(id);
                });
                
                // También agregar listener para hacer clic en el botón completo
                closeBtn.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                });
            } else {
                console.error('Close button not found for alert:', id);
            }
        }

        // Agregar animación de entrada
        alertElement.style.opacity = '0';
        alertElement.style.transform = 'translateX(100%)';
        alertElement.style.transition = 'all 0.3s ease-in-out';

        // Agregar al contenedor (dentro del dialog abierto si existe)
        this._getEffectiveContainer().appendChild(alertElement);

        // Animar entrada
        setTimeout(() => {
            alertElement.style.opacity = '1';
            alertElement.style.transform = 'translateX(0)';
        }, 10);

        // Auto-ocultar si está configurado
        if (autoHide > 0) {
            setTimeout(() => {
                this.hide(id);
            }, autoHide);
        }

        return id;
    }

    /**
     * Oculta una alerta específica
     * @param {string} id - ID de la alerta a ocultar
     */
    hide(id) {
        console.log('Hiding alert:', id);
        const alertElement = document.getElementById(id);
        if (alertElement) {
            console.log('Alert element found, starting hide animation');
            // Animar salida
            alertElement.style.opacity = '0';
            alertElement.style.transform = 'translateX(100%)';
            
            setTimeout(() => {
                if (alertElement.parentNode) {
                    console.log('Removing alert element from DOM');
                    alertElement.parentNode.removeChild(alertElement);
                }
            }, 300);
        } else {
            console.error('Alert element not found for ID:', id);
        }
    }

    /**
     * Oculta todas las alertas
     */
    hideAll() {
        console.log('Hiding all alerts');
        const alerts = this.alertContainer.querySelectorAll('[id^="alert-"]');
        alerts.forEach(alert => {
            this.hide(alert.id);
        });
    }

    /**
     * Muestra una alerta de éxito
     * @param {string} message - Mensaje a mostrar
     * @param {object} options - Opciones adicionales
     */
    success(message, options = {}) {
        return this.show(message, 'success', options);
    }

    /**
     * Muestra una alerta de error
     * @param {string} message - Mensaje a mostrar
     * @param {object} options - Opciones adicionales
     */
    error(message, options = {}) {
        return this.show(message, 'error', options);
    }

    /**
     * Muestra una alerta de advertencia
     * @param {string} message - Mensaje a mostrar
     * @param {object} options - Opciones adicionales
     */
    warning(message, options = {}) {
        return this.show(message, 'warning', options);
    }

    /**
     * Muestra una alerta informativa
     * @param {string} message - Mensaje a mostrar
     * @param {object} options - Opciones adicionales
     */
    info(message, options = {}) {
        return this.show(message, 'info', options);
    }

    /**
     * Obtiene el icono por defecto según el tipo
     * @param {string} type - Tipo de alerta
     * @returns {string} Clase del icono
     */
    getDefaultIcon(type) {
        const icons = {
            success: 'fa-solid fa-check-circle',
            error: 'fa-solid fa-exclamation-circle',
            warning: 'fa-solid fa-triangle-exclamation',
            info: 'fa-solid fa-circle-info'
        };
        return icons[type] || icons.info;
    }

    /**
     * Muestra una alerta de confirmación
     * @param {string} message - Mensaje a mostrar
     * @param {function} onConfirm - Función a ejecutar si se confirma
     * @param {function} onCancel - Función a ejecutar si se cancela
     * @param {object} options - Opciones adicionales
     */
    confirm(message, onConfirm, onCancel = null, options = {}) {
        if (!this.initialized) {
            this.init();
        }
        const {
            id = `confirm-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
            title = 'Confirmar',
            confirmText = 'Confirmar',
            cancelText = 'Cancelar',
            type = 'warning',                 // alert color: warning | error | info | success
            confirmClass = 'btn-save',        // semantic button class for the confirm action
            icon = 'fa-solid fa-circle-question',
        } = options;

        const validTypes = ['success', 'error', 'warning', 'info'];
        const alertType = validTypes.includes(type) ? type : 'warning';

        const confirmElement = document.createElement('div');
        confirmElement.id = id;
        confirmElement.className = `alert alert-${alertType}`;

        confirmElement.innerHTML = `
            <i class="${icon} text-base self-start mt-0.5"></i>
            <div class="flex-1">
                <h4 class="text-sm font-semibold mb-1">${title}</h4>
                <p class="text-sm mb-3">${message}</p>
                <div class="flex gap-2">
                    <button type="button" class="btn btn-sm ${confirmClass} confirm-btn" data-confirm-id="${id}" data-confirmed="true">
                        ${confirmText}
                    </button>
                    <button type="button" class="btn btn-sm btn-cancel confirm-btn" data-confirm-id="${id}" data-confirmed="false">
                        ${cancelText}
                    </button>
                </div>
            </div>
        `;

        // Agregar event listeners para los botones de confirmación
        const confirmBtns = confirmElement.querySelectorAll('.confirm-btn');
        confirmBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                const confirmed = btn.getAttribute('data-confirmed') === 'true';
                this.handleConfirm(id, confirmed);
            });
        });

        // Guardar callbacks
        this.confirmCallbacks[id] = { onConfirm, onCancel };

        // Agregar al contenedor (dentro del dialog abierto si existe)
        this._getEffectiveContainer().appendChild(confirmElement);

        // Animar entrada
        confirmElement.style.opacity = '0';
        confirmElement.style.transform = 'translateX(100%)';
        confirmElement.style.transition = 'all 0.3s ease-in-out';

        setTimeout(() => {
            confirmElement.style.opacity = '1';
            confirmElement.style.transform = 'translateX(0)';
        }, 10);

        return id;
    }

    /**
     * Maneja la respuesta de confirmación
     * @param {string} id - ID del elemento de confirmación
     * @param {boolean} confirmed - Si se confirmó o no
     */
    handleConfirm(id, confirmed) {
        const callbacks = this.confirmCallbacks[id];
        if (callbacks) {
            if (confirmed && callbacks.onConfirm) {
                callbacks.onConfirm();
            } else if (!confirmed && callbacks.onCancel) {
                callbacks.onCancel();
            }
            delete this.confirmCallbacks[id];
        }
        this.hide(id);
    }
}

// Crear instancia global
window.Alert = new Alert();

// Inicializar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.Alert.init();
    });
} else {
    window.Alert.init();
} 