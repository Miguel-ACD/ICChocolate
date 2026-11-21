import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

// ====================================================================
// IMPORTANTE: cambia esta IP por la de tu PC en la LAN.
// Ejemplo: si tu PC tiene IP 192.168.18.244 y Docker expone el puerto
// 8003 en esa IP, entonces usa 'http://192.168.18.244:8003/api/mobile'
// ====================================================================
const API_BASE = 'http://192.168.18.126:8003/api/mobile';

const api = axios.create({ baseURL: API_BASE, timeout: 30000 });

export { api };

// Interceptor: si hay un JWT guardado, lo incluye automáticamente
api.interceptors.request.use(async (config) => {
  const token = await AsyncStorage.getItem('jwt_access');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * Login: obtiene JWT y lo guarda en AsyncStorage.
 */
export async function login(email, password) {
  const resp = await api.post('/token/', { username: email, password });
  const { access, refresh } = resp.data;
  await AsyncStorage.setItem('jwt_access', access);
  await AsyncStorage.setItem('jwt_refresh', refresh);
  return access;
}

/**
 * Logout: limpia tokens almacenados.
 */
export async function logout() {
  await AsyncStorage.multiRemove(['jwt_access', 'jwt_refresh']);
}

/**
 * Registra el Expo Push Token en el backend.
 */
export async function registerExpoPushToken(expoToken) {
  return api.post('/expo-token/', { token: expoToken });
}

/**
 * Obtiene datos completos de monitoreo para un sensor ESP32 seleccionado.
 */
export async function fetchMonitoring(deviceCode = null) {
  const params = deviceCode ? { device: deviceCode } : {};
  const resp = await api.get('/monitoring/', { params });
  return resp.data;
}

/**
 * Obtiene el resumen del dashboard (estadísticas, sensor en vivo, movimientos).
 */
export async function fetchDashboard() {
  const resp = await api.get('/dashboard/');
  return resp.data;
}

/**
 * Obtiene la lista de stock.
 */
export async function fetchStock() {
  const resp = await api.get('/stock/');
  return resp.data;
}

/**
 * Obtiene últimos movimientos.
 */
export async function fetchMovements() {
  const resp = await api.get('/movements/');
  return resp.data;
}

/**
 * Obtiene últimas lecturas de sensor.
 */
export async function fetchSensorReadings() {
  const resp = await api.get('/sensor-readings/');
  return resp.data;
}

/**
 * Obtiene las alertas.
 */
export async function fetchAlerts() {
  const resp = await api.get('/alerts/');
  return resp.data;
}

/**
 * Sube una foto y ejecuta el análisis Gemini Vision automáticamente.
 */
export async function uploadPhoto(imageUri, kind = 'BOLETA') {
  const form = new FormData();
  form.append('kind', kind);
  form.append('image', {
    uri: imageUri,
    name: 'photo.jpg',
    type: 'image/jpeg',
  });
  const resp = await api.post('/photos/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return resp.data;
}

/**
 * Catálogo completo para formularios (presentaciones, ubicaciones, equivalencias y tipos de movimiento).
 */
export async function fetchCatalog() {
  const resp = await api.get('/catalog/');
  return resp.data;
}

/**
 * Obtiene la lista de borradores pendientes de confirmación.
 */
export async function fetchDrafts() {
  const resp = await api.get('/drafts/');
  return resp.data;
}

/**
 * Crea un nuevo borrador de movimiento o conversión.
 */
export async function createDraft(payload) {
  const resp = await api.post('/drafts/', payload);
  return resp.data;
}

/**
 * Confirma un borrador existente aplicando los cambios al stock.
 */
export async function confirmDraft(draftId, version) {
  const resp = await api.post(`/drafts/${draftId}/confirm/`, { version });
  return resp.data;
}

/**
 * Cancela un borrador existente.
 */
export async function cancelDraft(draftId, version) {
  const resp = await api.post(`/drafts/${draftId}/cancel/`, { version });
  return resp.data;
}

/**
 * Confirma un movimiento registrado mediante fotografías y renglones.
 */
export async function confirmPhotoGroup(payload) {
  const resp = await api.post('/photo-confirm/', payload);
  return resp.data;
}

/**
 * Envía una pregunta al asistente de IA.
 */
export async function chatAsk(question, context) {
  const resp = await api.post('/chat/', { question, context });
  return resp.data;
}

export default api;
