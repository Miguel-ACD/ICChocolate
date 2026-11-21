import React, { createContext, useState, useEffect, useContext } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, login as apiLogin, logout as apiLogout } from '../api';
import { registerForPushNotifications } from '../notifications';

const AuthContext = createContext();

export function AuthProvider({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);

  // Al iniciar la app, verificar si hay sesión guardada
  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const token = await AsyncStorage.getItem('jwt_access');
      if (token) {
        // Obtener datos del usuario desde el dashboard
        try {
          const resp = await api.get('/dashboard/');
          setUser(resp.data.user);
          setIsAuthenticated(true);
          registerForPushNotifications().catch(() => {});
        } catch (e) {
          await apiLogout();
          setIsAuthenticated(false);
          setUser(null);
        }
      } else {
        setIsAuthenticated(false);
        setUser(null);
      }
    } catch (e) {
      setIsAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    const token = await apiLogin(email, password);
    // Cargar perfil
    try {
      const resp = await api.get('/dashboard/');
      setUser(resp.data.user);
    } catch {
      setUser({ email, alias: email.split('@')[0], role: 'USUARIO' });
    }
    setIsAuthenticated(true);
    registerForPushNotifications().catch(() => {});
    return token;
  };

  const logout = async () => {
    await apiLogout();
    setIsAuthenticated(false);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, loading, user, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth debe ser usado dentro de un AuthProvider');
  }
  return context;
}

