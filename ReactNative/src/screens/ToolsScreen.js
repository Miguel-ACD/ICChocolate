import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert
} from 'react-native';
import * as Location from 'expo-location';
import { useAuth } from '../context/AuthContext';

export default function ToolsScreen({ navigation }) {
  const { user, logout } = useAuth();
  const [storeAddress, setStoreAddress] = useState('Detectando ubicación real de la tienda…');

  const detectLocation = useCallback(async () => {
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
          setStoreAddress('Sede Principal');
        }
      } else {
        setStoreAddress('Sede Principal (Permiso de ubicación no concedido)');
      }
    } catch {
      setStoreAddress('Sede Principal (Ubicación activa)');
    }
  }, []);

  useEffect(() => {
    detectLocation();
  }, [detectLocation]);

  const handleLogout = () => {
    Alert.alert(
      'Cerrar Sesión',
      '¿Estás seguro de que deseas salir del sistema?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Salir', style: 'destructive', onPress: logout },
      ]
    );
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Tarjeta de Perfil / Usuario */}
      <View style={styles.profileCard}>
        <View style={styles.avatarBox}>
          <Text style={styles.avatarEmoji}>👤</Text>
        </View>
        <View style={styles.profileInfo}>
          <Text style={styles.userName}>{user?.alias || 'Usuario'}</Text>
          <Text style={styles.userRole}>
            {user?.role === 'DUENO' ? '👑 Dueño / Administrador' : '💼 Empleado de Tienda'}
          </Text>
          <Text style={styles.userEmail}>{user?.email || 'usuario@icchocolate.local'}</Text>
        </View>
      </View>

      {/* Sección: Herramientas Operativas */}
      <Text style={styles.sectionHeader}>HERRAMIENTAS OPERATIVAS</Text>

      <TouchableOpacity
        style={styles.toolCard}
        onPress={() => navigation.navigate('Camera')}
      >
        <View style={[styles.toolIconBox, { backgroundColor: '#e8f5e9' }]}>
          <Text style={styles.toolIcon}>📸</Text>
        </View>
        <View style={styles.toolContent}>
          <Text style={styles.toolTitle}>Cámara IA & Reconocimiento</Text>
          <Text style={styles.toolDesc}>
            Fotografía boletas de compra o etiquetas de lote para extracción automática con Gemini Vision.
          </Text>
        </View>
        <Text style={styles.toolArrow}>›</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.toolCard}
        onPress={() => navigation.navigate('Chat')}
      >
        <View style={[styles.toolIconBox, { backgroundColor: '#e3f2fd' }]}>
          <Text style={styles.toolIcon}>💬</Text>
        </View>
        <View style={styles.toolContent}>
          <Text style={styles.toolTitle}>Asistente Inteligente IA</Text>
          <Text style={styles.toolDesc}>
            Consulta en lenguaje natural sobre stock crítico, mermas, recomendaciones y temperaturas.
          </Text>
        </View>
        <Text style={styles.toolArrow}>›</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.toolCard}
        onPress={() => navigation.navigate('Web')}
      >
        <View style={[styles.toolIconBox, { backgroundColor: '#fff3e0' }]}>
          <Text style={styles.toolIcon}>🌐</Text>
        </View>
        <View style={styles.toolContent}>
          <Text style={styles.toolTitle}>Portal Web Django Completo</Text>
          <Text style={styles.toolDesc}>
            Accede al panel web administrativo con gráficos, tablas avanzadas y administración.
          </Text>
        </View>
        <Text style={styles.toolArrow}>›</Text>
      </TouchableOpacity>

      {/* Sección: Sede y Sucursal */}
      <Text style={styles.sectionHeader}>UBICACIÓN DE TIENDA</Text>
      <View style={styles.storeCard}>
        <View style={styles.storeHeader}>
          <Text style={styles.storeIcon}>🏪</Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.storeName}>Sede Principal - ICChocolate</Text>
            <Text style={styles.storeAddress}>
              {storeAddress}
            </Text>
          </View>
        </View>
        <View style={styles.storeDivider} />
        <Text style={styles.storeNote}>
          ℹ️ La verificación de ubicación física confirma la sucursal asignada a tus movimientos y sensores.
        </Text>
      </View>

      {/* Sección: Sistema e Infraestructura */}
      <Text style={styles.sectionHeader}>INFORMACIÓN TÉCNICA DEL SISTEMA</Text>
      <View style={styles.systemCard}>
        <View style={styles.systemRow}>
          <Text style={styles.systemLabel}>Servidor Backend API:</Text>
          <Text style={styles.systemValue}>192.168.18.126:8003</Text>
        </View>
        <View style={styles.systemRow}>
          <Text style={styles.systemLabel}>Base de Datos:</Text>
          <Text style={styles.systemValue}>PostgreSQL 17 (Docker)</Text>
        </View>
        <View style={styles.systemRow}>
          <Text style={styles.systemLabel}>Gateway de Sensores:</Text>
          <Text style={styles.systemValue}>ESP32 DHT11 (Puerto 8002)</Text>
        </View>
        <View style={styles.systemRow}>
          <Text style={styles.systemLabel}>Versión App Móvil:</Text>
          <Text style={styles.systemValue}>0.1.0 (SDK 58 / React Native)</Text>
        </View>
      </View>

      {/* Botón de Cerrar Sesión */}
      <TouchableOpacity style={styles.btnLogout} onPress={handleLogout}>
        <Text style={styles.btnLogoutText}>🚪 Cerrar Sesión</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  content: { padding: 16, paddingBottom: 40 },
  profileCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 20,
    shadowColor: '#4a2c2a',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
  avatarBox: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#f5eee6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
  },
  avatarEmoji: { fontSize: 26 },
  profileInfo: { flex: 1 },
  userName: { fontSize: 18, fontWeight: 'bold', color: '#4a2c2a' },
  userRole: { fontSize: 13, color: '#2e7d32', fontWeight: '600', marginTop: 2 },
  userEmail: { fontSize: 12, color: '#8c766b', marginTop: 2 },
  sectionHeader: {
    fontSize: 12,
    fontWeight: '700',
    color: '#8c766b',
    marginBottom: 8,
    marginTop: 6,
    letterSpacing: 0.5,
  },
  toolCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 10,
    shadowColor: '#4a2c2a',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  toolIconBox: {
    width: 44,
    height: 44,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  toolIcon: { fontSize: 22 },
  toolContent: { flex: 1, marginRight: 8 },
  toolTitle: { fontSize: 15, fontWeight: 'bold', color: '#4a2c2a' },
  toolDesc: { fontSize: 12, color: '#7a6658', marginTop: 2, lineHeight: 16 },
  toolArrow: { fontSize: 22, color: '#b0a093', fontWeight: 'bold' },
  storeCard: {
    backgroundColor: '#fff',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 16,
  },
  storeHeader: { flexDirection: 'row', alignItems: 'center' },
  storeIcon: { fontSize: 26, marginRight: 12 },
  storeName: { fontSize: 14, fontWeight: 'bold', color: '#4a2c2a' },
  storeAddress: { fontSize: 12, color: '#6d5a4d', marginTop: 2 },
  storeDivider: { height: 1, backgroundColor: '#f5eee6', marginVertical: 10 },
  storeNote: { fontSize: 11, color: '#8c766b', lineHeight: 15 },
  systemCard: {
    backgroundColor: '#fff',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#ebdccb',
    marginBottom: 20,
  },
  systemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 5,
    borderBottomWidth: 1,
    borderBottomColor: '#f8f4ee',
  },
  systemLabel: { fontSize: 12, color: '#7a6658' },
  systemValue: { fontSize: 12, fontWeight: '600', color: '#4a2c2a' },
  btnLogout: {
    backgroundColor: '#ffebee',
    borderWidth: 1,
    borderColor: '#ffcdd2',
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 6,
  },
  btnLogoutText: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#c62828',
  },
});

