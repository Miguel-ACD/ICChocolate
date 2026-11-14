import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, RefreshControl,
  TouchableOpacity, ActivityIndicator, Alert
} from 'react-native';
import { fetchMonitoring } from '../api';

function formatTime(isoString) {
  if (!isoString) return '--:--';
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return isoString;
  }
}

function formatDate(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('es-PE', { day: '2-digit', month: 'short' });
  } catch {
    return isoString;
  }
}

export default function MonitoringScreen() {
  const [data, setData] = useState(null);
  const [selectedDeviceCode, setSelectedDeviceCode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (deviceCode) => {
    try {
      setError('');
      const res = await fetchMonitoring(deviceCode);
      setData(res);
      if (!selectedDeviceCode && res.selected_device) {
        setSelectedDeviceCode(res.selected_device.code);
      }
    } catch (e) {
      console.warn('Error loading monitoring data:', e);
      setError('No se pudo conectar al servicio de sensores.');
    } finally {
      setLoading(false);
    }
  }, [selectedDeviceCode]);

  useEffect(() => {
    load(selectedDeviceCode);
  }, [selectedDeviceCode, load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load(selectedDeviceCode);
    setRefreshing(false);
  };

  const handleSelectDevice = (code) => {
    setSelectedDeviceCode(code);
    setLoading(true);
  };

  if (loading && !data) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#4a2c2a" />
        <Text style={styles.loadingText}>Cargando telemetría de sensores...</Text>
      </View>
    );
  }

  const status = data?.status || {};
  const currentTemp = status.latest_temp;
  const currentHum = status.latest_hum;
  const threshold = status.threshold_c || 10.0;
  const isOverThreshold = currentTemp !== null && currentTemp > threshold;
  const isFresh = status.fresh;
  const isCommunicating = status.communicating;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          colors={['#4a2c2a']}
          tintColor="#4a2c2a"
        />
      }
    >
      {/* Selector de Dispositivos / Sensores */}
      <View style={styles.selectorSection}>
        <Text style={styles.sectionTitle}>Dispositivo Sensor ESP32:</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.deviceRow}>
          {(data?.devices || []).map((dev) => {
            const isSelected = (selectedDeviceCode || data?.selected_device?.code) === dev.code;
            return (
              <TouchableOpacity
                key={dev.id}
                style={[styles.devicePill, isSelected && styles.devicePillActive]}
                onPress={() => handleSelectDevice(dev.code)}
              >
                <Text style={styles.deviceIcon}>📡</Text>
                <View>
                  <Text style={[styles.deviceCodeText, isSelected && styles.deviceCodeTextActive]}>
                    {dev.code}
                  </Text>
                  <Text style={[styles.deviceLocText, isSelected && styles.deviceLocTextActive]}>
                    {dev.location || 'Sin ubicación'}
                  </Text>
                </View>
                {isSelected && <Text style={styles.checkIcon}>✓</Text>}
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>⚠️ {error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => load(selectedDeviceCode)}>
            <Text style={styles.retryBtnText}>Reintentar</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* Tarjeta de Estado del Sensor Seleccionado */}
      <View style={styles.statusCard}>
        <View style={styles.statusHeader}>
          <View style={styles.deviceInfoCol}>
            <Text style={styles.deviceTitle}>
              Sensor {data?.selected_device?.code || 'ESP32'}
            </Text>
            <Text style={styles.deviceLocationSub}>
              📍 Ubicación: <Text style={styles.bold}>{data?.selected_device?.location || 'Almacén'}</Text>
            </Text>
          </View>
          <View style={[styles.onlineBadge, isCommunicating ? styles.badgeOnline : styles.badgeOffline]}>
            <Text style={[styles.onlineBadgeText, isCommunicating ? styles.badgeOnlineText : styles.badgeOfflineText]}>
              {isCommunicating ? '🟢 En Línea' : '🔴 Desconectado'}
            </Text>
          </View>
        </View>

        {/* Métricas Principales */}
        <View style={styles.metricsGrid}>
          {/* Tarjeta Temperatura */}
          <View style={[styles.metricBox, isOverThreshold ? styles.metricBoxAlert : styles.metricBoxSafe]}>
            <Text style={styles.metricLabel}>TEMPERATURA</Text>
            <View style={styles.metricValueRow}>
              <Text style={[styles.metricValue, isOverThreshold ? styles.metricValueAlert : styles.metricValueSafe]}>
                {currentTemp !== null ? `${Number(currentTemp).toFixed(1)}` : '--'}
              </Text>
              <Text style={styles.metricUnit}>°C</Text>
            </View>
            <View style={[styles.conditionPill, isOverThreshold ? styles.condAlertPill : styles.condSafePill]}>
              <Text style={[styles.conditionText, isOverThreshold ? styles.condAlertText : styles.condSafeText]}>
                {currentTemp === null
                  ? 'Sin lectura'
                  : isOverThreshold
                  ? `⚠️ > ${threshold}°C Alerta Calidad`
                  : `🛡️ ≤ ${threshold}°C Óptimo`}
              </Text>
            </View>
          </View>

          {/* Tarjeta Humedad */}
          <View style={[styles.metricBox, styles.metricBoxNeutral]}>
            <Text style={styles.metricLabel}>HUMEDAD DHT11</Text>
            <View style={styles.metricValueRow}>
              <Text style={styles.metricValue}>
                {currentHum !== null ? `${Number(currentHum).toFixed(1)}` : '--'}
              </Text>
              <Text style={styles.metricUnit}>%</Text>
            </View>
            <View style={[styles.conditionPill, styles.condNeutralPill]}>
              <Text style={styles.condNeutralText}>
                {currentHum !== null ? 'Humedad Relativa' : 'Sin lectura'}
              </Text>
            </View>
          </View>
        </View>

        {/* Información del Ciclo */}
        <View style={styles.cycleFooter}>
          <Text style={styles.cycleFooterText}>
            ⏱️ Última medición: {formatTime(status.latest_time)} ({formatDate(status.latest_time)})
          </Text>
          <Text style={styles.cycleFreshText}>
            {isFresh ? '⚡ Lectura reciente (< 3 min)' : '⏳ Lectura histórica (> 3 min)'}
          </Text>
        </View>
      </View>

      {/* Alerta de Derretimiento de Chocolate si aplica */}
      {isOverThreshold && (
        <View style={styles.alertBanner}>
          <Text style={styles.alertBannerIcon}>🚨</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.alertBannerTitle}>ALERTA DE TEMPERATURA CRÍTICA</Text>
            <Text style={styles.alertBannerMsg}>
              La temperatura en Almacén ({currentTemp}°C) supera el límite de {threshold}°C.
              Existe riesgo de derretimiento de chocolates. Verifica la refrigeración.
            </Text>
          </View>
        </View>
      )}

      {/* Tabla de Últimas 30 Mediciones */}
      <View style={styles.tableSection}>
        <View style={styles.tableHeaderRow}>
          <Text style={styles.tableTitle}>Últimas Mediciones del Ciclo</Text>
          <TouchableOpacity onPress={onRefresh} style={styles.btnSmallRefresh}>
            <Text style={styles.btnSmallRefreshText}>🔄 Actualizar</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.tableContainer}>
          {/* Encabezado de Columnas */}
          <View style={styles.tableColHeader}>
            <Text style={[styles.colHeadText, { flex: 1.2 }]}>Hora</Text>
            <Text style={[styles.colHeadText, { flex: 1.2 }]}>Temp</Text>
            <Text style={[styles.colHeadText, { flex: 1.2 }]}>Humedad</Text>
            <Text style={[styles.colHeadText, { flex: 1.1 }]}>Muestras</Text>
            <Text style={[styles.colHeadText, { flex: 1.3, textAlign: 'right' }]}>Estado</Text>
          </View>

          {/* Filas */}
          {(data?.readings || []).length === 0 ? (
            <View style={styles.emptyTable}>
              <Text style={styles.emptyTableText}>No hay ciclos de telemetría registrados aún.</Text>
            </View>
          ) : (
            (data?.readings || []).map((r, idx) => {
              const isValid = r.status === 'VALIDO';
              const isWarm = r.temperature_c !== null && r.temperature_c > threshold;
              return (
                <View key={r.id || idx} style={[styles.tableRow, idx % 2 === 1 && styles.tableRowAlt]}>
                  <Text style={[styles.colCellText, { flex: 1.2 }]}>
                    {formatTime(r.received_at)}
                  </Text>
                  <Text style={[styles.colCellText, { flex: 1.2, fontWeight: 'bold' }, isWarm && { color: '#c62828' }]}>
                    {r.temperature_c !== null ? `${Number(r.temperature_c).toFixed(1)}°C` : '--'}
                  </Text>
                  <Text style={[styles.colCellText, { flex: 1.2 }]}>
                    {r.humidity_percent !== null ? `${Number(r.humidity_percent).toFixed(1)}%` : '--'}
                  </Text>
                  <Text style={[styles.colCellText, { flex: 1.1, color: '#6d5a4d' }]}>
                    {r.valid_samples !== undefined ? `${r.valid_samples}/4` : '-'}
                  </Text>
                  <View style={[{ flex: 1.3, alignItems: 'flex-end' }]}>
                    <View style={[styles.miniStatusBadge, isValid ? styles.miniValid : styles.miniInvalid]}>
                      <Text style={[styles.miniStatusText, isValid ? styles.miniValidText : styles.miniInvalidText]}>
                        {isValid ? 'Válido' : 'Anómalo'}
                      </Text>
                    </View>
                  </View>
                </View>
              );
            })
          )}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  content: { padding: 16, paddingBottom: 36 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fdf6ec' },
  loadingText: { marginTop: 12, fontSize: 14, color: '#4a2c2a' },
  selectorSection: { marginBottom: 14 },
  sectionTitle: { fontSize: 13, fontWeight: '700', color: '#6d5a4d', marginBottom: 8, textTransform: 'uppercase' },
  deviceRow: { flexDirection: 'row' },
  devicePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderWidth: 1.5,
    borderColor: '#e2d3c2',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginRight: 10,
    shadowColor: '#4a2c2a',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 2,
    elevation: 1,
  },
  devicePillActive: {
    backgroundColor: '#4a2c2a',
    borderColor: '#4a2c2a',
  },
  deviceIcon: { fontSize: 20, marginRight: 8 },
  deviceCodeText: { fontSize: 14, fontWeight: 'bold', color: '#4a2c2a' },
  deviceCodeTextActive: { color: '#fff' },
  deviceLocText: { fontSize: 11, color: '#8c766b' },
  deviceLocTextActive: { color: '#f2e8dc' },
  checkIcon: { marginLeft: 8, fontSize: 14, color: '#4caf50', fontWeight: 'bold' },
  statusCard: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    borderWidth: 1,
    borderColor: '#ebdccb',
    shadowColor: '#4a2c2a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
    marginBottom: 16,
  },
  statusHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 14,
  },
  deviceInfoCol: { flex: 1 },
  deviceTitle: { fontSize: 18, fontWeight: 'bold', color: '#4a2c2a' },
  deviceLocationSub: { fontSize: 13, color: '#7a6658', marginTop: 2 },
  bold: { fontWeight: 'bold', color: '#4a2c2a' },
  onlineBadge: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
  },
  badgeOnline: { backgroundColor: '#e8f5e9' },
  badgeOffline: { backgroundColor: '#ffebee' },
  onlineBadgeText: { fontSize: 12, fontWeight: '700' },
  badgeOnlineText: { color: '#2e7d32' },
  badgeOfflineText: { color: '#c62828' },
  metricsGrid: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 14,
  },
  metricBox: {
    flex: 1,
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
  },
  metricBoxSafe: {
    backgroundColor: '#f1f8e9',
    borderColor: '#c8e6c9',
  },
  metricBoxAlert: {
    backgroundColor: '#ffebee',
    borderColor: '#ffcdd2',
  },
  metricBoxNeutral: {
    backgroundColor: '#f5f5f5',
    borderColor: '#e0e0e0',
  },
  metricLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#6d5a4d',
    marginBottom: 4,
    letterSpacing: 0.5,
  },
  metricValueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  metricValue: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#333',
  },
  metricValueSafe: {
    color: '#2e7d32',
  },
  metricValueAlert: {
    color: '#c62828',
  },
  metricUnit: {
    fontSize: 16,
    color: '#666',
    marginLeft: 3,
    fontWeight: '600',
  },
  conditionPill: {
    marginTop: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  condSafePill: { backgroundColor: '#c8e6c9' },
  condAlertPill: { backgroundColor: '#ffcdd2' },
  condNeutralPill: { backgroundColor: '#e0e0e0' },
  conditionText: { fontSize: 11, fontWeight: 'bold' },
  condSafeText: { color: '#1b5e20' },
  condAlertText: { color: '#b71c1c' },
  condNeutralText: { fontSize: 11, color: '#555', fontWeight: '600' },
  cycleFooter: {
    borderTopWidth: 1,
    borderTopColor: '#f5eee6',
    paddingTop: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cycleFooterText: { fontSize: 12, color: '#7a6658' },
  cycleFreshText: { fontSize: 11, color: '#8c766b', fontWeight: '600' },
  alertBanner: {
    backgroundColor: '#ffebee',
    borderColor: '#ef5350',
    borderWidth: 1.5,
    borderRadius: 12,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  alertBannerIcon: { fontSize: 28, marginRight: 12 },
  alertBannerTitle: { fontSize: 14, fontWeight: 'bold', color: '#c62828' },
  alertBannerMsg: { fontSize: 12, color: '#5c1d1d', marginTop: 2, lineHeight: 16 },
  tableSection: { marginTop: 4 },
  tableHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 10,
  },
  tableTitle: { fontSize: 15, fontWeight: 'bold', color: '#4a2c2a' },
  btnSmallRefresh: {
    backgroundColor: '#f5eee6',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e2d3c2',
  },
  btnSmallRefreshText: { fontSize: 12, fontWeight: '600', color: '#4a2c2a' },
  tableContainer: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    overflow: 'hidden',
  },
  tableColHeader: {
    flexDirection: 'row',
    backgroundColor: '#f5eee6',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#ede0d0',
  },
  colHeadText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#6d5a4d',
  },
  tableRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f8f4ee',
  },
  tableRowAlt: {
    backgroundColor: '#fdfbf9',
  },
  colCellText: {
    fontSize: 12,
    color: '#4a2c2a',
  },
  miniStatusBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  miniValid: { backgroundColor: '#e8f5e9' },
  miniInvalid: { backgroundColor: '#ffebee' },
  miniStatusText: { fontSize: 10, fontWeight: 'bold' },
  miniValidText: { color: '#2e7d32' },
  miniInvalidText: { color: '#c62828' },
  emptyTable: { padding: 24, alignItems: 'center' },
  emptyTableText: { fontSize: 13, color: '#9e8b7c' },
  errorBox: {
    backgroundColor: '#ffebee',
    padding: 12,
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  errorText: { color: '#c62828', fontSize: 13, flex: 1 },
  retryBtn: { backgroundColor: '#c62828', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  retryBtnText: { color: '#fff', fontSize: 12, fontWeight: 'bold' },
});

