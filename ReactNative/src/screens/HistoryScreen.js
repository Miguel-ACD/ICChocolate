import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, TextInput, FlatList, StyleSheet, RefreshControl,
  TouchableOpacity, ActivityIndicator
} from 'react-native';
import { fetchMovements } from '../api';

const TYPE_CONFIG = {
  INICIAL: { label: 'Carga Inicial', bg: '#e8f5e9', text: '#2e7d32', icon: '📥' },
  COMPRA: { label: 'Compra', bg: '#e3f2fd', text: '#1565c0', icon: '🛒' },
  VENTA: { label: 'Venta', bg: '#f3e5f5', text: '#7b1fa2', icon: '💰' },
  TRASLADO: { label: 'Traslado', bg: '#fff3e0', text: '#e65100', icon: '🔄' },
  MERMA: { label: 'Merma', bg: '#ffebee', text: '#c62828', icon: '⚠️' },
  AJUSTE: { label: 'Ajuste', bg: '#eceff1', text: '#455a64', icon: '⚙️' },
};

function formatDateTime(isoString) {
  if (!isoString) return '';
  try {
    const d = new Date(isoString);
    return d.toLocaleString('es-PE', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

export default function HistoryScreen() {
  const [movements, setMovements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState('ALL');

  const load = useCallback(async () => {
    try {
      setError('');
      const data = await fetchMovements();
      setMovements(Array.isArray(data) ? data : data.results || []);
    } catch (e) {
      console.warn('Error loading movements:', e);
      setError('No se pudo cargar el historial de movimientos.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const filteredMovements = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return movements.filter((m) => {
      if (selectedType !== 'ALL' && m.type !== selectedType) {
        return false;
      }
      if (!q) return true;
      const typeStr = (m.type_label || m.type || '').toLowerCase();
      const reasonStr = (m.reason || '').toLowerCase();
      const authorStr = (m.created_by_alias || '').toLowerCase();
      const linesStr = (m.lines || [])
        .map((l) => `${l.presentation_snapshot} ${l.location_snapshot}`)
        .join(' ')
        .toLowerCase();

      return (
        typeStr.includes(q) ||
        reasonStr.includes(q) ||
        authorStr.includes(q) ||
        linesStr.includes(q)
      );
    });
  }, [movements, searchQuery, selectedType]);

  const renderMovementItem = ({ item }) => {
    const config = TYPE_CONFIG[item.type] || {
      label: item.type_label || item.type,
      bg: '#f5eee6',
      text: '#4a2c2a',
      icon: '📋',
    };

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={[styles.typeBadge, { backgroundColor: config.bg }]}>
            <Text style={styles.typeIcon}>{config.icon}</Text>
            <Text style={[styles.typeText, { color: config.text }]}>
              {config.label}
            </Text>
          </View>
          <Text style={styles.dateText}>{formatDateTime(item.created_at)}</Text>
        </View>

        {item.reason ? (
          <Text style={styles.reasonText}>"{item.reason}"</Text>
        ) : null}

        <View style={styles.linesSection}>
          {(item.lines || []).map((line, idx) => {
            const isPositive = Number(line.delta) > 0;
            return (
              <View key={idx} style={styles.lineItem}>
                <View style={styles.lineDesc}>
                  <Text style={styles.linePres}>{line.presentation_snapshot}</Text>
                  <Text style={styles.lineLoc}>📍 {line.location_snapshot}</Text>
                </View>
                <View style={[styles.deltaBadge, isPositive ? styles.deltaPos : styles.deltaNeg]}>
                  <Text style={[styles.deltaText, isPositive ? styles.deltaTextPos : styles.deltaTextNeg]}>
                    {isPositive ? `+${line.delta}` : line.delta}
                  </Text>
                </View>
              </View>
            );
          })}
        </View>

        <View style={styles.footerRow}>
          <Text style={styles.authorText}>
            👤 {item.created_by_alias || 'Sistema'}
            {item.confirmed_by_alias && item.confirmed_by_alias !== item.created_by_alias
              ? ` · Conf: ${item.confirmed_by_alias}`
              : ''}
          </Text>
          <Text style={styles.idText}>ID: {String(item.id).substring(0, 8)}</Text>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {/* Barra de Búsqueda y Filtros */}
      <View style={styles.searchHeader}>
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>🔍</Text>
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar por motivo, producto o usuario..."
            placeholderTextColor="#9e8b7c"
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')} style={styles.clearBtn}>
              <Text style={styles.clearBtnText}>✕</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Chips de Tipos */}
        <View style={styles.filterRow}>
          <FlatList
            horizontal
            showsHorizontalScrollIndicator={false}
            data={[
              { id: 'ALL', label: 'Todos' },
              { id: 'INICIAL', label: '📥 Inicial' },
              { id: 'COMPRA', label: '🛒 Compra' },
              { id: 'VENTA', label: '💰 Venta' },
              { id: 'TRASLADO', label: '🔄 Traslado' },
              { id: 'MERMA', label: '⚠️ Merma' },
              { id: 'AJUSTE', label: '⚙️ Ajuste' },
            ]}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => {
              const active = selectedType === item.id;
              return (
                <TouchableOpacity
                  style={[styles.filterChip, active && styles.filterChipActive]}
                  onPress={() => setSelectedType(item.id)}
                >
                  <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>
                    {item.label}
                  </Text>
                </TouchableOpacity>
              );
            }}
          />
        </View>

        <View style={styles.summaryBar}>
          <Text style={styles.summaryText}>
            Mostrando <Text style={styles.summaryBold}>{filteredMovements.length}</Text> movimientos
          </Text>
        </View>
      </View>

      {error ? (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>⚠️ {error}</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={load}>
            <Text style={styles.retryBtnText}>Reintentar</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#4a2c2a" />
          <Text style={styles.loadingText}>Cargando historial de movimientos...</Text>
        </View>
      ) : (
        <FlatList
          data={filteredMovements}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderMovementItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={['#4a2c2a']}
              tintColor="#4a2c2a"
            />
          }
          ListEmptyComponent={
            !loading && (
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyIcon}>📜</Text>
                <Text style={styles.emptyTitle}>No hay movimientos registrados</Text>
                <Text style={styles.emptySubtitle}>
                  {searchQuery
                    ? `No se encontraron coincidencias para "${searchQuery}"`
                    : 'Aún no se han ejecutado movimientos para el filtro seleccionado.'}
                </Text>
              </View>
            )
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  searchHeader: {
    backgroundColor: '#fff',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#ede0d0',
  },
  searchBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f5eee6',
    borderRadius: 10,
    paddingHorizontal: 12,
    height: 44,
  },
  searchIcon: { fontSize: 16, marginRight: 8 },
  searchInput: {
    flex: 1,
    fontSize: 14,
    color: '#4a2c2a',
  },
  clearBtn: { padding: 6 },
  clearBtnText: { fontSize: 14, color: '#8b6f5e', fontWeight: 'bold' },
  filterRow: {
    marginTop: 10,
    marginBottom: 4,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f5eee6',
    borderWidth: 1,
    borderColor: '#e2d3c2',
    marginRight: 8,
  },
  filterChipActive: {
    backgroundColor: '#4a2c2a',
    borderColor: '#4a2c2a',
  },
  filterChipText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#6d5a4d',
  },
  filterChipTextActive: {
    color: '#fff',
  },
  summaryBar: {
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: '#f2eae1',
  },
  summaryText: { fontSize: 12, color: '#7a6658' },
  summaryBold: { fontWeight: 'bold', color: '#4a2c2a' },
  listContent: {
    padding: 12,
    paddingBottom: 24,
  },
  card: {
    backgroundColor: '#fff',
    marginBottom: 10,
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    shadowColor: '#4a2c2a',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  typeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  typeIcon: { fontSize: 13, marginRight: 5 },
  typeText: { fontSize: 12, fontWeight: '700' },
  dateText: { fontSize: 12, color: '#8c766b' },
  reasonText: {
    fontSize: 13,
    fontStyle: 'italic',
    color: '#5c4a3e',
    marginBottom: 8,
  },
  linesSection: {
    backgroundColor: '#faf6f0',
    borderRadius: 8,
    padding: 8,
    marginBottom: 8,
  },
  lineItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#ede4d8',
  },
  lineDesc: { flex: 1, marginRight: 10 },
  linePres: { fontSize: 13, fontWeight: '600', color: '#4a2c2a' },
  lineLoc: { fontSize: 11, color: '#8c766b', marginTop: 1 },
  deltaBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    minWidth: 42,
    alignItems: 'center',
  },
  deltaPos: { backgroundColor: '#e8f5e9' },
  deltaNeg: { backgroundColor: '#ffebee' },
  deltaText: { fontSize: 13, fontWeight: 'bold' },
  deltaTextPos: { color: '#2e7d32' },
  deltaTextNeg: { color: '#c62828' },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 4,
  },
  authorText: { fontSize: 12, color: '#7a6658' },
  idText: { fontSize: 11, color: '#a09083', fontFamily: 'monospace' },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 10, fontSize: 14, color: '#6d5a4d' },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 50,
    paddingHorizontal: 24,
  },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 16, fontWeight: 'bold', color: '#4a2c2a', marginBottom: 6 },
  emptySubtitle: { fontSize: 13, color: '#8c766b', textAlign: 'center' },
  errorContainer: {
    backgroundColor: '#ffebee',
    margin: 12,
    padding: 12,
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  errorText: { color: '#c62828', fontSize: 13, flex: 1, marginRight: 8 },
  retryBtn: { backgroundColor: '#c62828', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6 },
  retryBtnText: { color: '#fff', fontSize: 12, fontWeight: 'bold' },
});

