import React, { useRef, useState } from 'react';
import {
  View, StyleSheet, ActivityIndicator, TouchableOpacity,
  Text, BackHandler, Platform,
} from 'react-native';
import { WebView } from 'react-native-webview';
import { useFocusEffect } from '@react-navigation/native';

const WEB_URL = 'http://192.168.18.126:8003/';

export default function WebScreen() {
  const webViewRef = useRef(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [loading, setLoading] = useState(true);

  // Manejar botón físico Atrás en Android dentro del WebView
  useFocusEffect(
    React.useCallback(() => {
      if (Platform.OS !== 'android') return;
      const onBackPress = () => {
        if (canGoBack && webViewRef.current) {
          webViewRef.current.goBack();
          return true;
        }
        return false;
      };
      const sub = BackHandler.addEventListener('hardwareBackPress', onBackPress);
      return () => sub.remove();
    }, [canGoBack])
  );

  return (
    <View style={styles.container}>
      {/* Barra de control rápido */}
      <View style={styles.topBar}>
        <TouchableOpacity
          style={[styles.barBtn, !canGoBack && styles.btnDisabled]}
          onPress={() => webViewRef.current?.goBack()}
          disabled={!canGoBack}
        >
          <Text style={styles.barBtnText}>◀ Atrás</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.barBtn}
          onPress={() => webViewRef.current?.reload()}
        >
          <Text style={styles.barBtnText}>🔄 Recargar</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.barBtn}
          onPress={() => webViewRef.current?.injectJavaScript(`window.location.href = "${WEB_URL}"; true;`)}
        >
          <Text style={styles.barBtnText}>🏠 Inicio</Text>
        </TouchableOpacity>
      </View>

      {/* WebView con la interfaz web completa de ICChocolate */}
      <WebView
        ref={webViewRef}
        source={{ uri: WEB_URL }}
        style={styles.webview}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        sharedCookiesEnabled={true}
        thirdPartyCookiesEnabled={true}
        allowFileAccess={true}
        scalesPageToFit={true}
        onNavigationStateChange={(navState) => {
          setCanGoBack(navState.canGoBack);
        }}
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
      />

      {loading && (
        <View style={styles.loadingOverlay}>
          <ActivityIndicator size="large" color="#4a2c2a" />
          <Text style={styles.loadingText}>Cargando ICChocolate…</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fdf6ec' },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#4a2c2a',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  barBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#6b3e37',
    borderRadius: 6,
  },
  btnDisabled: { opacity: 0.4 },
  barBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  webview: { flex: 1, backgroundColor: '#fdf6ec' },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(253, 246, 236, 0.85)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: { marginTop: 12, color: '#4a2c2a', fontSize: 15, fontWeight: '600' },
});

