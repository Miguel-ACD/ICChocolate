import React, { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { Text, Platform, StatusBar, View, ActivityIndicator, StyleSheet, LogBox } from 'react-native';

// Silenciar advertencia informativa interna de Expo Go sobre push remotos
LogBox.ignoreLogs([
  '[expo-notifications]',
  '`expo-notifications` functionality is not fully supported in Expo Go',
]);

import { AuthProvider, useAuth } from './src/context/AuthContext';
import LoginScreen from './src/screens/LoginScreen';
import HomeScreen from './src/screens/HomeScreen';
import StockScreen from './src/screens/StockScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import MonitoringScreen from './src/screens/MonitoringScreen';
import ToolsScreen from './src/screens/ToolsScreen';
import CameraScreen from './src/screens/CameraScreen';
import ChatScreen from './src/screens/ChatScreen';
import WebScreen from './src/screens/WebScreen';

import { configurePushHandler } from './src/notifications';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: '#4a2c2a' },
        headerTintColor: '#fff',
        headerTitleStyle: { fontWeight: 'bold', fontSize: 18 },
        tabBarActiveTintColor: '#4a2c2a',
        tabBarInactiveTintColor: '#8c766b',
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopColor: '#e0d5c4',
          paddingBottom: Platform.OS === 'android' ? 6 : 20,
          height: Platform.OS === 'android' ? 62 : 82,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '700' },
      }}
    >
      <Tab.Screen
        name="Home"
        component={HomeScreen}
        options={{
          title: 'ICChocolate',
          tabBarLabel: 'Inicio',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>🏠</Text>,
        }}
      />
      <Tab.Screen
        name="Stock"
        component={StockScreen}
        options={{
          title: 'Inventario de Stock',
          tabBarLabel: 'Stock',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>📦</Text>,
        }}
      />
      <Tab.Screen
        name="Camera"
        component={CameraScreen}
        options={{
          title: 'Registro y Operaciones',
          tabBarLabel: 'Registro',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>📸</Text>,
        }}
      />
      <Tab.Screen
        name="History"
        component={HistoryScreen}
        options={{
          title: 'Historial de Movimientos',
          tabBarLabel: 'Historial',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>📜</Text>,
        }}
      />
      <Tab.Screen
        name="Monitoring"
        component={MonitoringScreen}
        options={{
          title: 'Monitoreo de Sensores',
          tabBarLabel: 'Monitoreo',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>📡</Text>,
        }}
      />
      <Tab.Screen
        name="Tools"
        component={ToolsScreen}
        options={{
          title: 'Herramientas',
          tabBarLabel: 'Herramientas',
          tabBarIcon: () => <Text style={{ fontSize: 20 }}>⚙️</Text>,
        }}
      />
    </Tab.Navigator>
  );
}

function NavigationRoot() {
  const { isAuthenticated, loading } = useAuth();

  useEffect(() => {
    configurePushHandler();
  }, []);

  if (loading) {
    return (
      <View style={styles.splash}>
        <Text style={styles.splashEmoji}>🍫</Text>
        <ActivityIndicator size="large" color="#4a2c2a" style={{ marginTop: 16 }} />
        <Text style={styles.spashText}>Iniciando ICChocolate…</Text>
      </View>
    );
  }

  return (
    <NavigationContainer>
      <StatusBar barStyle="light-content" backgroundColor="#4a2c2a" />
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: '#4a2c2a' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: 'bold' },
        }}
      >
        {!isAuthenticated ? (
          <Stack.Screen
            name="Login"
            component={LoginScreen}
            options={{ headerShown: false }}
          />
        ) : (
          <>
            <Stack.Screen
              name="MainTabs"
              component={MainTabs}
              options={{ headerShown: false }}
            />
            <Stack.Screen
              name="Camera"
              component={CameraScreen}
              options={{ title: '📸 Registro con Cámara IA' }}
            />
            <Stack.Screen
              name="Chat"
              component={ChatScreen}
              options={{ title: '💬 Asistente IA' }}
            />
            <Stack.Screen
              name="Web"
              component={WebScreen}
              options={{ title: '🌐 Portal Web Django' }}
            />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <NavigationRoot />
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  splash: {
    flex: 1,
    backgroundColor: '#fdf6ec',
    justifyContent: 'center',
    alignItems: 'center',
  },
  splashEmoji: { fontSize: 60 },
  spashText: { marginTop: 12, fontSize: 16, fontWeight: 'bold', color: '#4a2c2a' },
});
