import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Alert,
  StyleSheet, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useAuth } from '../context/AuthContext';

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Datos incompletos', 'Por favor ingresa tu correo y contraseña.');
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password);
    } catch (e) {
      console.warn('Login error:', e);
      let msg = 'No se pudo conectar al servidor (verifica Wi-Fi o puerto 8003).';
      if (e.response?.status === 401) {
        msg = 'Credenciales inválidas. Revisa tu correo y contraseña.';
      } else if (e.response?.data?.detail) {
        msg = String(e.response.data.detail);
      }
      Alert.alert('Error de inicio de sesión', msg);
    } finally {
      setLoading(false);
    }
  };

  // Autocompletar cuentas demo
  const fillDemo = (demoEmail, demoPassword) => {
    setEmail(demoEmail);
    setPassword(demoPassword);
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.header}>
          <Text style={styles.logo}>🍫</Text>
          <Text style={styles.title}>ICChocolate</Text>
          <Text style={styles.subtitle}>Gestión de Inventario y Calidad</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Iniciar Sesión</Text>
          <Text style={styles.cardHint}>Ingresa tus credenciales para acceder al sistema.</Text>

          <Text style={styles.label}>Correo Electrónico</Text>
          <TextInput
            placeholder="usuario@icchocolate.local"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            style={styles.input}
            placeholderTextColor="#a89a8c"
            editable={!loading}
          />

          <Text style={styles.label}>Contraseña</Text>
          <TextInput
            placeholder="••••••••"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            style={styles.input}
            placeholderTextColor="#a89a8c"
            editable={!loading}
          />

          <TouchableOpacity
            style={[styles.btnSubmit, loading && styles.btnDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.btnSubmitText}>Ingresar al Sistema</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Accesos rápidos para cuentas demo */}
        <View style={styles.demoSection}>
          <Text style={styles.demoHeader}>Acceso rápido con cuentas de prueba:</Text>
          <View style={styles.demoButtons}>
            <TouchableOpacity
              style={styles.btnDemo}
              onPress={() => fillDemo('dueno@icchocolate.local', 'OwnerPass!2026')}
            >
              <Text style={styles.btnDemoEmoji}>👑</Text>
              <View>
                <Text style={styles.btnDemoTitle}>Cuenta Dueño</Text>
                <Text style={styles.btnDemoSub}>Acceso total y configuración</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.btnDemo}
              onPress={() => fillDemo('empleado@icchocolate.local', 'EmpPass!2026')}
            >
              <Text style={styles.btnDemoEmoji}>👤</Text>
              <View>
                <Text style={styles.btnDemoTitle}>Cuenta Empleado</Text>
                <Text style={styles.btnDemoSub}>Movimientos e inventario</Text>
              </View>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, backgroundColor: '#fdf6ec', padding: 20, justifyContent: 'center' },
  header: { alignItems: 'center', marginBottom: 24 },
  logo: { fontSize: 56, marginBottom: 4 },
  title: { fontSize: 30, fontWeight: 'bold', color: '#4a2c2a' },
  subtitle: { fontSize: 14, color: '#8b6f5e', marginTop: 2 },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 22,
    elevation: 3,
    shadowColor: '#4a2c2a',
    shadowOpacity: 0.1,
    shadowRadius: 8,
    borderWidth: 1,
    borderColor: '#e8dcce',
  },
  cardTitle: { fontSize: 20, fontWeight: 'bold', color: '#4a2c2a', marginBottom: 4 },
  cardHint: { fontSize: 13, color: '#8b6f5e', marginBottom: 18 },
  label: { fontSize: 13, fontWeight: '600', color: '#5a4638', marginBottom: 6 },
  input: {
    borderWidth: 1,
    borderColor: '#d8c8b8',
    backgroundColor: '#fbf9f6',
    marginBottom: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 8,
    fontSize: 15,
    color: '#2b1d16',
  },
  btnSubmit: {
    backgroundColor: '#4a2c2a',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 4,
  },
  btnDisabled: { opacity: 0.6 },
  btnSubmitText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  demoSection: { marginTop: 24 },
  demoHeader: { fontSize: 12, fontWeight: 'bold', color: '#8b6f5e', textAlign: 'center', marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  demoButtons: { gap: 10 },
  btnDemo: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d8c8b8',
    padding: 12,
    borderRadius: 10,
    elevation: 1,
  },
  btnDemoEmoji: { fontSize: 24, marginRight: 12 },
  btnDemoTitle: { fontSize: 14, fontWeight: 'bold', color: '#4a2c2a' },
  btnDemoSub: { fontSize: 12, color: '#8b6f5e' },
});
