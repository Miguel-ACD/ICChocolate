import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, FlatList, StyleSheet, RefreshControl } from 'react-native';
import { fetchAlerts } from '../api';

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchAlerts();
      setAlerts(Array.isArray(data) ? data : data.results || []);
    } catch (e) {
      console.warn('Error cargando alertas', e);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const statusEmoji = (s) => {
    if (s === 'ACTIVO') return '🔴';
    if (s === 'RECUPERADO') return '✅';
    return '⚪';
  };

  const renderItem = ({ item }) => (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.device}>{statusEmoji(item.status)} {item.device_code}</Text>
        <Text style={styles.status}>{item.status}</Text>
      </View>
      <Text style={styles.detail}>📍 {item.location_snapshot}  •  Umbral: {item.threshold_snapshot} °C</Text>
      <Text style={styles.date}>Inicio: {new Date(item.started_at).toLocaleString()}</Text>
      {item.closed_at && (
        <Text style={styles.date}>Cierre: {new Date(item.closed_at).toLocaleString()}</Text>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <FlatList
        data={alerts}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={<Text style={styles.empty}>Sin alertas registradas.</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  card: {
    backgroundColor: '#fff', marginHorizontal: 12, marginTop: 10,
    padding: 14, borderRadius: 8, elevation: 1,
  },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  device: { fontSize: 16, fontWeight: 'bold', color: '#4a2c2a' },
  status: { fontSize: 13, fontWeight: '600', color: '#8b6f5e' },
  detail: { fontSize: 13, color: '#555', marginTop: 2 },
  date: { fontSize: 12, color: '#999', marginTop: 2 },
  empty: { textAlign: 'center', marginTop: 40, color: '#999' },
});

