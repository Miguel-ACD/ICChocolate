import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, TextInput, FlatList, StyleSheet, RefreshControl,
  TouchableOpacity, ActivityIndicator
} from 'react-native';
import { fetchStock } from '../api';

export default function StockScreen() {
  const [stock, setStock] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('ALL'); // 'ALL' | 'ALMACEN' | 'DISPLAY'

  const load = useCallback(async () => {
    try {
      setError('');
      const data = await fetchStock();
      setStock(Array.isArray(data) ? data : data.results || []);
    } catch (e) {
      console.warn('Error loading stock:', e);
      setError('No se pudo cargar el inventario. Verifica la conexión.');
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

  // Filtrado reactivo en tiempo real
  const filteredStock = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return stock.filter((item) => {
      // Filtro de ubicación
      if (selectedLocation === 'ALMACEN' && !item.location_name?.toLowerCase().includes('almacén') && item.location_code !== 'ALMACEN') {
        return false;
      }
      if (selectedLocation === 'DISPLAY' && !item.location_name?.toLowerCase().includes('display') && item.location_code !== 'DISPLAY') {
        return false;
      }
      // Filtro de búsqueda de texto
      if (!q) return true;
      const productName = (item.product_name || '').toLowerCase();
      const presCode = (item.presentation_code || '').toLowerCase();
      const presName = (item.presentation_name || '').toLowerCase();
      const locName = (item.location_name || '').toLowerCase();
      return (
        productName.includes(q) ||
        presCode.includes(q) ||
        presName.includes(q) ||
        locName.includes(q)
      );
    });
  }, [stock, searchQuery, selectedLocation]);

  const totalFilteredUnits = useMemo(() => {
    return filteredStock.reduce((acc, curr) => acc + (Number(curr.quantity) || 0), 0);
  }, [filteredStock]);

  const renderItem = ({ item }) => {
    const isLow = Number(item.quantity) <= 5;
    const isWarehouse = (item.location_code || '').toUpperCase().includes('ALMACEN') ||
                        (item.location_name || '').toLowerCase().includes('almacén');

    return (
      <View style={styles.card}>
        <View style={styles.cardTop}>
          <View style={styles.productHeader}>
            <Text style={styles.productIcon}>🍫</Text>
            <View style={{ flex: 1 }}>
              <Text style={styles.productName}>{item.product_name}</Text>
              <Text style={styles.presName}>{item.presentation_name}</Text>
            </View>
          </View>
          <View style={styles.badgeCode}>
            <Text style={styles.badgeCodeText}>{item.presentation_code}</Text>
          </View>
        </View>

        <View style={styles.cardDivider} />

        <View style={styles.cardBottom}>
          <View style={[styles.locBadge, isWarehouse ? styles.locWarehouse : styles.locDisplay]}>
            <Text style={styles.locBadgeText}>
              {isWarehouse ? '📦 Almacén' : '🏪 Display Tienda'}
            </Text>
          </View>

          <View style={styles.qtyContainer}>
            <Text style={[styles.qtyNumber, isLow && styles.qtyLow]}>
              {item.quantity}
            </Text>
            <Text style={styles.qtyUnit}>uds</Text>
          </View>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {/* Barra de búsqueda */}
      <View style={styles.searchHeader}>
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>🔍</Text>
          <TextInput
            style={styles.searchInput}
            placeholder="Buscar por producto, código (BARRA-100)..."
            placeholderTextColor="#9e8b7c"
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoCapitalize="none"
            autoCorrect={false}
            clearButtonMode="while-editing"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')} style={styles.clearBtn}>
              <Text style={styles.clearBtnText}>✕</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Chips de filtro por ubicación */}
        <View style={styles.filterRow}>
          <TouchableOpacity
            style={[styles.filterChip, selectedLocation === 'ALL' && styles.filterChipActive]}
            onPress={() => setSelectedLocation('ALL')}
          >
            <Text style={[styles.filterChipText, selectedLocation === 'ALL' && styles.filterChipTextActive]}>
              Todos ({stock.length})
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.filterChip, selectedLocation === 'ALMACEN' && styles.filterChipActive]}
            onPress={() => setSelectedLocation('ALMACEN')}
          >
            <Text style={[styles.filterChipText, selectedLocation === 'ALMACEN' && styles.filterChipTextActive]}>
              📦 Almacén
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.filterChip, selectedLocation === 'DISPLAY' && styles.filterChipActive]}
            onPress={() => setSelectedLocation('DISPLAY')}
          >
            <Text style={[styles.filterChipText, selectedLocation === 'DISPLAY' && styles.filterChipTextActive]}>
              🏪 Display
            </Text>
          </TouchableOpacity>
        </View>

        {/* Barra de estadísticas resumida */}
        <View style={styles.summaryBar}>
          <Text style={styles.summaryText}>
            Mostrando <Text style={styles.summaryBold}>{filteredStock.length}</Text> de {stock.length} ítems
          </Text>
          <Text style={styles.summaryUnits}>
            Total: <Text style={styles.summaryBold}>{totalFilteredUnits}</Text> unidades
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
          <Text style={styles.loadingText}>Cargando inventario...</Text>
        </View>
      ) : (
        <FlatList
          data={filteredStock}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderItem}
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
                <Text style={styles.emptyIcon}>📦</Text>
                <Text style={styles.emptyTitle}>No se encontraron resultados</Text>
                <Text style={styles.emptySubtitle}>
                  {searchQuery
                    ? `No hay coincidencias para "${searchQuery}"`
                    : 'No hay stock registrado en esta ubicación.'}
                </Text>
                {searchQuery ? (
                  <TouchableOpacity
                    style={styles.clearSearchBtn}
                    onPress={() => {
                      setSearchQuery('');
                      setSelectedLocation('ALL');
                    }}
                  >
                    <Text style={styles.clearSearchBtnText}>Limpiar búsqueda</Text>
                  </TouchableOpacity>
                ) : null}
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
    paddingVertical: 0,
  },
  clearBtn: {
    padding: 6,
  },
  clearBtnText: {
    fontSize: 14,
    color: '#8b6f5e',
    fontWeight: 'bold',
  },
  filterRow: {
    flexDirection: 'row',
    marginTop: 10,
    gap: 8,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#f5eee6',
    borderWidth: 1,
    borderColor: '#e2d3c2',
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
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f2eae1',
  },
  summaryText: {
    fontSize: 12,
    color: '#7a6658',
  },
  summaryUnits: {
    fontSize: 12,
    color: '#7a6658',
  },
  summaryBold: {
    fontWeight: 'bold',
    color: '#4a2c2a',
  },
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
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  productHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginRight: 8,
  },
  productIcon: {
    fontSize: 24,
    marginRight: 10,
  },
  productName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#4a2c2a',
  },
  presName: {
    fontSize: 13,
    color: '#8b6f5e',
    marginTop: 2,
  },
  badgeCode: {
    backgroundColor: '#f2e8dc',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#dfcfbe',
  },
  badgeCodeText: {
    fontSize: 11,
    fontFamily: 'monospace',
    fontWeight: 'bold',
    color: '#5c3a21',
  },
  cardDivider: {
    height: 1,
    backgroundColor: '#f5eee6',
    marginVertical: 10,
  },
  cardBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  locBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  locWarehouse: {
    backgroundColor: '#e8f0fe',
  },
  locDisplay: {
    backgroundColor: '#fef7e0',
  },
  locBadgeText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#333',
  },
  qtyContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  qtyNumber: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#2e7d32',
  },
  qtyLow: {
    color: '#d32f2f',
  },
  qtyUnit: {
    fontSize: 12,
    color: '#777',
    marginLeft: 4,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 50,
    paddingHorizontal: 24,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#4a2c2a',
    marginBottom: 6,
  },
  emptySubtitle: {
    fontSize: 13,
    color: '#8c766b',
    textAlign: 'center',
    marginBottom: 16,
  },
  clearSearchBtn: {
    backgroundColor: '#4a2c2a',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  clearSearchBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    marginTop: 10,
    fontSize: 14,
    color: '#6d5a4d',
  },
  errorContainer: {
    backgroundColor: '#ffebee',
    margin: 12,
    padding: 12,
    borderRadius: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  errorText: {
    color: '#c62828',
    fontSize: 13,
    flex: 1,
    marginRight: 8,
  },
  retryBtn: {
    backgroundColor: '#c62828',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  retryBtnText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: 'bold',
  },
});
