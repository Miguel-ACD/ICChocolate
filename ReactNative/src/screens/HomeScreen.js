import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  RefreshControl, ActivityIndicator,
} from 'react-native';
import * as Location from 'expo-location';
import { fetchDashboard } from '../api';
import { useAuth } from '../context/AuthContext';
import { sendLocalNotification } from '../notifications';

export default function HomeScreen({ navigation }) {
  const { user, logout } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [storeAddress, setStoreAddress] = useState('Detectando dirección de la tienda…');

  const loadData = useCallback(async () => {
    try {
      const result = await fetchDashboard();
      setData(result);
      // Si la temperatura supera 10 °C, lanzar notificación local
      if (result?.sensor?.is_alert) {
        sendLocalNotification(
          '⚠️ ALERTA TÉRMICA: Chocolate en riesgo',
          `Temperatura en ${result.sensor.location}: ${result.sensor.temperature_c.toFixed(1)} °C (supera umbral de 10 °C)`
        );
      }
    } catch (e) {
      console.warn('Error fetching dashboard:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Obtener solo la dirección física para saber en qué tienda/sucursal se encuentra
  const detectStoreAddress = useCallback(async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        const geocoded = await Location.reverseGeocodeAsync({
          latitude: loc.coords.latitude,
          longitude: loc.coords.longitude,
        });
        if (geocoded && geocoded.length > 0) {
          const addr = geocoded[0];
          const parts = [
            [addr.street, addr.streetNumber].filter(Boolean).join(' ') || addr.name,
            addr.district || addr.subregion,
            addr.city || addr.region,
          ].filter(Boolean);
          setStoreAddress(parts.join(', ') || 'Sede Principal');
        } else {
          setStoreAddress('Sede Principal (Almacén Central)');
        }
      } else {
        setStoreAddress('Sede Principal (Permiso de ubicación no activo)');
      }
    } catch {
      setStoreAddress('Sede Principal (Almacén Central)');
    }
  }, []);

  useEffect(() => {
    loadData();
    detectStoreAddress();
  }, [loadData, detectStoreAddress]);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([loadData(), detectStoreAddress()]);
    setRefreshing(false);
  };

  const sensor = data?.sensor;
  const stats = data?.stats;

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {/* Encabezado: Saludo y Cerrar sesión */}
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>Hola, {user?.alias || 'Usuario'} 👋</Text>
          <Text style={styles.roleBadge}>
            {user?.role === 'DUENO' ? '👑 Dueño' : '👤 Empleado'} • ICChocolate
          </Text>
        </View>
        <TouchableOpacity style={styles.btnLogout} onPress={logout}>
          <Text style={styles.btnLogoutText}>Cerrar sesión</Text>
        </TouchableOpacity>
      </View>

      {/* Tarjeta de Tienda / Dirección Actual */}
      <View style={styles.storeCard}>
        <Text style={styles.storeCardLabel}>🏪 TIENDA / SEDE DETECTADA</Text>
        <Text style={styles.storeAddress}>{storeAddress}</Text>
        <Text style={styles.storeHint}>Verificación de punto de venta activo para inventario</Text>
      </View>

      {/* Monitoreo Crítico del Sensor (DHT11 - ESP32) */}
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={() => navigation.navigate('Monitoring')}
        style={[styles.sensorCard, sensor?.is_alert ? styles.sensorAlert : styles.sensorNormal]}
      >
        <View style={styles.sensorHeader}>
          <Text style={styles.sensorTitle}>🌡️ Temperatura Actual ({sensor?.location || 'Almacén'})</Text>
          <View style={[styles.badge, sensor?.is_alert ? styles.badgeAlert : styles.badgeNormal]}>
            <Text style={[styles.badgeText, sensor?.is_alert && { color: '#c62828' }]}>
              {sensor?.is_alert ? '🔴 ALERTA TÉRMICA (> 10°C)' : '🟢 ÓPTIMA (< 10°C)'}
            </Text>
          </View>
        </View>

        {sensor ? (
          <View style={styles.sensorMetrics}>
            <View style={styles.metricItem}>
              <Text style={[styles.metricVal, sensor.is_alert && { color: '#c62828' }]}>
                {sensor.temperature_c !== null ? `${sensor.temperature_c.toFixed(1)} °C` : '--'}
              </Text>
              <Text style={styles.metricLbl}>Medición en vivo (Toca para monitoreo)</Text>
            </View>
            <View style={styles.metricDivider} />
            <View style={styles.metricItem}>
              <Text style={styles.metricVal}>
                {sensor.humidity_percent !== null ? `${sensor.humidity_percent.toFixed(1)} %` : '--'}
              </Text>
              <Text style={styles.metricLbl}>Humedad relativa</Text>
            </View>
          </View>
        ) : (
          <Text style={styles.noSensor}>Conectando con el sensor ESP32…</Text>
        )}
      </TouchableOpacity>

      {/* Resumen de Existencias */}
      <Text style={styles.sectionTitle}>Estado del Inventario</Text>
      <View style={styles.statsGrid}>
        <View style={styles.statBox}>
          <Text style={styles.statIcon}>📦</Text>
          <Text style={styles.statVal}>{stats?.total_units || 0}</Text>
          <Text style={styles.statLbl}>Unidades en Stock</Text>
        </View>

        <View style={styles.statBox}>
          <Text style={styles.statIcon}>🍫</Text>
          <Text style={styles.statVal}>{stats?.products_count || 0}</Text>
          <Text style={styles.statLbl}>Productos Activos</Text>
        </View>

        <View style={styles.statBox}>
          <Text style={styles.statIcon}>📍</Text>
          <Text style={styles.statVal}>{stats?.positions_count || 0}</Text>
          <Text style={styles.statLbl}>Ubicaciones de Stock</Text>
        </View>
      </View>

      {/* Acciones Esenciales del Negocio */}
      <Text style={styles.sectionTitle}>Operaciones del Negocio</Text>
      <View style={styles.actionsList}>
        {/* Acción 1: Registrar con Cámara */}
        <TouchableOpacity
          style={styles.actionBtnPrimary}
          onPress={() => navigation.navigate('Camera')}
        >
          <Text style={styles.actionEmoji}>📸</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.actionTitlePrimary}>Registrar con Fotos (Cámara IA)</Text>
            <Text style={styles.actionSubPrimary}>Fotografía boletas o etiquetas para ingreso rápido con Gemini</Text>
          </View>
          <Text style={styles.actionArrowPrimary}>❯</Text>
        </TouchableOpacity>

        {/* Acción 2: Consultar Stock */}
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('Stock')}
        >
          <Text style={styles.actionEmoji}>📋</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.actionTitle}>Consultar Inventario por Presentación</Text>
            <Text style={styles.actionSub}>Barras, cajas, polvo y chispas en Almacén y Display</Text>
          </View>
          <Text style={styles.actionArrow}>❯</Text>
        </TouchableOpacity>

        {/* Acción 3: Asistente IA */}
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('Chat')}
        >
          <Text style={styles.actionEmoji}>💬</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.actionTitle}>Consultar al Asistente de IA</Text>
            <Text style={styles.actionSub}>Pregunta por existencias o dudas en lenguaje natural</Text>
          </View>
          <Text style={styles.actionArrow}>❯</Text>
        </TouchableOpacity>

        {/* Acción 4: Consola Web */}
        <TouchableOpacity
          style={styles.actionBtn}
          onPress={() => navigation.navigate('Web')}
        >
          <Text style={styles.actionEmoji}>🌐</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.actionTitle}>Consola Web Administrativa</Text>
            <Text style={styles.actionSub}>Conversiones, equivalencias y administración completa</Text>
          </View>
          <Text style={styles.actionArrow}>❯</Text>
        </TouchableOpacity>
      </View>

      {/* Historial Reciente */}
      {data?.recent_movements && data.recent_movements.length > 0 && (
        <View style={styles.movementsSection}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text style={styles.sectionTitle}>Últimos Movimientos</Text>
            <TouchableOpacity onPress={() => navigation.navigate('History')}>
              <Text style={{ fontSize: 13, color: '#4a2c2a', fontWeight: 'bold' }}>Ver todos ›</Text>
            </TouchableOpacity>
          </View>
          {data.recent_movements.map((m) => (
            <View key={m.id} style={styles.movementItem}>
              <View style={styles.movementHeader}>
                <Text style={styles.movementType}>📝 {m.type_label}</Text>
                <Text style={styles.movementAuthor}>{m.author}</Text>
              </View>
              <Text style={styles.movementDetail} numberOfLines={2}>{m.lines_summary}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, backgroundColor: '#fdf6ec', padding: 16 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  greeting: { fontSize: 22, fontWeight: 'bold', color: '#4a2c2a' },
  roleBadge: { fontSize: 13, color: '#8b6f5e', marginTop: 2 },
  btnLogout: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d4c4a8',
    borderRadius: 8,
  },
  btnLogoutText: { color: '#8b6f5e', fontSize: 12, fontWeight: 'bold' },
  storeCard: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    marginBottom: 14,
    borderLeftWidth: 5,
    borderLeftColor: '#4a2c2a',
    elevation: 1,
  },
  storeCardLabel: { fontSize: 11, fontWeight: 'bold', color: '#4a2c2a', letterSpacing: 0.5, marginBottom: 4 },
  storeAddress: { fontSize: 15, fontWeight: 'bold', color: '#2b1d16', lineHeight: 20 },
  storeHint: { fontSize: 12, color: '#8b6f5e', marginTop: 4 },
  sensorCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    elevation: 2,
    borderWidth: 1,
  },
  sensorNormal: { borderColor: '#c8e6c9' },
  sensorAlert: { borderColor: '#ffcdd2', backgroundColor: '#fff8f8' },
  sensorHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sensorTitle: { fontSize: 13, fontWeight: 'bold', color: '#4a2c2a' },
  badge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  badgeNormal: { backgroundColor: '#e8f5e9' },
  badgeAlert: { backgroundColor: '#ffebee' },
  badgeText: { fontSize: 10, fontWeight: 'bold', color: '#2e7d32' },
  sensorMetrics: { flexDirection: 'row', alignItems: 'center' },
  metricItem: { flex: 1, alignItems: 'center' },
  metricVal: { fontSize: 24, fontWeight: 'bold', color: '#4a2c2a' },
  metricLbl: { fontSize: 11, color: '#777', marginTop: 2, textAlign: 'center' },
  metricDivider: { width: 1, height: 36, backgroundColor: '#e0d5c4' },
  noSensor: { color: '#777', fontStyle: 'italic', textAlign: 'center', marginVertical: 8 },
  sectionTitle: { fontSize: 17, fontWeight: 'bold', color: '#4a2c2a', marginVertical: 10 },
  statsGrid: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  statBox: {
    flex: 1,
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 1,
    borderWidth: 1,
    borderColor: '#e8dcce',
  },
  statIcon: { fontSize: 22, marginBottom: 4 },
  statVal: { fontSize: 18, fontWeight: 'bold', color: '#4a2c2a' },
  statLbl: { fontSize: 11, color: '#8b6f5e', textAlign: 'center', marginTop: 2 },
  actionsList: { gap: 10, marginBottom: 16 },
  actionBtnPrimary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#4a2c2a',
    padding: 14,
    borderRadius: 12,
    elevation: 2,
  },
  actionEmoji: { fontSize: 26, marginRight: 12 },
  actionTitlePrimary: { color: '#fff', fontSize: 15, fontWeight: 'bold' },
  actionSubPrimary: { color: '#e0d5c4', fontSize: 12, marginTop: 2 },
  actionArrowPrimary: { color: '#fff', fontSize: 18, marginLeft: 8 },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e8dcce',
    elevation: 1,
  },
  actionTitle: { color: '#4a2c2a', fontSize: 14, fontWeight: 'bold' },
  actionSub: { color: '#8b6f5e', fontSize: 12, marginTop: 1 },
  actionArrow: { color: '#999', fontSize: 16, marginLeft: 8 },
  movementsSection: { marginBottom: 20 },
  movementItem: {
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
    borderLeftWidth: 4,
    borderLeftColor: '#4a2c2a',
    elevation: 1,
  },
  movementHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  movementType: { fontWeight: 'bold', color: '#4a2c2a', fontSize: 13 },
  movementAuthor: { color: '#888', fontSize: 12 },
  movementDetail: { color: '#555', fontSize: 12 },
});
